'''
Description: 认证中间件
Author: zyq
Date: 2025-01-21
'''
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        # 不需要认证的路径
        self.public_paths = {
            "/auth/login",
            "/auth/verify", 
            "/health",
            "/",
            "/docs",
            "/openapi.json",
            "/redoc"
        }
    
    async def dispatch(self, request: Request, call_next):
        # 跳过公开接口
        if request.url.path in self.public_paths:
            return await call_next(request)
        
        # 获取trace_id用于日志
        trace_id = getattr(request.state, 'trace_id', 'unknown')
        
        # 获取认证服务实例
        auth_service = getattr(request.app.state, 'auth_service', None)
        if not auth_service:
            logger.warning(f"Auth service not available - TraceID: {trace_id}")
            raise HTTPException(status_code=500, detail="认证服务不可用")
        
        # 检查Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            logger.warning(f"Missing or invalid Authorization header - TraceID: {trace_id}")
            raise HTTPException(status_code=401, detail="缺少或无效的授权头信息")
        
        # 提取token
        token = auth_header.split(" ")[1]
        
        # 验证token
        payload = auth_service.verify_token(token)
        if not payload:
            logger.warning(f"Invalid or expired token - TraceID: {trace_id}")
            raise HTTPException(status_code=401, detail="无效或已过期的令牌")
        
        # 将用户信息存储到request state
        request.state.user_id = payload.user_id
        request.state.username = payload.username
        request.state.permissions = payload.permissions
        
        return await call_next(request)