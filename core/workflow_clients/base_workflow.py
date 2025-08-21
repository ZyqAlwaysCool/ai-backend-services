'''
Description: 工作流客户端基础接口和抽象类
Author: zyq
Date: 2025-08-13 14:50:00
LastEditors: zyq
LastEditTime: 2025-08-13 14:50:00
'''
from typing import Dict, Any, Optional, AsyncGenerator
from enum import Enum
from pydantic import BaseModel, Field


class WorkflowType(str, Enum):
    """工作流类型枚举"""
    DIFY = "dify"
    LANGGRAPH = "langgraph"
    CUSTOM = "custom"


class WorkflowStatus(str, Enum):
    """工作流执行状态"""
    PENDING = "pending"
    RUNNING = "running" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowResponse(BaseModel):
    """统一的工作流响应模型"""
    status: WorkflowStatus = Field(..., description="执行状态")
    message: str = Field("", description="响应消息")
    data: Optional[Dict[str, Any]] = Field(None, description="响应数据")
    conversation_id: Optional[str] = Field(None, description="会话ID")
    task_id: Optional[str] = Field(None, description="任务ID")
    trace_id: Optional[str] = Field(None, description="追踪ID")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据信息")
    
    @classmethod
    def success(cls, data: Dict[str, Any], **kwargs):
        """创建成功响应"""
        return cls(status=WorkflowStatus.COMPLETED, data=data, **kwargs)
    
    @classmethod
    def error(cls, message: str, **kwargs):
        """创建错误响应"""
        return cls(status=WorkflowStatus.FAILED, message=message, **kwargs)
    
    @classmethod
    def running(cls, message: str = "工作流执行中", **kwargs):
        """创建执行中响应"""
        return cls(status=WorkflowStatus.RUNNING, message=message, **kwargs)


class BaseWorkflowClient:
    """工作流客户端基类"""
    
    def __init__(self, workflow_name: str, workflow_type: WorkflowType, **kwargs):
        self.workflow_name = workflow_name
        self.workflow_type = workflow_type
        self.metadata = kwargs
    
    async def execute_workflow(
        self, 
        inputs: Dict[str, Any], 
        trace_id: Optional[str] = None,
        **kwargs
    ) -> WorkflowResponse:
        """执行工作流（异步）- 默认实现"""
        raise NotImplementedError("子类需要实现此方法")
    
    async def stream_workflow(
        self, 
        inputs: Dict[str, Any], 
        trace_id: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[WorkflowResponse, None]:
        """流式执行工作流 - 默认实现"""
        # 提供默认实现，避免抽象方法错误
        raise NotImplementedError("子类需要实现此方法")
        yield  # 这行不会执行，只是为了满足AsyncGenerator类型
    
    async def get_status(self, task_id: str) -> WorkflowResponse:
        """获取工作流执行状态 - 默认实现"""
        return WorkflowResponse.error("方法未实现")
    
    async def cancel_workflow(self, task_id: str) -> WorkflowResponse:
        """取消工作流执行 - 默认实现"""
        return WorkflowResponse.error("方法未实现")
    
    async def upload_file(self, file_path: str, **kwargs) -> WorkflowResponse:
        """上传文件到工作流 - 默认实现"""
        return WorkflowResponse.error("方法未实现")
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 子类可以重写此方法实现特定的健康检查逻辑
            return True
        except Exception:
            return False
    
    def get_metadata(self) -> Dict[str, Any]:
        """获取客户端元数据"""
        return {
            "workflow_name": self.workflow_name,
            "workflow_type": self.workflow_type.value,
            **self.metadata
        }