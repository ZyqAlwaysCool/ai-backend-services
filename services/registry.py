'''
Description: 服务注册器
Author: zyq
Date: 2025-01-21
'''
import importlib
from typing import Dict, List, Optional
from pathlib import Path
from loguru import logger
import yaml
import os

from .base import BaseService


class ServiceRegistry:
    """AI服务注册器"""
    
    def __init__(self):
        self.services: Dict[str, BaseService] = {}
        self.services_config = self._load_services_config()
    
    def _load_services_config(self) -> Dict[str, any]:
        """加载服务配置"""
        config_path = Path(__file__).parent.parent / "configs" / "services" / "services.yml"
        
        if not config_path.exists():
            raise FileNotFoundError(f"服务配置文件不存在: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    async def discover_and_register_services(self):
        """发现并注册所有启用的服务"""
        enabled_services = self.services_config.get('services', {}).get('enabled', [])
        
        for service_name in enabled_services:
            try:
                await self._register_service(service_name)
            except Exception as e:
                logger.error(f"Failed to register service {service_name}: {str(e)}")
                continue
    
    async def _register_service(self, service_name: str):
        """注册单个服务"""
        logger.info(f"Registering service: {service_name}")
        
        # 动态导入服务模块
        module_path = f"services.{service_name}.service"
        module = importlib.import_module(module_path)
        
        # 获取服务类 (约定命名: {ServiceName}Service)
        class_name = f"{service_name.capitalize()}Service"
        service_class = getattr(module, class_name)
        
        # 获取服务配置
        service_config = self.services_config.get('services', {}).get(service_name, {})
        
        # 实例化服务
        service_instance = service_class(service_config)
        
        # 检查服务是否启用
        if not service_instance.enabled:
            logger.warning(f"Service {service_name} is disabled, skipping registration")
            return
        
        # 初始化服务
        await service_instance.initialize()
        
        # 注册服务
        self.services[service_name] = service_instance
        logger.info(f"Successfully registered service: {service_name}")
    
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
                logger.error(f"Health check failed for {name}: {str(e)}")
                results[name] = False
        return results


# 全局服务注册器实例
service_registry = ServiceRegistry()