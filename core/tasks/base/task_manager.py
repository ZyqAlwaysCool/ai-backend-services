'''
Description: 任务管理器抽象基类: 提供统一的任务管理接口，整合队列和存储后端
Author: zyq
Date: 2025-08-28 09:56:12
LastEditors: zyq
LastEditTime: 2025-08-28 11:17:28
'''

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from loguru import logger

from .queue_backend import QueueBackend
from .storage_backend import StorageBackend
from ..models.task_models import (
    BaseTask, BatchTask, TaskResult, TaskQuery, TaskStatus, 
    TaskType, generate_task_id
)


class BaseTaskManager(ABC):
    """任务管理器抽象基类"""
    
    def __init__(
        self, 
        queue_backend: QueueBackend,
        storage_backend: StorageBackend,
        config: Dict[str, Any] = None
    ):
        """
        初始化任务管理器
        
        Args:
            queue_backend: 队列后端
            storage_backend: 存储后端
            config: 配置参数
        """
        self.queue_backend = queue_backend
        self.storage_backend = storage_backend
        self.config = config or {}
        
        # 默认配置
        self.default_timeout = self.config.get('default_timeout', 3600)
        self.default_max_retries = self.config.get('default_max_retries', 3)
        self.default_queue_name = self.config.get('default_queue_name', 'default_queue')
    
    @abstractmethod
    def get_task_type(self) -> TaskType:
        """获取任务类型"""
        pass
    
    @abstractmethod
    async def create_task_instance(self, **kwargs) -> BaseTask:
        """
        创建任务实例（由具体管理器实现）
        
        Args:
            **kwargs: 任务创建参数
            
        Returns:
            任务实例
        """
        pass
    
    async def submit_task(
        self, 
        task_func: Callable,
        task_params: Dict[str, Any],
        **kwargs
    ) -> str:
        """
        提交任务到队列
        
        Args:
            task_func: 任务执行函数
            task_params: 任务参数
            **kwargs: 其他任务配置
            
        Returns:
            任务ID
        """
        try:
            # 创建任务实例
            task = await self.create_task_instance(**task_params, **kwargs)
            
            # 保存任务到存储后端
            await self.storage_backend.create_task(task)
            logger.info(f"Task created in storage: {task.task_id}")
            
            # 提交任务到队列
            queue_task_id = await self.queue_backend.enqueue_task(
                task, task_func, **task_params
            )
            
            # 更新任务状态
            await self.storage_backend.update_task_status(
                task.task_id, 
                TaskStatus.PENDING,
                queue_task_id=queue_task_id
            )
            
            logger.info(f"Task submitted to queue: {task.task_id} -> {queue_task_id}")
            return task.task_id
            
        except Exception as e:
            logger.error(f"Failed to submit task: {str(e)}")
            raise
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务状态信息
        """
        try:
            task = await self.storage_backend.get_task(task_id)
            if not task:
                return None
            
            # 获取队列中的状态（如果有队列任务ID）
            queue_status = None
            if hasattr(task, 'queue_task_id') and task.queue_task_id:
                try:
                    queue_status = await self.queue_backend.get_task_status(
                        task.queue_task_id
                    )
                except Exception as e:
                    logger.warning(f"Failed to get queue status: {str(e)}")
            
            return {
                'task_id': task.task_id,
                'status': task.status,
                'queue_status': queue_status,
                'created_at': task.created_at,
                'started_at': task.started_at,
                'completed_at': task.completed_at,
                'progress': getattr(task, 'progress', None),
                'error_message': task.error_message
            }
            
        except Exception as e:
            logger.error(f"Failed to get task status: {str(e)}")
            return None
    
    async def get_task_result(self, task_id: str) -> Optional[TaskResult]:
        """
        获取任务结果
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务结果
        """
        try:
            task = await self.storage_backend.get_task(task_id)
            if not task or task.status != TaskStatus.COMPLETED:
                return None
            
            # 尝试从队列获取结果（如果有队列任务ID）
            queue_result = None
            if hasattr(task, 'queue_task_id') and task.queue_task_id:
                try:
                    queue_result = await self.queue_backend.get_task_result(
                        task.queue_task_id
                    )
                except Exception as e:
                    logger.warning(f"Failed to get queue result: {str(e)}")
            
            # 构建结果对象
            result = TaskResult(
                task_id=task.task_id,
                status=task.status,
                result_data=queue_result.result_data if queue_result else None,
                metadata=queue_result.metadata if queue_result else {},
                execution_time=queue_result.execution_time if queue_result else None,
                created_at=task.completed_at or task.created_at
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get task result: {str(e)}")
            return None
    
    async def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否成功取消
        """
        try:
            task = await self.storage_backend.get_task(task_id)
            if not task:
                return False
            
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                logger.warning(f"Cannot cancel task in status: {task.status}")
                return False
            
            # 取消队列中的任务
            queue_cancelled = True
            if hasattr(task, 'queue_task_id') and task.queue_task_id:
                queue_cancelled = await self.queue_backend.cancel_task(task.queue_task_id)
            
            # 更新存储中的状态
            storage_updated = await self.storage_backend.update_task_status(
                task_id, TaskStatus.CANCELLED
            )
            
            success = queue_cancelled and storage_updated
            if success:
                logger.info(f"Task cancelled successfully: {task_id}")
            else:
                logger.warning(f"Task cancellation partially failed: {task_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to cancel task: {str(e)}")
            return False
    
    async def query_tasks(self, query: TaskQuery) -> List[Dict[str, Any]]:
        """
        查询任务列表
        
        Args:
            query: 查询条件
            
        Returns:
            任务信息列表
        """
        try:
            tasks = await self.storage_backend.query_tasks(query)
            
            result = []
            for task in tasks:
                task_info = {
                    'task_id': task.task_id,
                    'task_type': task.task_type,
                    'status': task.status,
                    'created_at': task.created_at,
                    'started_at': task.started_at,
                    'completed_at': task.completed_at,
                    'error_message': task.error_message
                }
                
                # 添加批处理任务特有信息
                if isinstance(task, BatchTask):
                    task_info.update({
                        'total_items': task.total_items,
                        'processed_items': task.processed_items,
                        'progress': task.progress,
                        'success_rate': task.success_rate
                    })
                
                result.append(task_info)
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to query tasks: {str(e)}")
            return []
    
    async def health_check(self) -> Dict[str, bool]:
        """
        健康检查
        
        Returns:
            各组件健康状态
        """
        result = {
            'queue': False,
            'storage': False,
            'overall': False
        }
        
        try:
            # 检查队列后端
            result['queue'] = await self.queue_backend.health_check()
        except Exception as e:
            logger.error(f"Queue health check failed: {str(e)}")
        
        try:
            # 检查存储后端(简单的查询测试)
            test_query = TaskQuery(limit=1)
            await self.storage_backend.query_tasks(test_query)
            result['storage'] = True
        except Exception as e:
            logger.error(f"Storage health check failed: {str(e)}")
        
        result['overall'] = result['queue'] and result['storage']
        return result