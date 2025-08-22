'''
Description: 认证用户存储服务
Author: zyq
Date: 2025-01-21
'''
import hashlib
import secrets
from typing import Optional, List, Tuple
from datetime import datetime
from loguru import logger
from pymongo.errors import DuplicateKeyError

from core.storage.mongo_storage import MongoStorage
from .models import AuthUser, UserStatus

class AuthUserStorage:
    """认证用户存储服务"""
    
    def __init__(self, mongo_storage: MongoStorage):
        self.mongo = mongo_storage
        self.collection_name = "auth_users"
        self._ensure_indexes()
    
    def _ensure_indexes(self):
        """确保数据库索引"""
        collection = self.mongo.db[self.collection_name]
        # 用户名唯一索引
        collection.create_index("username", unique=True)
        # 用户ID唯一索引
        collection.create_index("user_id", unique=True)
    
    def _hash_password(self, password: str) -> str:
        """密码加密"""
        salt = secrets.token_hex(16)
        password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        return f"{salt}:{password_hash}"
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """验证密码"""
        try:
            salt, hashed = password_hash.split(":", 1)
            return hashlib.sha256((password + salt).encode()).hexdigest() == hashed
        except ValueError:
            return False
    
    def create_user(self, business_name: str, permissions: List[str]) -> Tuple[AuthUser, str]:
        """创建用户 - 仅供脚本使用"""
        try:
            # 生成用户名格式: {业务名}_auth_user
            username = f"{business_name}_auth_user"
            user_id = f"user_{secrets.token_hex(8)}"
            
            # 生成随机密码 (16位，包含字母数字)
            password = secrets.token_urlsafe(16)
            password_hash = self._hash_password(password)
            
            user_data = {
                "user_id": user_id,
                "username": username,
                "password_hash": password_hash,
                "permissions": permissions,
                "status": UserStatus.ACTIVE,
                "created_at": datetime.utcnow(),
                "last_login": None
            }
            
            collection = self.mongo.db[self.collection_name]
            result = collection.insert_one(user_data)
            user_data["_id"] = result.inserted_id
            
            logger.info(f"Auth user created: {username} (ID: {user_id})")
            return AuthUser(**user_data), password  # 返回明文密码供脚本输出
            
        except DuplicateKeyError:
            raise ValueError(f"业务 '{business_name}' 的认证用户已存在")
    
    def authenticate_user(self, username: str, password: str) -> Optional[AuthUser]:
        """用户认证"""
        collection = self.mongo.db[self.collection_name]
        user_data = collection.find_one({"username": username, "status": UserStatus.ACTIVE})
        
        if not user_data:
            logger.warning(f"Authentication failed: user not found - {username}")
            return None
        
        if not self._verify_password(password, user_data["password_hash"]):
            logger.warning(f"Authentication failed: invalid password - {username}")
            return None
        
        # 更新最后登录时间
        collection = self.mongo.db[self.collection_name]
        collection.update_one(
            {"user_id": user_data["user_id"]},
            {"$set": {"last_login": datetime.utcnow()}}
        )
        
        logger.info(f"User authenticated: {username}")
        return AuthUser(**user_data)
    
    def get_user_by_username(self, username: str) -> Optional[AuthUser]:
        """根据用户名获取用户"""
        collection = self.mongo.db[self.collection_name]
        user_data = collection.find_one({"username": username})
        return AuthUser(**user_data) if user_data else None
    
    def disable_user(self, username: str) -> bool:
        """禁用用户"""
        collection = self.mongo.db[self.collection_name]
        result = collection.update_one(
            {"username": username},
            {"$set": {"status": UserStatus.DISABLED}}
        )
        return result.modified_count > 0
    
    def update_permissions(self, username: str, permissions: List[str]) -> bool:
        """更新用户权限"""
        collection = self.mongo.db[self.collection_name]
        result = collection.update_one(
            {"username": username},
            {"$set": {"permissions": permissions}}
        )
        return result.modified_count > 0