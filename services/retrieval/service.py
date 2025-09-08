'''
Description: Retrieval服务主类
Author: zyq
Date: 2025-09-08
'''

from typing import Dict, Any
from fastapi import APIRouter
from loguru import logger

from services.base import BaseService
from .handlers import RetrievalHandlers
from .routers import retrieval_router


class RetrievalService(BaseService):
    """Retrieval服务主类"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.handlers = None
    
    def _get_service_name(self) -> str:
        return "retrieval"
    
    def get_router(self) -> APIRouter:
        if not self.enabled:
            return APIRouter()
        return retrieval_router
    
    async def initialize(self) -> None:
        if not self.enabled:
            logger.warning("Retrieval service not enabled")
            return
        
        self.handlers = RetrievalHandlers(self.config)
        await self.handlers.initialize()
        logger.info("Retrieval service initialized")
    
    async def health_check(self) -> bool:
        if not self.enabled:
            return False
        return self.handlers is not None