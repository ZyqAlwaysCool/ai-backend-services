'''
Description: 队列后端抽象接口: 定义任务队列的统一接口, 支持多种队列实现(RQ、Celery等)
Author: zyq
Date: 2025-08-28 09:54:12
LastEditors: zyq
LastEditTime: 2025-09-18 16:34:23
'''
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Callable
from ..models.task_models import BaseTask, TaskResult, TaskStatus


class QueueBackend(ABC):
    """队列后端抽象基类"""
    
    @abstractmethod
    async def enqueue_task(
        self, 
        task: BaseTask, 
        func: Callable, 
        *args, 
        **kwargs
    ) -> str:
        """
        将任务加入队列
        
        Args:
            task: 任务对象
            func: 要执行的函数
            *args: 函数参数
            **kwargs: 函数关键字参数
            
        Returns:
            队列中的任务ID
        """
        pass
    
    @abstractmethod
    async def get_task_status(self, queue_task_id: str) -> Dict[str, Any]:
        """
        获取队列中任务的执行状态
        
        Args:
            queue_task_id: 队列任务ID
            
        Returns:
            任务执行状态信息字典
        """
        pass
    
    @abstractmethod
    async def get_task_result(self, queue_task_id: str) -> Optional[TaskResult]:
        """
        获取任务执行结果
        
        Args:
            queue_task_id: 队列任务ID
            
        Returns:
            任务结果,未完成返回None
        """
        pass
    
    @abstractmethod
    async def cancel_task(self, queue_task_id: str) -> bool:
        """
        取消任务执行
        
        Args:
            queue_task_id: 队列任务ID
            
        Returns:
            是否成功取消
        """
        pass
    
    @abstractmethod
    async def get_queue_length(self, queue_name: str = "default") -> int:
        """
        获取队列长度
        
        Args:
            queue_name: 队列名称
            
        Returns:
            队列中等待的任务数量
        """
        pass
    
    @abstractmethod
    async def get_failed_tasks(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取失败的任务列表
        
        Args:
            limit: 限制返回数量
            
        Returns:
            失败任务列表
        """
        pass
    
    @abstractmethod
    async def retry_failed_task(self, queue_task_id: str) -> bool:
        """
        重试失败的任务
        
        Args:
            queue_task_id: 队列任务ID
            
        Returns:
            是否成功重试
        """
        pass
    
    @abstractmethod
    async def clear_failed_tasks(self) -> int:
        """
        清理失败任务
        
        Returns:
            清理的任务数量
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        队列健康检查
        
        Returns:
            队列是否正常
        """
        pass