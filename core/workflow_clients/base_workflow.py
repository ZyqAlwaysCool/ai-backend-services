'''
Description: 工作流客户端基础接口和抽象类
Author: zyq
Date: 2025-08-13 14:50:00
LastEditors: zyq
LastEditTime: 2025-11-18 15:47:44
'''
from typing import Dict, Any, Optional, AsyncGenerator, Union
from enum import Enum
from pydantic import BaseModel, Field
import httpx
from loguru import logger



class WorkflowType(str, Enum):
    """工作流类型枚举"""
    DIFY = "dify"
    COZE = "coze"
    CUSTOM = "custom"


class WorkflowStatus(str, Enum):
    """工作流执行状态"""
    PENDING = "pending"
    RUNNING = "running" 
    SUCCEED = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowResponse(BaseModel):
    status: WorkflowStatus = Field(default=WorkflowStatus.SUCCEED)
    message: str = Field(default="")
    data: Union[str, Dict[str, Any], None] = Field(default="")
    conversation_id: str = Field(default="")
    
    @classmethod
    def success(cls, data: Union[str, Dict[str, Any]], conv_id: str=""):
        return cls(data=data, conversation_id=conv_id)
    
    @classmethod
    def error(cls, msg: str):
        return cls(status=WorkflowStatus.FAILED, message=msg)


class BaseWorkflowClient:
    """工作流客户端基类"""
    
    def __init__(self, workflow_name: str, workflow_type: WorkflowType, timeout: int, **kwargs):
        self.workflow_name = workflow_name
        self.workflow_type = workflow_type
        self.metadata = kwargs
        # 请求参数设置
        self.sync_req_timeout = timeout
        self.async_req_timeout = httpx.Timeout(2 * timeout, read=timeout)
    
    async def execute_workflow(
        self, 
        inputs: Dict[str, Any], 
        trace_id: Optional[str] = None,
        **kwargs
    ) -> WorkflowResponse:
        """执行工作流（异步）- 默认实现"""
        raise NotImplementedError("子类需要实现此方法")
    
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
    
    def _sync_request(self, 
                       url: str, 
                       method: str, 
                       headers: Optional[Dict[str, str]]=None, 
                       params: Optional[Dict[str, Any]]=None, 
                       json: Any=None, 
                       data: Any=None, 
                       files: Any=None) -> httpx.Response:
        """通用同步http请求封装"""
        logger.info(f"start sync request. url=({url}) headers=({headers}) method=({method}) params=({params}) data=({data}) json=({json})")
        with httpx.Client(timeout=self.sync_req_timeout) as client:
            response = client.request(method.upper(), url, headers=headers, params=params, json=json, data=data, files=files)
            response.raise_for_status()
            return response
    
    async def _async_request(
        self,
        url: str,
        method: str = "POST",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        stream: bool = False,
        **client_kwargs: Any,
    ) -> httpx.Response:
        """
        通用异步HTTP请求。
        返回原始 httpx.Response，由调用者自行处理（.json() / .text / .iter_bytes() …）。
        任何网络异常都会直接抛出，方便调用者捕获后决定重试或降级。
        """
        logger.info(f"start async request. workflow_name=({self.workflow_name}) url=({url}) method=({method}) params=({params})")
        async with httpx.AsyncClient(timeout=self.async_req_timeout, limits=httpx.Limits(max_connections=None)) as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                headers=headers,
                json=data if files is None else None,  # 传 json 时不能同时传 files
                data=data if files is not None else None,
                files=files,
                params=params,
            )
            response.raise_for_status()
            if not stream:
                await response.aread()  # 一次性读完整 body

            # 对于204 NO CONTENT状态码，避免JSON解析错误
            if response.status_code == 204:
                logger.info("end async request. response=HTTP 204 No Content")
            else:
                logger.info(f"end async request. response=({response.json()})")
            return response