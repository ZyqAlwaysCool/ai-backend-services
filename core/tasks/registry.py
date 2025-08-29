'''
Description: 任务函数注册表, 提供通用的任务函数注册和查找机制
Author: zyq
Date: 2025-08-29 10:07:49
LastEditors: zyq
LastEditTime: 2025-08-29 10:30:19
'''
from typing import Dict, Callable, Any
from loguru import logger


class TaskFunctionRegistry:
    """任务函数注册表"""
    
    def __init__(self):
        self._functions: Dict[str, Callable] = {}
    
    def register(self, func_name: str, func: Callable):
        """
        注册任务函数
        
        Args:
            func_name: 函数名称
            func: 函数对象
        """
        if func_name in self._functions:
            logger.warning(f"Function {func_name} already registered, overriding")
        
        self._functions[func_name] = func
        logger.info(f"Registered task function: {func_name}")
    
    def get(self, func_name: str) -> Callable:
        """
        获取任务函数
        
        Args:
            func_name: 函数名称
            
        Returns:
            函数对象
            
        Raises:
            ValueError: 函数未注册时抛出
        """
        if func_name not in self._functions:
            raise ValueError(f"Task function '{func_name}' is not registered")
        
        return self._functions[func_name]
    
    def list_functions(self) -> Dict[str, str]:
        """列出所有已注册的函数"""
        return {name: str(func) for name, func in self._functions.items()}


class TaskCollectionRegistry:
    """任务Collection映射注册表"""
    
    def __init__(self):
        self._mappings: Dict[str, str] = {'default': 'task_records'}  # 默认映射
        self._prefix_mappings: Dict[str, str] = {}  # task_id前缀 → collection_type 映射
    
    def register(self, task_type_key: str, collection_name: str, task_id_prefix: str = None):
        """
        注册任务类型到collection的映射
        
        Args:
            task_type_key: 任务类型键(如: 'pdf_batch_processing')  
            collection_name: MongoDB collection名称
            task_id_prefix: 任务ID前缀(如: 'pdf_batch')，用于查找
        """
        if task_type_key in self._mappings and task_type_key != 'default':
            logger.warning(f"Task type {task_type_key} already registered, overriding")
        
        self._mappings[task_type_key] = collection_name
        
        # 注册task_id前缀映射（如果提供）
        if task_id_prefix:
            self._prefix_mappings[task_id_prefix] = task_type_key
            logger.info(f"Registered task mapping: {task_type_key} -> {collection_name} (prefix: {task_id_prefix})")
        else:
            logger.info(f"Registered task collection mapping: {task_type_key} -> {collection_name}")
    
    def get_mappings(self) -> Dict[str, str]:
        """获取所有映射"""
        return self._mappings.copy()
    
    def get_collection(self, task_type_key: str) -> str:
        """
        获取任务类型对应的collection名称
        
        Args:
            task_type_key: 任务类型键
            
        Returns:
            collection名称
        """
        return self._mappings.get(task_type_key, self._mappings['default'])
    
    def get_collection_by_task_id(self, task_id: str) -> str:
        """
        根据task_id查找对应的collection类型键
        
        Args:
            task_id: 任务ID
            
        Returns:
            collection类型键
        """
        if '_' not in task_id:
            return 'default'
        
        # 提取前缀
        prefix = task_id.split('_')[0]
        
        # 从前缀映射中查找
        return self._prefix_mappings.get(prefix, 'default')


# 全局注册表实例
task_registry = TaskFunctionRegistry()
collection_registry = TaskCollectionRegistry()
