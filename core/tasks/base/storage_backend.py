'''
Description: 存储后端抽象接口: 定义任务状态存储的统一接口, 支持多种存储实现(MongoDB等)
Author: zyq
Date: 2025-08-28 09:55:01
LastEditors: zyq
LastEditTime: 2025-08-28 09:59:13
'''
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from ..models.task_models import BaseTask, BatchTask, TaskResult, TaskQuery, TaskStatus


class StorageBackend(ABC):
    """存储后端抽象基类"""
    
    @abstractmethod
    async def create_task(self, task: BaseTask) -> bool:
        """
        创建任务记录
        
        Args:
            task: 任务对象
            
        Returns:
            是否创建成功
        """
        pass
    
    @abstractmethod
    async def get_task(self, task_id: str) -> Optional[BaseTask]:
        """
        获取任务信息
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务对象，不存在返回None
        """
        pass
    
    @abstractmethod
    async def update_task_status(
        self, 
        task_id: str, 
        status: TaskStatus,
        **kwargs
    ) -> bool:
        """
        更新任务状态
        
        Args:
            task_id: 任务ID
            status: 新状态
            **kwargs: 其他要更新的字段
            
        Returns:
            是否更新成功
        """
        pass
    
    @abstractmethod
    async def update_task_progress(
        self, 
        task_id: str, 
        processed_items: int,
        successful_items: int = None,
        failed_items: int = None
    ) -> bool:
        """
        更新任务进度（针对批处理任务）
        
        Args:
            task_id: 任务ID
            processed_items: 已处理项目数
            successful_items: 成功项目数
            failed_items: 失败项目数
            
        Returns:
            是否更新成功
        """
        pass
    
    @abstractmethod
    async def add_sub_task_result(
        self, 
        task_id: str, 
        sub_task_id: str,
        status: TaskStatus,
        result: Any = None,
        error_message: str = None,
        processing_time: float = None
    ) -> bool:
        """
        添加子任务结果
        
        Args:
            task_id: 主任务ID
            sub_task_id: 子任务ID
            status: 子任务状态
            result: 子任务结果
            error_message: 错误消息
            processing_time: 处理时间
            
        Returns:
            是否添加成功
        """
        pass
    
    @abstractmethod
    async def save_task_result(
        self, 
        task_id: str, 
        result: TaskResult
    ) -> bool:
        """
        保存任务结果
        
        Args:
            task_id: 任务ID
            result: 任务结果
            
        Returns:
            是否保存成功
        """
        pass
    
    @abstractmethod
    async def query_tasks(self, query: TaskQuery) -> List[BaseTask]:
        """
        查询任务列表
        
        Args:
            query: 查询条件
            
        Returns:
            任务列表
        """
        pass
    
    @abstractmethod
    async def delete_task(self, task_id: str) -> bool:
        """
        删除任务记录
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否删除成功
        """
        pass
    
    @abstractmethod
    async def cleanup_expired_tasks(self, days: int = 30) -> int:
        """
        清理过期任务
        
        Args:
            days: 过期天数
            
        Returns:
            清理的任务数量
        """
        pass
    
    @abstractmethod
    async def get_task_statistics(
        self, 
        task_type: str = None, 
        days: int = 7
    ) -> Dict[str, Any]:
        """
        获取任务统计信息
        
        Args:
            task_type: 任务类型筛选
            days: 统计天数
            
        Returns:
            统计信息字典
        """
        pass