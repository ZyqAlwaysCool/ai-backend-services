'''
Description: MCP服务Schema定义
Author: zyq
Date: 2025-12-24 10:05:00
LastEditors: zyq
LastEditTime: 2025-12-19 08:48:58
'''
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator


class AgentMode(str, Enum):
    """编排模式"""
    SINGLE_TOOL = "single_tool"
    PLAN_REACT = "plan_react"
    SUPERVISOR = "supervisor"


class SyncMCPToolRequest(BaseModel):
    """同步MCP工具请求"""
    mcp_server_host: str = Field(..., description="MCP服务器host", min_length=1)
    mcp_server_port: str = Field(..., description="MCP服务器port", min_length=1)
    mcp_server_apikey: str = Field(..., description="MCP服务apikey", min_length=1)


class SyncToolMetaRequest(BaseModel):
    """同步工具元数据请求"""
    tool_names: Optional[List[str]] = Field(default=None, description="需要同步的工具列表，空则同步已注册全部")


class ListToolsResponse(BaseModel):
    """工具列表响应"""
    tools: List[Dict[str, Any]]


class AskRequest(BaseModel):
    """提问请求"""
    query: str = Field(..., description="用户问题", min_length=1)
    prompt: str = Field(..., description="提示词", min_length=1)
    tool_names: List[str] = Field(..., description="本次可用工具名称列表", min_items=1)
    agent_mode: AgentMode = Field(AgentMode.SINGLE_TOOL, description="编排模式")
    stream: bool = Field(True, description="是否流式返回")

    @field_validator("tool_names")
    def validate_tool_names(cls, v: List[str]) -> List[str]:
        names = [name.strip() for name in v if name.strip()]
        if not names:
            raise ValueError("工具列表不能为空")
        return names


class McpStreamChunk(BaseModel):
    """流式事件块"""
    type: str = Field(..., description="事件类型")
    trace_id: str = Field(..., description="链路ID")
    agent_mode: str = Field(..., description="编排模式")
    ts: int = Field(..., description="时间戳(毫秒)")
    content: Optional[str] = Field(None, description="文本增量或最终内容")
    model: Optional[str] = Field(None, description="模型名称")
    tool_name: Optional[str] = Field(None, description="工具名称")
    step: Optional[int] = Field(None, description="步骤编号")
    input: Optional[str] = Field(None, description="工具输入")
    output: Optional[str] = Field(None, description="工具输出")
    latency_ms: Optional[int] = Field(None, description="耗时")
    status: Optional[str] = Field(None, description="状态")
    detail: Optional[Dict[str, Any]] = Field(None, description="其他信息")
