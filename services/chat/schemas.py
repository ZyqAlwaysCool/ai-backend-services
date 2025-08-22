'''
Description: Chat服务数据模型
Author: zyq
Date: 2025-01-21
'''
from typing import List, Optional, Dict, Any
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


class SingleTurnChatRequest(BaseModel):
    """单轮对话请求模型"""
    query: str = Field(..., description="用户问题", min_length=1)
    model: str = Field("qwen3-32B", description="使用的模型名称")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    temperature: Optional[float] = Field(0.7, description="温度参数", ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(2000, description="最大生成token数", ge=1, le=8000)


class MultiTurnChatRequest(BaseModel):
    """多轮对话请求模型"""
    query: str = Field(..., description="当前用户问题", min_length=1)
    history: List[ChatMessage] = Field(default=[], description="历史对话记录")
    model: str = Field("qwen3-32B", description="使用的模型名称")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    temperature: Optional[float] = Field(0.7, description="温度参数", ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(2000, description="最大生成token数", ge=1, le=8000)


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