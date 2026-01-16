'''
Description: 认证服务
Author: zyq
Date: 2025-11-12 09:31:14
LastEditors: zyq
LastEditTime: 2026-01-12 17:06:16
'''

import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional
from loguru import logger

from .models import AuthUser, TokenResponse, TokenPayload
from .user_storage import AuthUserStorage

class AuthService:
    def __init__(self, secret_key: str, token_expire_hours: int = 24):
        self.secret_key = secret_key
        self.token_expire_hours = token_expire_hours
        self.user_storage: Optional[AuthUserStorage] = None

    def set_user_storage(self, user_storage: AuthUserStorage):
        """设置用户存储服务"""
        self.user_storage = user_storage

    def register(self, business_name: str) -> tuple[Optional[AuthUser], Optional[str], Optional[str]]:
        """
        用户注册
        返回: (user, password, error_message)
        - 成功: (user, password, None)
        - 用户已存在: (None, None, "用户已存在")
        - 其他错误: (None, None, "注册失败")
        """
        if not self.user_storage:
            logger.error("User storage not initialized")
            return None, None, "系统错误"

        try:
            # 默认给予全部权限
            permissions = ["*"]
            user, password = self.user_storage.create_user(business_name, permissions)
            logger.info(f"User registered successfully: {user.username}")
            return user, password, None
        except ValueError as e:
            # 用户已存在
            logger.warning(f"User registration failed: {str(e)}")
            return None, None, str(e)
        except Exception as e:
            logger.error(f"User registration error: {str(e)}")
            return None, None, "注册失败"

    def authenticate(self, username: str, password: str) -> Optional[TokenResponse]:
        """用户认证"""
        if not self.user_storage:
            logger.error("User storage not initialized")
            return None
        
        user = self.user_storage.authenticate_user(username, password)
        if not user:
            return None
        
        # 生成token
        expires_at = datetime.now(timezone.utc) + timedelta(hours=self.token_expire_hours)
        payload = {
            "user_id": user.user_id,
            "username": user.username,
            "permissions": user.permissions,
            "exp": int(expires_at.timestamp())
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm="HS256")
        
        logger.info(f"User {username} authenticated successfully")
        return TokenResponse(
            access_token=token,
            expires_in=self.token_expire_hours * 3600,
            expires_at=expires_at
        )
    
    def verify_token(self, token: str) -> Optional[TokenPayload]:
        """验证Token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            return TokenPayload(**payload)
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired.")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {str(e)}")
            return None
