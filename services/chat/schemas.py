'''
Description: Chat服务数据模型
Author: zyq
Date: 2025-08-26 11:18:33
LastEditors: zyq
LastEditTime: 2025-11-05 17:48:39
'''
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class MessageRole(str, Enum):
    """消息角色枚举"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    """聊天消息模型"""
    role: MessageRole = Field(..., description="消息角色")
    content: str = Field(..., description="消息内容", min_length=1)
    
    class Config:
        use_enum_values = True


class ChatRequest(BaseModel):
    """对话请求模型（统一单轮/多轮）"""
    query: str = Field(..., description="当前用户问题", min_length=1)
    history: List[ChatMessage] = Field(default=[], description="历史对话记录（为空则为单轮对话）")
    model: str = Field("qwen3-32B", description="使用的模型名称")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    temperature: Optional[float] = Field(0.7, description="温度参数")
    max_tokens: Optional[int] = Field(2000, description="最大生成token数")


class ChatResponse(BaseModel):
    """对话响应模型"""
    answer: str = Field(..., description="AI回复内容")
    model: str = Field(..., description="使用的模型")
    usage: Dict[str, int] = Field(..., description="Token使用统计")
    finish_reason: str = Field(..., description="完成原因")


class StreamChatChunk(BaseModel):
    """流式对话数据块"""
    content: str = Field(..., description="增量内容")
    finish_reason: Optional[str] = Field(None, description="完成原因")
    model: str = Field(..., description="使用的模型")


class ChatServiceStatus(BaseModel):
    """Chat服务状态模型"""
    service_name: str = Field(..., description="服务名称")
    version: str = Field(..., description="服务版本")
    status: str = Field(..., description="服务状态")
    enabled_endpoints: List[str] = Field(..., description="启用的端点列表")
    available_models: List[str] = Field(..., description="可用模型列表")
    

# ========================工作流/对话流相关接口适配========================
class ChatFlowPlatform(str, Enum):
    """对话流平台"""
    DIFY = "dify"
    COZE = "coze"

class ApiKeyStatus(str, Enum):
    """API Key状态枚举"""
    ACTIVE = "active"
    DISABLED = "disabled"

class AddChatFlowApiKeyRequest(BaseModel):
    """添加对话流API key请求模型"""
    api_key: str = Field(..., description="对话流API key", min_length=1)
    chatflow_name: str = Field(..., description="对话流名称", min_length=1)
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="对话流平台")
    description: Optional[str] = Field(None, description="备注说明")

class AddChatFlowApiKeyResponse(BaseModel):
    """添加对话流API key响应模型"""
    key_id: str = Field(..., description="API key记录ID")

class ChatFlowApiKeyInfo(BaseModel):
    """对话流API key信息模型"""
    key_id: str = Field(..., description="记录ID")
    user_id: str = Field(..., description="所属用户ID")
    chatflow_name: str = Field(..., description="对话流名称")
    platform: ChatFlowPlatform = Field(default=ChatFlowPlatform.DIFY, description="对话流平台")
    api_key: str = Field(..., description="实际的API key")
    description: Optional[str] = Field(None, description="备注说明")
    status: ApiKeyStatus = Field(default=ApiKeyStatus.ACTIVE, description="状态")
    created_at: datetime = Field(default=datetime.utcnow, description="创建时间")

class GetChatFlowApiKeyResponse(BaseModel):
    """查询对话流API key响应模型"""
    api_keys_info: List[ChatFlowApiKeyInfo] = Field(default=[], description="对话流API key信息列表")

class ChatFlowResponseMode(str, Enum):
    """对话流响应模式枚举"""
    BLOCK = "block"
    STREAM = "stream"

# ========================兼容dify的数据模型========================
class DifyChatFlowFileTransferMethod(str, Enum):
    """Dify对话流文件传输方式枚举"""
    LOCAL_FILE = "local_file"
    URL = "remote_url"

class DifyResponseMode(str, Enum):
    """Dify响应模式枚举"""
    BLOCK = "blocking"
    STREAM = "streaming"

class DifyChatFlowFileInfo(BaseModel):
    """对话流文件信息模型"""
    transfor_method: DifyChatFlowFileTransferMethod = Field(DifyChatFlowFileTransferMethod.LOCAL_FILE, description="文件传输方式")
    type: str = Field(..., description="文件类型")
    upload_file_id: Optional[str] = Field(None, description="上传的文件id, 仅当传输方式为local_file时填入")
    url: Optional[str] = Field(None, description="文件url, 仅当传输方式为remote_url时填入")
    

# class DifyChatFlowRequest(BaseModel):
#     """dify对话流请求模型, 不对外"""
#     query: str = Field(..., description="用户的问题", min_length=1)
#     chatflow_name: str = Field(..., description="对话流名称", min_length=1)
#     inputs: dict = Field(default={}, description="输入参数")
#     response_mode: DifyResponseMode = Field(DifyResponseMode.STREAM, description="响应模式, 默认流式")
#     files: Optional[List[DifyChatFlowFileInfo]] = Field(None, description="上传的文件列表")

# ========================兼容dify数据模型========================

class UploadFileInfo(BaseModel):
    """上传文件信息模型"""
    file_name: str = Field(..., description="文件名称")
    file_id: str = Field(..., description="文件ID")

class ChatFlowRequest(BaseModel):
    """对话流请求模型(统一dify/coze)"""
    query: str = Field(..., description="用户的问题", min_length=1)
    chatflow_name: str = Field(..., description="对话流名称", min_length=1)
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="对话流平台")
    platform_user: str = Field(default="test_user_1", description="平台用户标识")
    inputs: dict = Field(default={}, description="输入参数")
    response_mode: ChatFlowResponseMode = Field(ChatFlowResponseMode.STREAM, description="响应模式, 默认流式")
    files: Optional[List[UploadFileInfo]] = Field(None, description="上传的文件列表")

class UploadFilesToChatFlowPlatformRequest(BaseModel):
    """上传文件到对话流平台请求模型"""
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="对话流平台")
    user: str = Field(..., description="用户标识")
    chatflow_name: str = Field(..., description="对话流名称", min_length=1)

class UploadFilesToChatFlowPlatformResponse(BaseModel):
    """上传文件到对话流平台响应模型"""
    file_info_list: List[Dict] = Field([], description="文件ID列表")

class StopChatTaskRequest(BaseModel):
    """停止对话任务请求模型"""
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="对话流平台")
    task_id: str = Field(..., description="任务ID")
    user: str = Field(..., description="用户标识")

# ========================工作流/对话流相关接口适配========================