'''
Description: 
任务管理核心模块

提供统一的异步任务管理能力，支持：
- 批处理任务管理
- 任务状态持久化  
- 队列调度和监控
- 多种后端实现(ARQ/Celery)
- 多collection存储策略
Author: zyq
Date: 2025-08-28 10:50:40
LastEditors: zyq
LastEditTime: 2025-08-28 11:20:24
'''

from .models.task_models import (
    TaskStatus, TaskType, TaskPriority,
    BaseTask, BatchTask, SubTaskResult, TaskResult, TaskQuery,
    generate_task_id
)

from .base.queue_backend import QueueBackend
from .base.storage_backend import StorageBackend
from .base.task_manager import BaseTaskManager

from .backends.arq_backend import ARQTaskBackend
from .backends.mongo_task_storage import MongoTaskStorage
from .factory import TaskManagerFactory

__all__ = [
    # 数据模型
    'TaskStatus', 'TaskType', 'TaskPriority',
    'BaseTask', 'BatchTask', 'SubTaskResult', 'TaskResult', 'TaskQuery',
    'generate_task_id',
    
    # 抽象基类
    'QueueBackend', 'StorageBackend', 'BaseTaskManager',
    
    # 具体实现
    'ARQTaskBackend', 'MongoTaskStorage',
    
    # 工厂类
    'TaskManagerFactory'
]