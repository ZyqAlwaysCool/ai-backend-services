'''
Description: 
ARQ Worker管理器
负责在FastAPI应用中启动和管理ARQ Worker
Author: zyq
Date: 2025-08-28 10:58:22
LastEditors: zyq
LastEditTime: 2025-08-28 11:26:34
'''
import asyncio
import os
import signal
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager
from arq import Worker
from arq.connections import RedisSettings
from loguru import logger

from .backends.arq_backend import ARQTaskBackend
from .worker import process_task
from core.config.config_center import get_app_config


class WorkerManager:
    """ARQ Worker管理器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化Worker管理器
        
        Args:
            config: Worker配置
        """
        self.config = config or {}
        
        # 从统一配置中心获取Redis配置
        app_config = get_app_config()
        self.redis_settings = RedisSettings(
            host=app_config.redis_host,
            port=app_config.redis_port,
            database=app_config.redis_db,
            password=app_config.redis_password,
        )
        
        # Worker配置
        self.worker_config = {
            'queue_name': self.config.get('queue_name', 'arq:queue'),
            'max_jobs': self.config.get('max_jobs', 10),
            'job_timeout': self.config.get('job_timeout', 3600),
            'keep_result': self.config.get('keep_result', 86400),
            'health_check_interval': self.config.get('health_check_interval', 3600)
        }
        
        # Worker实例和控制
        self.worker: Optional[Worker] = None
        self.worker_task: Optional[asyncio.Task] = None
        self.running = False
        
        logger.info("Worker manager initialized")
    
    def create_worker(self) -> Worker:
        """
        创建配置好的Worker实例
        
        Returns:
            配置好的Worker实例
        """
        return Worker(
            functions=[process_task],
            queue_name=self.worker_config['queue_name'],
            redis_settings=self.redis_settings,
            max_jobs=self.worker_config['max_jobs'],
            job_timeout=self.worker_config['job_timeout'],
            keep_result=self.worker_config['keep_result'],
            handle_signals=False  # 让FastAPI处理信号，避免Ctrl+C被阻塞
        )
    
    async def start_worker(self) -> bool:
        """
        启动Worker
        
        Returns:
            是否启动成功
        """
        if self.running:
            logger.warning("Worker is already running")
            return True
        
        try:
            # 创建Worker实例
            self.worker = self.create_worker()
            
            # 创建Worker任务
            self.worker_task = asyncio.create_task(self._run_worker())
            self.running = True
            
            logger.info("ARQ Worker started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start Worker: {str(e)}")
            return False
    
    async def _run_worker(self):
        """Worker运行的内部方法"""
        try:
            logger.info("Starting ARQ Worker main loop...")
            await self.worker.main()
        except asyncio.CancelledError:
            logger.info("Worker task was cancelled")
            raise  # 重新抛出CancelledError以确保正确处理
        except Exception as e:
            logger.error(f"Worker encountered error: {str(e)}")
            # Worker异常退出，标记为非运行状态
            self.running = False
        finally:
            # 确保在任何情况下都标记为非运行状态
            self.running = False
    
    async def stop_worker(self) -> bool:
        """
        停止Worker
        
        Returns:
            是否停止成功
        """
        if not self.running:
            logger.warning("Worker is not running")
            return True
        
        try:
            logger.info("Stopping ARQ Worker...")
            
            # 取消Worker任务
            if self.worker_task and not self.worker_task.done():
                self.worker_task.cancel()
                
                try:
                    # 等待任务取消完成
                    await asyncio.wait_for(self.worker_task, timeout=10.0)
                except asyncio.TimeoutError:
                    logger.warning("Worker task cancellation timed out")
                except asyncio.CancelledError:
                    logger.info("Worker task cancelled successfully")
            
            # 关闭Worker
            if self.worker:
                try:
                    await self.worker.close()
                except Exception as e:
                    logger.warning(f"Error closing worker: {str(e)}")
                
                self.worker = None
            
            self.running = False
            self.worker_task = None
            
            logger.info("ARQ Worker stopped successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop Worker: {str(e)}")
            return False
    
    async def restart_worker(self) -> bool:
        """
        重启Worker
        
        Returns:
            是否重启成功
        """
        logger.info("Restarting ARQ Worker...")
        
        # 先停止
        stop_success = await self.stop_worker()
        if not stop_success:
            return False
        
        # 等待一点时间
        await asyncio.sleep(1)
        
        # 再启动
        return await self.start_worker()
    
    def is_running(self) -> bool:
        """检查Worker是否在运行"""
        return self.running and self.worker_task and not self.worker_task.done()
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Worker健康检查
        
        Returns:
            健康状态信息
        """
        status = {
            'worker_running': self.is_running(),
            'worker_config': self.worker_config,
            'redis_connected': False,
            'queue_accessible': False
        }
        
        if self.worker:
            try:
                # 检查Redis连接
                redis_pool = self.worker.pool
                if redis_pool:
                    await redis_pool.ping()
                    status['redis_connected'] = True
                    
                    # 检查队列访问
                    queue_key = f"{self.worker_config['queue_name']}"
                    await redis_pool.exists(queue_key)
                    status['queue_accessible'] = True
                    
            except Exception as e:
                logger.warning(f"Health check failed: {str(e)}")
        
        return status
    
    async def get_queue_stats(self) -> Dict[str, Any]:
        """
        获取队列统计信息
        
        Returns:
            队列统计信息
        """
        stats = {
            'queue_length': 0,
            'active_jobs': 0,
            'failed_jobs': 0,
            'completed_jobs': 0
        }
        
        if self.worker and self.worker.pool:
            try:
                redis_pool = self.worker.pool
                
                # 获取队列长度
                queue_key = f"{self.worker_config['queue_name']}"
                stats['queue_length'] = await redis_pool.llen(queue_key)
                
                # 这里可以添加更多统计信息的获取逻辑
                
            except Exception as e:
                logger.warning(f"Failed to get queue stats: {str(e)}")
        
        return stats


# 全局Worker管理器实例
_worker_manager: Optional[WorkerManager] = None


def get_worker_manager(config: Optional[Dict[str, Any]] = None) -> WorkerManager:
    """
    获取全局Worker管理器实例
    
    Args:
        config: Worker配置(仅在首次调用时生效)
        
    Returns:
        Worker管理器实例
    """
    global _worker_manager
    
    if _worker_manager is None:
        _worker_manager = WorkerManager(config)
    
    return _worker_manager


@asynccontextmanager
async def worker_lifespan():
    """
    Worker生命周期管理上下文
    可用于FastAPI的lifespan参数
    """
    worker_manager = get_worker_manager()
    
    # 启动Worker
    logger.info("Starting worker in lifespan context...")
    success = await worker_manager.start_worker()
    
    if not success:
        logger.error("Failed to start worker during startup")
    else:
        logger.info("Worker started successfully during startup")
    
    try:
        yield worker_manager
    finally:
        # 停止Worker
        logger.info("Stopping worker in lifespan context...")
        await worker_manager.stop_worker()
        logger.info("Worker stopped during shutdown")


def setup_signal_handlers(worker_manager: WorkerManager):
    """
    设置信号处理器，用于优雅地关闭Worker
    
    Args:
        worker_manager: Worker管理器实例
    """
    def signal_handler(signum, _):
        logger.info(f"Received signal {signum}, shutting down worker...")
        
        # 在事件循环中运行关闭逻辑
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(worker_manager.stop_worker())
            else:
                loop.run_until_complete(worker_manager.stop_worker())
        except Exception as e:
            logger.error(f"Error during signal handling: {str(e)}")
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)