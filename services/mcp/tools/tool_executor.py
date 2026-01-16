'''
Description: 工具执行器
Author: zyq
Date: 2025-12-24 10:15:00
LastEditors: zyq
LastEditTime: 2025-12-24 10:15:00
'''
import asyncio
import os
from typing import Dict, Any
from loguru import logger
import time

from .mcp_client import MCPClient
from core.exceptions import BaseBusinessException
from core.config.error_codes import COMMON_ERROR_REQUEST_PARSE_ERROR


class ToolExecutor:
    """封装单个工具的调用"""

    def __init__(self, tool: Dict[str, Any], server_cfg: Dict[str, Any]):
        self.tool = tool
        self.tool_name = tool.get("tool_name")
        self.tool_meta = tool.get("meta", {}) or {}
        self.server_cfg = server_cfg or {}
        self.client = MCPClient()
        self._init_client()

    def _init_client(self):
        """根据工具元信息和配置初始化MCP客户端"""
        host = self.tool_meta.get("mcp_server_host")
        port = self.tool_meta.get("mcp_server_port")
        api_key = self.tool_meta.get("mcp_server_apikey") or self.tool_meta.get("api_key")

        host_env = self.server_cfg.get("host_env")
        port_env = self.server_cfg.get("port_env")
        default_host = self.server_cfg.get("default_host")
        default_port = self.server_cfg.get("default_port")
        api_key_header = self.server_cfg.get("api_key_header", "X-API-Key")

        if not host:
            host = os.getenv(host_env) if host_env else None
        if not host:
            host = default_host
        if not port:
            port = os.getenv(port_env) if port_env else None
        if not port:
            port = default_port
        if not api_key:
            api_key = self.tool.get("api_key") or self.tool_meta.get("api_key") or os.getenv("MCP_SERVER_API_KEY")

        if not host or not port or not api_key:
            raise BaseBusinessException(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                message="MCP服务器配置缺失，请检查工具元数据或服务配置"
            )
        self.client.set_mcp_base_info(str(host), str(port), api_key, api_key_header=api_key_header)

    async def call(self, args: Dict[str, Any], timeout_ms: int | None = None) -> Dict[str, Any]:
        """调用MCP工具"""
        start = time.time()
        if timeout_ms:
            result = await asyncio.wait_for(
                self.client.call_tool(self.tool_name, args),
                timeout=timeout_ms / 1000
            )
        else:
            result = await self.client.call_tool(self.tool_name, args)
        latency = int((time.time() - start) * 1000)
        logger.info(f"MCP工具调用完成 tool=({self.tool_name}) latency_ms=({latency})")
        return {"result": result, "latency_ms": latency}
