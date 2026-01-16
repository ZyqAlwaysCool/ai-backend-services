'''
Description: MCP client
Author: zyq
Date: 2025-12-18 10:45:00
LastEditors: zyq
LastEditTime: 2025-12-23 09:13:55
'''

from typing import List, Dict, Any, Optional
from loguru import logger
import mcp.types as types
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from core.exceptions import BaseBusinessException
from core.config.error_codes import COMMON_ERROR_REQUEST_PARSE_ERROR


class MCPClient:
    """简化的MCP客户端，用于拉取工具信息与调用工具"""

    def __init__(self):
        self._mcp_api_key = None
        self._mcp_base_url = None
        self._api_key_header = "X-API-Key"
    
    def set_mcp_base_info(self, mcp_host: str, mcp_port: str, mcp_api_key: str, api_key_header: str = "X-API-Key"):
        """注入MCP服务器基础信息"""
        self._mcp_base_url = f"http://{mcp_host}:{mcp_port}/sse"
        self._mcp_api_key = mcp_api_key
        self._api_key_header = api_key_header or "X-API-Key"

    def _ensure_ready(self):
        if self._mcp_api_key is None or self._mcp_base_url is None:
            raise BaseBusinessException(code=COMMON_ERROR_REQUEST_PARSE_ERROR, message="检查mcp服务器配置和apikey信息")

    async def list_tools(self) -> List[Dict[str, Any]]:
        """列出服务器提供的工具信息"""
        self._ensure_ready()
        headers = {self._api_key_header: self._mcp_api_key}
        async with sse_client(self._mcp_base_url, headers=headers) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                init_result = await session.initialize()
                logger.info(f"MCP服务器连接成功 server=({init_result.serverInfo.name}) version=({init_result.serverInfo.version})")
                tools = []

                async def _collect_page(cursor: Optional[str]):
                    return await session.list_tools(cursor=cursor)

                cursor = None
                while True:
                    result: types.ListToolsResult = await _collect_page(cursor)
                    for tool in result.tools:
                        tools.append({
                            "tool_name": tool.name,
                            "description": tool.description or "",
                            "input_schema": tool.inputSchema if tool.inputSchema else {}
                        })
                    cursor = result.nextCursor
                    if cursor is None:
                        break
                return tools

    async def call_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """调用指定工具"""
        self._ensure_ready()
        headers = {self._api_key_header: self._mcp_api_key}
        async with sse_client(self._mcp_base_url, headers=headers) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, args)
                return result.model_dump()
