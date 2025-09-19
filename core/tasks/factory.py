'''
Description: 任务管理器工厂类
Author: zyq
Date: 2025-08-29 15:30:33
LastEditors: zyq
LastEditTime: 2025-09-18 16:58:19
'''
import os
from typing import Dict, Any, Optional
from loguru import logger

from .backends.arq_backend import ARQTaskBackend
from .backends.mongo_task_storage import MongoTaskStorage
from .base.queue_backend import QueueBackend
from .base.storage_backend import StorageBackend
from core.config.config_center import get_app_config, get_worker_config


class TaskManagerFactory:
    """任务管理器工厂类"""

    @classmethod
    def create_arq_backend(cls, config: Optional[Dict[str, Any]] = None) -> ARQTaskBackend:
        """
        创建ARQ队列后端
        
        Args:
            config: ARQ配置,如果为None则使用统一配置中心配置
            
        Returns:
            ARQ队列后端实例
        """
        # 从统一配置中心获取配置
        app_config = get_app_config()
        worker_config = get_worker_config()
        
        # 构建ARQ配置
        final_config = {
            'default_queue': worker_config.queue_name,
            'job_timeout': worker_config.job_timeout,
            'keep_result': worker_config.keep_result,
            'redis_host': app_config.redis_host,
            'redis_port': app_config.redis_port,
            'redis_db': app_config.redis_db,
            'redis_password': app_config.redis_password,
            'max_connections': app_config.redis_max_connections
        }
        
        # 用户自定义配置覆盖
        if config:
            final_config.update(config)
        
        logger.info(f"Creating ARQ backend with config: {final_config}")
        return ARQTaskBackend(final_config)
    
    @classmethod
    def create_mongo_storage(cls, config: Optional[Dict[str, Any]] = None) -> MongoTaskStorage:
        """
        创建MongoDB存储后端
        
        Args:
            config: MongoDB配置, 如果为None则使用统一配置中心配置
            
        Returns:
            MongoDB存储后端实例
        """
        # 从统一配置中心获取MongoDB配置
        app_config = get_app_config()
        
        final_config = {
            'db_name': app_config.mongo_database
        }
        
        # 用户自定义配置覆盖
        if config:
            final_config.update(config)
        
        logger.info(f"Creating MongoDB storage with config: {final_config}")
        return MongoTaskStorage(final_config)
    
    @classmethod
    def create_default_backends(
        cls, 
        arq_config: Optional[Dict[str, Any]] = None,
        mongo_config: Optional[Dict[str, Any]] = None
    ) -> tuple[QueueBackend, StorageBackend]:
        """
        创建默认的队列和存储后端
        
        Args:
            arq_config: ARQ配置
            mongo_config: MongoDB配置
            
        Returns:
            (队列后端, 存储后端) 元组
        """
        queue_backend = cls.create_arq_backend(arq_config)
        storage_backend = cls.create_mongo_storage(mongo_config)
        
        return queue_backend, storage_backend

    @classmethod
    async def health_check_backends(
        cls,
        queue_backend: QueueBackend,
        storage_backend: StorageBackend
    ) -> Dict[str, bool]:
        """
        检查后端健康状态
        
        Args:
            queue_backend: 队列后端
            storage_backend: 存储后端
            
        Returns:
            健康检查结果
        """
        result = {
            'queue': False,
            'storage': False,
            'overall': False
        }
        
        try:
            result['queue'] = await queue_backend.health_check()
        except Exception as e:
            logger.error(f"Queue health check failed: {str(e)}")
        
        try:
            # 简单的存储健康检查
            from .models.task_models import TaskQuery
            test_query = TaskQuery(limit=1)
            await storage_backend.query_tasks(test_query)
            result['storage'] = True
        except Exception as e:
            logger.error(f"Storage health check failed: {str(e)}")
        
        result['overall'] = result['queue'] and result['storage']
        return result
    
    @classmethod
    def validate_config(
        cls,
        rq_config: Optional[Dict[str, Any]] = None,
        mongo_config: Optional[Dict[str, Any]] = None,
        task_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        验证配置参数
        
        Args:
            rq_config: RQ配置
            mongo_config: MongoDB配置  
            task_config: 任务配置
            
        Returns:
            验证结果和错误信息
        """
        result = {
            'valid': True,
            'errors': []
        }
        
        # 验证RQ配置
        if rq_config:
            required_rq_fields = ['redis_host', 'redis_port']
            for field in required_rq_fields:
                if field not in rq_config:
                    result['errors'].append(f"Missing required RQ config field: {field}")
                    result['valid'] = False
        
        # 验证MongoDB配置
        if mongo_config:
            if 'collection_mapping' in mongo_config:
                mapping = mongo_config['collection_mapping']
                if not isinstance(mapping, dict):
                    result['errors'].append("collection_mapping must be a dictionary")
                    result['valid'] = False
                elif 'default' not in mapping:
                    result['errors'].append("collection_mapping must contain 'default' key")
                    result['valid'] = False
        
        # 验证任务配置
        if task_config:
            numeric_fields = ['default_timeout', 'default_max_retries']
            for field in numeric_fields:
                if field in task_config:
                    try:
                        int(task_config[field])
                    except (ValueError, TypeError):
                        result['errors'].append(f"Task config field '{field}' must be numeric")
                        result['valid'] = False
        
        return result