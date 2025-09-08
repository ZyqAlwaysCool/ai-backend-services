'''
Description: 服务注册器
Author: zyq
Date: 2025-01-21
'''
import importlib
from typing import Dict, List, Optional
from loguru import logger

from .base import BaseService
from core.config import get_services_config, ServicesConfig


class ServiceRegistry:
    """AI服务注册器"""
    
    def __init__(self):
        self.services: Dict[str, BaseService] = {}
        self.services_config = get_services_config()
    
    async def discover_and_register_services(self):
        """发现并注册所有启用的服务"""
        enabled_services = self.services_config.enabled
        
        for service_name in enabled_services:
            try:
                await self._register_service(service_name)
            except Exception as e:
                logger.error(f"Service registration failed service={service_name} error={str(e)}")
                continue
    
    async def _register_service(self, service_name: str):
        """注册单个服务"""
        
        # 动态导入服务模块
        module_path = f"services.{service_name}.service"
        module = importlib.import_module(module_path)
        
        # 获取服务类 (约定命名: {ServiceName}Service)
        class_name = f"{service_name.capitalize()}Service"
        service_class = getattr(module, class_name)
        
        # 获取服务配置
        service_config_attr = getattr(self.services_config, service_name, None)
        if service_config_attr:
            # 将Pydantic模型转换为字典，以保持与原有接口兼容
            service_config = service_config_attr.model_dump()
        else:
            service_config = {}
        
        # 实例化服务
        service_instance = service_class(service_config)
        
        # 检查服务是否启用
        if not service_instance.enabled:
            logger.warning(f"Service disabled, skipping registration service={service_name}")
            return
        
        # 初始化服务
        await service_instance.initialize()
        
        # 注册服务
        self.services[service_name] = service_instance
    
    def get_enabled_services(self) -> Dict[str, BaseService]:
        """获取所有启用的服务"""
        return {name: service for name, service in self.services.items() 
                if service.enabled}
    
    def get_service(self, name: str) -> Optional[BaseService]:
        """获取指定服务"""
        return self.services.get(name)
    
    def get_all_routers(self) -> List:
        """获取所有服务的路由"""
        routers = []
        for service in self.get_enabled_services().values():
            router = service.get_router()
            if router and router.routes:  # 只添加非空路由
                routers.append(router)
        return routers
    
    async def health_check_all(self) -> Dict[str, bool]:
        """检查所有服务的健康状态"""
        results = {}
        for name, service in self.get_enabled_services().items():
            try:
                results[name] = await service.health_check()
            except Exception as e:
                logger.error(f"Health check failed service={name} error={str(e)}")
                results[name] = False
        return results


# 全局服务注册器实例
service_registry = ServiceRegistry()