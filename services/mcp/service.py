'''
Description: MCP服务主类
Author: zyq
Date: 2025-12-24 10:23:00
LastEditors: zyq
LastEditTime: 2025-12-24 10:23:00
'''
from typing import Dict, Any
from fastapi import APIRouter
from loguru import logger

from services.base import BaseService
from services.mcp.handlers import MCPHandlers
from services.mcp.routers import mcp_router


class McpService(BaseService):
    """MCP服务主类"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.handlers = None

    def _get_service_name(self) -> str:
        return "mcp"

    def get_router(self) -> APIRouter:
        if not self.enabled:
            return APIRouter()
        return mcp_router

    async def initialize(self) -> None:
        try:
            if not self.enabled:
                logger.warning("MCP服务未启用")
                return
            self.handlers = MCPHandlers(self.config)
            await self.handlers.initialize()
            logger.info("MCP服务初始化完成")
        except Exception as e:
            logger.error(f"MCP服务初始化失败 error={str(e)}")
            raise

    async def health_check(self) -> bool:
        if not self.enabled:
            return False
        return self.handlers is not None

    async def shutdown(self) -> None:
        logger.info("MCP服务清理完成")
