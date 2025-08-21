'''
Description: 中间件集合，包含请求追踪、日志记录等
Author: zyq
Date: 2025-08-13 14:35:00
LastEditors: zyq
LastEditTime: 2025-08-13 14:35:00
'''
import time
import uuid
from typing import Callable
from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware


class RequestTraceMiddleware(BaseHTTPMiddleware):
    """请求追踪中间件"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 生成或获取追踪ID
        trace_id = request.headers.get('X-Trace-ID', str(uuid.uuid4()))
        request.state.trace_id = trace_id
        
        # 记录请求开始时间
        start_time = time.time()
        
        # 记录请求信息
        logger.info(
            f"Request started - TraceID: {trace_id} | "
            f"Method: {request.method} | "
            f"Path: {request.url.path} | "
            f"Query: {request.url.query} | "
            f"Client: {request.client.host if request.client else 'unknown'}"
        )
        
        # 处理请求
        try:
            response = await call_next(request)
            
            # 计算处理时间
            process_time = time.time() - start_time
            
            # 添加追踪ID到响应头
            response.headers['X-Trace-ID'] = trace_id
            
            # 记录请求完成信息
            logger.info(
                f"Request completed - TraceID: {trace_id} | "
                f"Status: {response.status_code} | "
                f"Duration: {process_time:.3f}s"
            )
            
            return response
            
        except Exception as exc:
            # 记录异常信息
            process_time = time.time() - start_time
            logger.error(
                f"Request failed - TraceID: {trace_id} | "
                f"Duration: {process_time:.3f}s | "
                f"Exception: {type(exc).__name__}: {str(exc)}"
            )
            raise  # 重新抛出异常给全局异常处理器


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 记录请求体大小（如果存在）
        content_length = request.headers.get('content-length', '0')
        
        logger.debug(
            f"Request details - "
            f"User-Agent: {request.headers.get('user-agent', 'unknown')} | "
            f"Content-Length: {content_length} | "
            f"Content-Type: {request.headers.get('content-type', 'unknown')}"
        )
        
        response = await call_next(request)
        
        # 记录响应详情
        logger.debug(
            f"Response details - "
            f"Content-Type: {response.headers.get('content-type', 'unknown')} | "
            f"Content-Length: {response.headers.get('content-length', 'unknown')}"
        )
        
        return response