'''
Description: 认证路由
Author: zyq
Date: 2025-01-21
'''
import uuid
from fastapi import APIRouter, Request
from loguru import logger

from core.schemas.base_resp_model_define import BaseResponse
from .models import LoginRequest, TokenResponse
from .auth_service import AuthService

auth_router = APIRouter(prefix="/auth", tags=["认证"])

# 认证服务实例（在app.py中注入）
auth_service_instance: AuthService = None

def set_auth_service(service: AuthService):
    """设置认证服务实例"""
    global auth_service_instance
    auth_service_instance = service

@auth_router.post("/login", response_model=BaseResponse)
async def login(request: LoginRequest, http_request: Request):
    """用户登录获取访问token"""
    trace_id = str(uuid.uuid4())
    logger.info(f"Login request - TraceID: {trace_id} | Username: {request.username}")
    
    try:
        token_response = auth_service_instance.authenticate(
            request.username, 
            request.password
        )
        
        if not token_response:
            logger.warning(f"Authentication failed - TraceID: {trace_id}")
            return BaseResponse.error(
                code=401,
                msg="用户名或密码错误",
                trace_id=trace_id
            )
        
        logger.info(f"Authentication successful - TraceID: {trace_id}")
        return BaseResponse.success(
            data=token_response.dict(),
            trace_id=trace_id
        )
        
    except Exception as e:
        logger.error(f"Login error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="登录服务异常",
            trace_id=trace_id
        )

@auth_router.post("/verify", response_model=BaseResponse)
async def verify_token(token: str, http_request: Request):
    """验证token有效性（可选接口）"""
    trace_id = str(uuid.uuid4())
    
    try:
        payload = auth_service_instance.verify_token(token)
        if not payload:
            return BaseResponse.error(
                code=401,
                msg="Token无效或已过期",
                trace_id=trace_id
            )
        
        return BaseResponse.success(
            data={
                "valid": True,
                "user_id": payload.user_id,
                "username": payload.username,
                "permissions": payload.permissions,
                "expires_at": payload.exp
            },
            trace_id=trace_id
        )
        
    except Exception as e:
        logger.error(f"Token verification error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="Token验证异常",
            trace_id=trace_id
        )