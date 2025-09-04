'''
Description: Document服务类
Author: zyq
Date: 2025-08-27 15:47:04
LastEditors: zyq
LastEditTime: 2025-08-29 15:40:33
'''
from typing import Dict, Any
from fastapi import APIRouter
from loguru import logger

from services.base import BaseService
from .handlers import DocumentHandlers
from .routers import document_router


class DocumentService(BaseService):
    """Document服务主类"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.handlers = None
    
    def _get_service_name(self) -> str:
        return "document"
    
    def get_router(self) -> APIRouter:
        if not self.enabled:
            return APIRouter()
        return document_router
    
    async def initialize(self) -> None:
        if not self.enabled:
            logger.warning("Document service not enabled")
            return
        
        self.handlers = DocumentHandlers(self.config)
        await self.handlers.initialize()
        logger.info("Document service initialized")
    
    async def health_check(self) -> bool:
        if not self.enabled:
            return False
        return self.handlers is not None