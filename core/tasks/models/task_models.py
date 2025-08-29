'''
Description: 通用任务数据模型定义: 提供业务无关的任务管理基础数据结构
Author: zyq
Date: 2025-08-28 09:53:06
LastEditors: zyq
LastEditTime: 2025-08-28 10:15:45
'''
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
import uuid


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    """任务类型枚举"""
    BATCH_PROCESSING = "batch_processing"
    SINGLE_PROCESSING = "single_processing"
    SCHEDULED = "scheduled"


class TaskPriority(int, Enum):
    """任务优先级枚举"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


class BaseTask(BaseModel):
    """基础任务模型"""
    task_id: str = Field(..., description="任务唯一标识")
    task_type: TaskType = Field(..., description="任务类型")
    status: TaskStatus = Field(TaskStatus.PENDING, description="任务状态")
    priority: TaskPriority = Field(TaskPriority.NORMAL, description="任务优先级")
    
    # 时间字段
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    started_at: Optional[datetime] = Field(None, description="开始执行时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    
    # 任务配置
    timeout: int = Field(3600, description="任务超时时间(秒)")
    retry_count: int = Field(0, description="重试次数")
    max_retries: int = Field(3, description="最大重试次数")
    
    # 错误信息
    error_message: Optional[str] = Field(None, description="错误消息")
    error_details: Optional[Dict[str, Any]] = Field(None, description="错误详情")
    
    # 执行环境
    worker_id: Optional[str] = Field(None, description="执行worker标识")
    trace_id: Optional[str] = Field(None, description="链路追踪ID")
    
    class Config:
        use_enum_values = True


class SubTaskResult(BaseModel):
    """子任务结果模型"""
    sub_task_id: str = Field(..., description="子任务ID")
    status: TaskStatus = Field(..., description="子任务状态")
    result: Optional[Any] = Field(None, description="子任务结果")
    error_message: Optional[str] = Field(None, description="错误消息")
    processing_time: Optional[float] = Field(None, description="处理时间(秒)")
    
    class Config:
        use_enum_values = True


class BatchTask(BaseTask):
    """批处理任务模型"""
    total_items: int = Field(..., description="总项目数", ge=1)
    processed_items: int = Field(0, description="已处理项目数", ge=0)
    successful_items: int = Field(0, description="成功项目数", ge=0)
    failed_items: int = Field(0, description="失败项目数", ge=0)
    
    # 子任务结果
    sub_results: List[SubTaskResult] = Field(default_factory=list, description="子任务结果列表")
    
    # 批处理特有配置
    batch_size: int = Field(1, description="批处理大小", ge=1)
    parallel_processing: bool = Field(False, description="是否并行处理")
    
    @property
    def progress(self) -> float:
        """计算处理进度百分比"""
        if self.total_items == 0:
            return 0.0
        return (self.processed_items / self.total_items) * 100
    
    @property
    def success_rate(self) -> float:
        """计算成功率"""
        if self.processed_items == 0:
            return 0.0
        return (self.successful_items / self.processed_items) * 100


class TaskResult(BaseModel):
    """任务结果模型"""
    task_id: str = Field(..., description="任务ID")
    status: TaskStatus = Field(..., description="任务状态")
    result_data: Optional[Any] = Field(None, description="结果数据")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="结果元数据")
    
    # 执行统计
    execution_time: Optional[float] = Field(None, description="执行时间(秒)")
    memory_usage: Optional[int] = Field(None, description="内存使用(MB)")
    
    # 时间信息
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    
    class Config:
        use_enum_values = True


class TaskQuery(BaseModel):
    """任务查询模型"""
    task_id: Optional[str] = Field(None, description="任务ID")
    task_type: Optional[TaskType] = Field(None, description="任务类型")
    status: Optional[TaskStatus] = Field(None, description="任务状态")
    created_after: Optional[datetime] = Field(None, description="创建时间起始")
    created_before: Optional[datetime] = Field(None, description="创建时间结束")
    limit: int = Field(10, description="查询限制", ge=1, le=100)
    offset: int = Field(0, description="查询偏移", ge=0)
    
    class Config:
        use_enum_values = True


def generate_task_id(prefix: str = "task") -> str:
    """生成任务ID"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    uuid_short = str(uuid.uuid4())[:8]
    return f"{prefix}_{timestamp}_{uuid_short}"