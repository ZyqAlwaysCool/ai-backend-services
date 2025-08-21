'''
Description: 全局异常处理和自定义异常定义
Author: zyq
Date: 2025-08-13 14:30:00
LastEditors: zyq
LastEditTime: 2025-08-13 14:30:00
'''
from typing import Any, Dict, Optional
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
import traceback
import uuid
from ..config.error_codes import *


class BaseBusinessException(Exception):
    """业务异常基类"""
    def __init__(self, code: int, message: str, details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class FileProcessException(BaseBusinessException):
    """文件处理异常"""
    def __init__(self, message: str = "文件处理失败", details: Optional[Dict[str, Any]] = None):
        super().__init__(FILE_ERROR_PREPROCESS_FAILED, message, details)


class WorkflowException(BaseBusinessException):
    """工作流执行异常"""
    def __init__(self, message: str = "工作流执行失败", code: int = -11000, details: Optional[Dict[str, Any]] = None):
        super().__init__(code, message, details)


class DatabaseException(BaseBusinessException):
    """数据库操作异常"""
    def __init__(self, message: str = "数据库操作失败", code: int = DB_ERROR_SYSTEM_ERROR, details: Optional[Dict[str, Any]] = None):
        super().__init__(code, message, details)


class ValidationException(BaseBusinessException):
    """参数验证异常"""
    def __init__(self, message: str = "参数验证失败", details: Optional[Dict[str, Any]] = None):
        super().__init__(COMMON_ERROR_INVALID_REQUEST_PARAM_ERROR, message, details)


def generate_trace_id() -> str:
    """生成请求追踪ID"""
    return str(uuid.uuid4())


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """全局异常处理器"""
    # 获取或生成追踪ID
    trace_id = getattr(request.state, 'trace_id', generate_trace_id())
    
    # 记录异常详情
    logger.error(
        f"Global exception caught - TraceID: {trace_id} | "
        f"Path: {request.url.path} | "
        f"Method: {request.method} | "
        f"Exception: {type(exc).__name__}: {str(exc)} | "
        f"Traceback: {traceback.format_exc()}"
    )
    
    # 根据异常类型返回不同响应
    if isinstance(exc, BaseBusinessException):
        return JSONResponse(
            status_code=200,  # 业务异常仍返回200
            content={
                "code": exc.code,
                "msg": exc.message,
                "data": "",
                "trace_id": trace_id,
                "details": exc.details
            }
        )
    elif isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.status_code,
                "msg": exc.detail,
                "data": "",
                "trace_id": trace_id
            }
        )
    elif isinstance(exc, ValueError):
        return JSONResponse(
            status_code=200,
            content={
                "code": COMMON_ERROR_INVALID_REQUEST_PARAM_ERROR,
                "msg": f"参数验证错误: {str(exc)}",
                "data": "",
                "trace_id": trace_id
            }
        )
    else:
        # 未知异常
        return JSONResponse(
            status_code=500,
            content={
                "code": -50000,
                "msg": "系统内部错误，请稍后重试",
                "data": "",
                "trace_id": trace_id
            }
        )


async def business_exception_handler(request: Request, exc: BaseBusinessException) -> JSONResponse:
    """业务异常处理器"""
    trace_id = getattr(request.state, 'trace_id', generate_trace_id())
    
    logger.warning(
        f"Business exception - TraceID: {trace_id} | "
        f"Path: {request.url.path} | "
        f"Code: {exc.code} | "
        f"Message: {exc.message} | "
        f"Details: {exc.details}"
    )
    
    return JSONResponse(
        status_code=200,
        content={
            "code": exc.code,
            "msg": exc.message,
            "data": "",
            "trace_id": trace_id,
            "details": exc.details
        }
    )