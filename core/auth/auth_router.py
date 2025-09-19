'''
Description: 认证路由
Author: zyq
Date: 2025-08-22 14:58:12
LastEditors: zyq
LastEditTime: 2025-09-18 15:31:24
'''

import uuid
from fastapi import APIRouter, Request
from loguru import logger

from core.schemas.base_resp_model_define import BaseResponse
from .models import LoginRequest, TokenResponse
from .auth_service import AuthService
from core.config.error_codes import *

auth_router = APIRouter(prefix="/auth", tags=["认证"])

# 认证服务实例（在app.py中注入）
auth_service_instance: AuthService = None

def set_auth_service(service: AuthService):
    """设置认证服务实例"""
    global auth_service_instance
    auth_service_instance = service

@auth_router.post("/login", response_model=BaseResponse, summary=["登录鉴权"])
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
                code=AUTH_ERROR_AUTH_FAILED,
                msg=get_error_message(AUTH_ERROR_AUTH_FAILED),
                trace_id=trace_id
            )
        
        logger.info(f"Authentication successful - TraceID: {trace_id}")
        return BaseResponse.success(
            data=token_response.model_dump(),
            trace_id=trace_id
        )
        
    except Exception as e:
        logger.error(f"Login error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=AUTH_ERROR_LOGIN_FAILED,
            msg=get_error_message(AUTH_ERROR_LOGIN_FAILED),
            trace_id=trace_id
        )

@auth_router.post("/verify", response_model=BaseResponse, summary=["验证token有效性"])
async def verify_token(token: str, http_request: Request):
    """验证token有效性"""
    trace_id = str(uuid.uuid4())
    
    try:
        payload = auth_service_instance.verify_token(token)
        if not payload:
            return BaseResponse.error(
                code=AUTH_ERROR_INVALID_TOKEN,
                msg=get_error_message(AUTH_ERROR_INVALID_TOKEN),
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
            code=AUTH_ERROR_VERIFY_TOKEN_FAILED,
            msg=get_error_message(AUTH_ERROR_VERIFY_TOKEN_FAILED),
            trace_id=trace_id
        )