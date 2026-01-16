'''
Description: 工具元数据提供器
Author: zyq
Date: 2025-12-24 10:14:00
LastEditors: zyq
LastEditTime: 2025-12-18 17:48:08
'''
from typing import Dict, Any, List
from loguru import logger

from .mcp_client import MCPClient


class ToolMetaProvider:
    """通过MCP客户端拉取工具元数据"""

    def __init__(self):
        self.client = MCPClient()

    async def fetch_meta_batch(self) -> List[Dict[str, Any]]:
        """批量拉取工具信息，返回名称到元数据映射"""
        mcp_tools_info = await self.client.list_tools()
        logger.info(f"工具元数据同步完成 count={len(mcp_tools_info)}")
        return mcp_tools_info
    
    def set_mcp_client(self, mcp_host: str, mcp_port: str, mcp_api_key: str) -> None:
        self.client.set_mcp_base_info(mcp_host, mcp_port, mcp_api_key)
