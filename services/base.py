'''
Description: 服务基类
Author: zyq
Date: 2025-08-21 16:22:44
LastEditors: zyq
LastEditTime: 2025-10-11 10:39:16
'''
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from fastapi import APIRouter


class BaseService(ABC):
    """AI服务基类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.service_name = self._get_service_name()
        self.version = config.get('version', '1.0.0')
        self.enabled = config.get('enabled', False)
    
    @abstractmethod
    def _get_service_name(self) -> str:
        """获取服务名称"""
        pass
    
    @abstractmethod
    def get_router(self) -> APIRouter:
        """获取服务路由"""
        pass
    
    @abstractmethod
    async def initialize(self):
        """初始化服务"""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass
    
    def get_enabled_endpoints(self) -> List[str]:
        """获取启用的端点列表"""
        endpoints_config = self.config.get('endpoints', {})
        return [name for name, enabled in endpoints_config.items() if enabled]
    
    def is_endpoint_enabled(self, endpoint_name: str) -> bool:
        """检查端点是否启用"""
        return self.config.get('endpoints', {}).get(endpoint_name, False)
    
    def get_metadata(self) -> Dict[str, Any]:
        """获取服务元数据"""
        return {
            'service_name': self.service_name,
            'version': self.version,
            'enabled': self.enabled,
            'enabled_endpoints': self.get_enabled_endpoints()
        }