'''
Description: Chat服务主类
Author: zyq
Date: 2025-01-21
'''
from typing import Dict, Any
from fastapi import APIRouter
from loguru import logger

from services.base import BaseService
from .handlers import ChatHandlers
from .routers import chat_router


class ChatService(BaseService):
    """Chat服务主类"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.handlers = None
    
    def _get_service_name(self) -> str:
        """获取服务名称"""
        return "chat"
    
    def get_router(self) -> APIRouter:
        """获取服务路由"""
        if not self.enabled:
            return APIRouter()
        
        # 直接返回配置好的chat_router，由app.py统一添加前缀
        return chat_router
    
    async def initialize(self) -> None:
        """初始化chat服务"""
        try:
            if not self.enabled:
                logger.warning("Chat service not enabled")
                return
            
            # 初始化handlers
            self.handlers = ChatHandlers(self.config)
            await self.handlers.initialize()
            
            logger.info("Chat service initialized successfully")
            
        except Exception as e:
            logger.error(f"Chat service initialization failed: {str(e)}")
            raise
    
    async def health_check(self) -> bool:
        """服务健康检查"""
        if not self.enabled:
            return False
        
        # 只检查handlers是否已初始化，不检查模型健康状态
        return self.handlers is not None
    
    def get_service_info(self) -> Dict[str, Any]:
        """获取服务信息"""
        if not self.enabled:
            return {
                "name": self.service_name,
                "enabled": False,
                "status": "disabled"
            }
        
        enabled_models = []
        if self.handlers:
            enabled_models = self.handlers.get_enabled_models()
        
        return {
            "name": self.service_name,
            "enabled": True,
            "version": self.version,
            "status": "running" if self.handlers else "initializing",
            "endpoints": self.get_enabled_endpoints(),
            "enabled_models": enabled_models
        }
    
    async def shutdown(self) -> None:
        """服务关闭清理"""
        try:
            if self.handlers:
                # 这里可以添加清理逻辑，比如关闭连接、清理缓存等
                logger.info("Chat service cleanup completed")
        except Exception as e:
            logger.error(f"Error occurred during Chat service shutdown: {str(e)}")