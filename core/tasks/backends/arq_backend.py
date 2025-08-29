"""
ARQ队列后端实现

基于ARQ实现的异步任务队列后端，支持原生asyncio
"""

import os
import asyncio
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
import redis.asyncio as redis
from arq import create_pool, ArqRedis
from arq.connections import RedisSettings
from arq.jobs import Job
from arq.constants import job_key_prefix
from loguru import logger

from ..base.queue_backend import QueueBackend
from ..models.task_models import BaseTask, TaskResult, TaskStatus
from core.config.config_center import get_app_config


class ARQTaskBackend(QueueBackend):
    """ARQ队列后端实现"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化ARQ后端
        
        Args:
            config: ARQ配置参数
        """
        self.config = config or {}
        
        # 从传入的config获取Redis配置
        self.redis_settings = RedisSettings(
            host=self.config.get('redis_host', '127.0.0.1'),
            port=self.config.get('redis_port', 6379),
            database=self.config.get('redis_db', 0),
            password=self.config.get('redis_password'),
            max_connections=self.config.get('max_connections', 10)
        )
        
        # 队列配置
        self.default_queue_name = self.config.get('default_queue', 'arq:queue')
        self.job_timeout = self.config.get('job_timeout', 3600)
        self.keep_result = self.config.get('keep_result', 86400)  # 保留结果24小时
        
        # 连接池（延迟初始化）
        self.pool: Optional[ArqRedis] = None
        self.redis_client: Optional[redis.Redis] = None
        
        logger.info(f"ARQ backend configured with Redis: {self.redis_settings.host}:{self.redis_settings.port}")
    
    async def _ensure_connection(self):
        """确保Redis连接池已初始化"""
        if self.pool is None:
            self.pool = await create_pool(self.redis_settings)
            self.redis_client = redis.Redis(
                host=self.redis_settings.host,
                port=self.redis_settings.port,
                db=self.redis_settings.database,
                password=self.redis_settings.password,
                max_connections=self.redis_settings.max_connections
            )
            logger.info("ARQ connection pool created")
    
    async def enqueue_task(
        self, 
        task: BaseTask, 
        func: Callable, 
        *args, 
        **kwargs
    ) -> str:
        """将任务加入队列"""
        try:
            await self._ensure_connection()
            
            # 设置任务参数
            job_kwargs = {
                'job_timeout': timedelta(seconds=task.timeout),
                'keep_result': timedelta(seconds=self.keep_result),
                'job_id': task.task_id,  # 使用任务ID作为作业ID
            }
            
            # ARQ需要事先注册函数，这里我们使用通用的处理函数
            # 实际的任务函数和参数通过job参数传递
            job = await self.pool.enqueue_job(
                'process_task',  # 通用处理函数名
                task.dict(),  # 直接传递task_dict作为第一个位置参数
                func.__name__ if hasattr(func, '__name__') else 'anonymous',
                args,
                kwargs,
                **job_kwargs
            )
            
            logger.info(f"Task enqueued: {task.task_id} -> ARQ job: {job.job_id if job else 'None'}")
            return job.job_id if job else task.task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue task {task.task_id}: {str(e)}")
            raise
    
    async def _execute_with_context(
        self, 
        task: BaseTask, 
        func: Callable, 
        *args, 
        **kwargs
    ):
        """在任务上下文中执行函数"""
        import time
        start_time = time.time()
        
        try:
            logger.info(f"Starting async task execution: {task.task_id}")
            
            # 执行异步任务函数
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            execution_time = time.time() - start_time
            logger.info(f"Task completed: {task.task_id} in {execution_time:.2f}s")
            
            # 构建任务结果
            task_result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.COMPLETED,
                result_data=result,
                execution_time=execution_time
            )
            
            return task_result
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Task failed: {task.task_id} after {execution_time:.2f}s - {str(e)}")
            
            # 构建错误结果
            task_result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                result_data=None,
                metadata={'error': str(e)},
                execution_time=execution_time
            )
            
            raise Exception(task_result)  # ARQ会捕获并标记为失败
    
    async def get_task_status(self, queue_task_id: str) -> Dict[str, Any]:
        """获取队列中任务的执行状态"""
        try:
            await self._ensure_connection()
            
            # 获取作业信息
            job = Job(queue_task_id, redis=self.pool)
            arq_status = await job.status()
            
            # ARQ状态映射到TaskStatus
            status_mapping = {
                'queued': TaskStatus.PENDING,
                'in_progress': TaskStatus.PROCESSING,
                'complete': TaskStatus.COMPLETED,
                'not_found': TaskStatus.FAILED,
                'deferred': TaskStatus.PENDING,
            }
            
            task_status = status_mapping.get(arq_status, TaskStatus.PENDING)
            
            # 返回统一格式的状态信息
            return {
                'queue_task_id': queue_task_id,
                'execution_status': task_status,
                'arq_status': arq_status,
                'queue_type': 'arq'
            }
            
        except Exception as e:
            logger.error(f"Failed to get task status: {str(e)}")
            return {
                'queue_task_id': queue_task_id,
                'execution_status': TaskStatus.FAILED,
                'error': str(e),
                'queue_type': 'arq'
            }
    
    async def get_task_result(self, queue_task_id: str) -> Optional[TaskResult]:
        """获取任务执行结果"""
        try:
            await self._ensure_connection()
            
            job = Job(queue_task_id, redis=self.pool)
            status = await job.status()
            
            if status != 'complete':
                return None
            
            # 获取结果
            result = await job.result()
            if isinstance(result, TaskResult):
                return result
            
            # 如果不是TaskResult对象，构建一个
            return TaskResult(
                task_id=queue_task_id,
                status=TaskStatus.COMPLETED,
                result_data=result,
                execution_time=None
            )
            
        except Exception as e:
            logger.error(f"Failed to get task result: {str(e)}")
            return None
    
    async def cancel_task(self, queue_task_id: str) -> bool:
        """取消任务执行"""
        try:
            await self._ensure_connection()
            
            job = Job(queue_task_id, redis=self.pool)
            status = await job.status()
            
            if status in ['complete', 'not_found']:
                return False
            
            # ARQ没有直接的cancel方法，我们通过删除作业来实现
            await job.abort()
            logger.info(f"Task cancelled: {queue_task_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cancel task: {str(e)}")
            return False
    
    async def get_queue_length(self, queue_name: str = "default") -> int:
        """获取队列长度"""
        try:
            await self._ensure_connection()
            
            # ARQ使用Redis列表存储队列
            queue_key = f"{self.default_queue_name}:queue"
            length = await self.redis_client.llen(queue_key)
            return length
            
        except Exception as e:
            logger.error(f"Failed to get queue length: {str(e)}")
            return 0
    
    async def get_failed_tasks(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取失败的任务列表"""
        try:
            await self._ensure_connection()
            
            # 扫描失败的作业
            failed_tasks = []
            
            # ARQ将失败的作业信息存储在Redis中
            # 这里简化实现，实际可能需要更复杂的查询逻辑
            pattern = f"{job_key_prefix}*"
            keys = await self.redis_client.keys(pattern)
            
            for key in keys[:limit]:
                try:
                    job_data = await self.redis_client.hgetall(key)
                    if job_data.get('status') == 'failed':
                        failed_tasks.append({
                            'job_id': key.decode().split(':')[-1],
                            'failed_at': job_data.get('enqueue_time'),
                            'error': job_data.get('result')
                        })
                except Exception:
                    continue
            
            return failed_tasks
            
        except Exception as e:
            logger.error(f"Failed to get failed tasks: {str(e)}")
            return []
    
    async def retry_failed_task(self, queue_task_id: str) -> bool:
        """重试失败的任务"""
        try:
            await self._ensure_connection()
            
            job = Job(queue_task_id, redis=self.pool)
            
            # ARQ的重试机制相对简单，这里实现基础版本
            await job.requeue()
            logger.info(f"Task retried: {queue_task_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to retry task: {str(e)}")
            return False
    
    async def clear_failed_tasks(self) -> int:
        """清理失败任务"""
        try:
            await self._ensure_connection()
            
            count = 0
            pattern = f"{job_key_prefix}*"
            keys = await self.redis_client.keys(pattern)
            
            for key in keys:
                try:
                    job_data = await self.redis_client.hgetall(key)
                    if job_data.get('status') == 'failed':
                        await self.redis_client.delete(key)
                        count += 1
                except Exception:
                    continue
            
            logger.info(f"Cleared {count} failed tasks")
            return count
            
        except Exception as e:
            logger.error(f"Failed to clear failed tasks: {str(e)}")
            return 0
    
    async def health_check(self) -> bool:
        """队列健康检查"""
        try:
            await self._ensure_connection()
            
            # 检查Redis连接
            await self.redis_client.ping()
            
            # 检查ARQ连接池
            info = await self.pool.ping()
            
            return info == b'PONG'
            
        except Exception as e:
            logger.error(f"ARQ health check failed: {str(e)}")
            return False
    
    async def close(self):
        """关闭连接"""
        if self.pool:
            await self.pool.close()
            self.pool = None
        
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None
        
        logger.info("ARQ backend connections closed")
    
    def get_worker_functions(self) -> Dict[str, Callable]:
        """
        获取Worker函数映射（用于启动ARQ Worker）
        
        Returns:
            函数名到函数的映射字典
        """
        # 这个方法在实际使用时需要注册所有可能的任务函数
        # 这里返回一个空字典，具体的函数注册在业务代码中完成
        return getattr(self.pool, '_registered_functions', {}) if self.pool else {}
    
    async def start_worker(self, functions: Dict[str, Callable] = None, **kwargs):
        """
        启动ARQ Worker（用于部署时）
        
        Args:
            functions: 要处理的函数映射
            **kwargs: 其他ARQ Worker参数
        """
        from arq import Worker
        
        await self._ensure_connection()
        
        # 合并函数
        all_functions = functions or {}
        if hasattr(self.pool, '_registered_functions'):
            all_functions.update(self.pool._registered_functions)
        
        # 创建Worker类
        class TaskWorker(Worker):
            redis_settings = self.redis_settings
            functions = list(all_functions.values())
            
            # Worker配置
            job_timeout = timedelta(seconds=self.job_timeout)
            keep_result = timedelta(seconds=self.keep_result)
        
        logger.info(f"Starting ARQ worker with {len(all_functions)} functions")
        worker = TaskWorker()
        await worker.main()