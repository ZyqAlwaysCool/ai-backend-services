'''
Description: ARQ Worker任务处理函数,只负责定义任务处理逻辑,不涉及Worker管理
Author: zyq
Date: 2025-08-28 11:35:30
LastEditors: zyq
LastEditTime: 2025-08-29 09:50:24
'''

import asyncio
import time
from typing import Dict, Any
from loguru import logger

from .models.task_models import TaskResult, TaskStatus
from .registry import task_registry


async def process_task(
    ctx,  # ARQ上下文参数
    task_dict: Dict[str, Any],
    func_name: str,
    args: tuple,
    kwargs: Dict[str, Any],
    **arq_kwargs  # 接收ARQ传递的额外参数
) -> TaskResult:
    """
    通用任务处理函数 - ARQ Worker的统一入口
    
    Args:
        task_dict: 任务字典数据
        func_name: 要执行的函数名称
        args: 函数位置参数
        kwargs: 函数关键字参数
        
    Returns:
        任务执行结果
    """
    start_time = time.time()
    task_id = task_dict.get('task_id', 'unknown')
    
    try:
        logger.info(f"Processing task: {task_id} | Function: {func_name}")
        
        # 动态导入并执行业务函数
        func = _get_business_function(func_name)
        
        # 将task_id添加到kwargs中传递给业务函数
        kwargs['task_id'] = task_id
        
        # 执行业务函数
        if asyncio.iscoroutinefunction(func):
            result = await func(*args, **kwargs)
        else:
            result = func(*args, **kwargs)
        
        execution_time = time.time() - start_time
        logger.info(f"Task completed: {task_id} in {execution_time:.2f}s")
        
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.COMPLETED,
            result_data=result,
            execution_time=execution_time
        )
        
    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"Task failed: {task_id} after {execution_time:.2f}s - {str(e)}")
        
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.FAILED,
            result_data=None,
            metadata={'error': str(e)},
            execution_time=execution_time
        )


def _get_business_function(func_name: str):
    """
    通过注册表获取业务函数 - 完全通用，无业务侵入
    
    Args:
        func_name: 函数名称
        
    Returns:
        业务函数对象
        
    Raises:
        ValueError: 函数未注册时抛出
    """
    try:
        return task_registry.get(func_name)
    except ValueError as e:
        logger.error(f"Task function not found: {func_name}. Available functions: {list(task_registry._functions.keys())}")
        raise e