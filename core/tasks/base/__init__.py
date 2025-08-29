"""任务管理抽象基类"""

from .queue_backend import QueueBackend
from .storage_backend import StorageBackend
from .task_manager import BaseTaskManager

__all__ = ['QueueBackend', 'StorageBackend', 'BaseTaskManager']