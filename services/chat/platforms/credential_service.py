'''
Description: 平台鉴权与客户端创建服务
Author: zyq
Date: 2025-11-21 09:40:23
LastEditors: zyq
LastEditTime: 2025-11-21 15:08:34
'''
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from loguru import logger

from core.exceptions import ValidationException
from core.workflow_clients.coze_client import CozeClient
from core.workflow_clients.dify_client import DifyClient
from core.storage import MongoStorage
from ..schemas import ApiKeyStatus, ChatFlowPlatform, ChatFlowApiKeyInfo, JWTOauthInfo, WorkflowApiKeyInfo, WorkFlowJWTOauthInfo


class CredentialService:
    """统一管理平台鉴权数据信息与客户端创建"""

    def __init__(
        self,
        chatflow_apikey_storage: MongoStorage,
        workflow_apikey_storage: MongoStorage,
        chatflow_oauth_storage: MongoStorage,
        workflow_oauth_storage: MongoStorage,
        coze_auth_mode: str,
        coze_oauth_token_ttl: int,
    ):
        self._chatflow_apikey_storage = chatflow_apikey_storage
        self._workflow_apikey_storage = workflow_apikey_storage
        self._chatflow_oauth_storage = chatflow_oauth_storage
        self._workflow_oauth_storage = workflow_oauth_storage        
        self._coze_auth_mode = coze_auth_mode
        self._coze_oauth_token_ttl = coze_oauth_token_ttl

    def get_chatflow_apikey_info(self, user_id: str, chatflow_name: str, platform: ChatFlowPlatform = ChatFlowPlatform.DIFY) -> Dict[str, Any]:
        filter_query = {
            "user_id": user_id,
            "chatflow_name": chatflow_name,
            "platform": platform,
            "status": ApiKeyStatus.ACTIVE,
        }
        records = self._chatflow_apikey_storage.find_record(filter_query)
        if len(records) == 0 or len(records) > 1:
            raise ValidationException(
                f"未找到用户 {user_id} 在 {platform} 平台的对话流 {chatflow_name} 的有效API Key"
            )

        apikey_info = records[0]

        # 如果是Coze平台的API key，检查是否超过30天有效期
        if platform == ChatFlowPlatform.COZE:
            created_at = apikey_info.get("created_at")
            if created_at:
                try:
                    if isinstance(created_at, str):
                        if "T" in created_at:
                            created_at_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        else:
                            if "." in created_at:
                                created_at_dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S.%f")
                            else:
                                created_at_dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                    elif isinstance(created_at, datetime):
                        created_at_dt = created_at
                    else:
                        logger.warning(f"Coze API key创建时间类型不支持 - key_id={apikey_info.get('key_id')} type={type(created_at)}")
                        return apikey_info

                    current_time = datetime.utcnow()
                    expiration_date = created_at_dt + timedelta(days=30)

                    if current_time > expiration_date:
                        update_filter = {"key_id": apikey_info.get("key_id")}
                        update_data = apikey_info.copy()
                        update_data["status"] = ApiKeyStatus.DISABLED
                        self._chatflow_apikey_storage.update_record(update_filter, update_data)

                        logger.warning(
                            f"Coze API key已过期并标记为DISABLED - key_id={apikey_info.get('key_id')} user_id={user_id} created_at={created_at}"
                        )

                        raise ValidationException(
                            f"{apikey_info.get('chatflow_name')} 在Coze平台的API Key已超过30天有效期，已被禁用。请更新API Key."
                        )
                except Exception as exc:
                    logger.error(f"解析Coze API key创建时间失败 - key_id={apikey_info.get('key_id')} created_at={created_at} error={str(exc)}")
        return apikey_info

    def get_chatflow_oauth_info(self, user_id: str, chatflow_name: str) -> Dict[str, Any]:
        logger.info(f"get chatflow oauth info user={user_id} chatflow={chatflow_name}")
        filter_query = {
            "user_id": user_id,
            "chatflow_name": chatflow_name,
            "status": ApiKeyStatus.ACTIVE,
        }
        records = self._chatflow_oauth_storage.find_record(filter_query)
        if len(records) == 0:
            raise ValidationException(f"未找到用户 {user_id} 的Coze OAuth配置, 对话流 {chatflow_name}")
        if len(records) > 1:
            raise ValidationException(f"用户 {user_id} 存在多个Coze OAuth配置, 对话流 {chatflow_name}")
        return records[0]

    def get_workflow_apikey_info(self, user_id: str, workflow_name: str, platform: ChatFlowPlatform = ChatFlowPlatform.DIFY) -> Dict[str, Any]:
        filter_query = {
            "user_id": user_id,
            "workflow_name": workflow_name,
            "platform": platform,
            "status": ApiKeyStatus.ACTIVE,
        }
        records = self._workflow_apikey_storage.find_record(filter_query)
        if len(records) == 0 or len(records) > 1:
            raise ValidationException(
                f"未找到用户 {user_id} 在{platform}平台的工作流 {workflow_name} 的有效API Key"
            )
        return records[0]
    
    def get_workflow_oauth_info(self, user_id: str, workflow_name: str) -> Dict[str, Any]:
        logger.info(f"get workflow oauth info user={user_id} workflow={workflow_name}")
        filter_query = {
            "user_id": user_id,
            "workflow_name": workflow_name,
            "status": ApiKeyStatus.ACTIVE,
        }
        records = self._workflow_oauth_storage.find_record(filter_query)
        if len(records) == 0:
            raise ValidationException(f"未找到用户 {user_id} 的Coze OAuth配置, 工作流 {workflow_name}")
        if len(records) > 1:
            raise ValidationException(f"用户 {user_id} 存在多个Coze OAuth配置, 工作流 {workflow_name}")
        return records[0]
    
    # ============ CRUD: chatflow apikey ============
    def add_chatflow_apikey(self, info: ChatFlowApiKeyInfo):
        filter_query = {
            "user_id": info.user_id,
            "chatflow_name": info.chatflow_name,
            "platform": info.platform,
            "api_key": info.api_key,
        }
        exist_records = self._chatflow_apikey_storage.find_record(filter_query)
        if len(exist_records) > 0:
            raise ValidationException("已存在相同的API key记录")
        if info.platform == ChatFlowPlatform.COZE and info.bot_id is None:
            raise ValidationException("coze平台必须指定bot_id, 此参数位于web链接的bot/xxx")
        self._chatflow_apikey_storage.create_record(info.model_dump())

    def update_chatflow_apikey(self, info: ChatFlowApiKeyInfo):
        filter_query = {
            "user_id": info.user_id,
            "chatflow_name": info.chatflow_name,
            "platform": info.platform,
        }
        exist_records = self._chatflow_apikey_storage.find_record(filter_query)
        if len(exist_records) == 0:
            raise ValidationException(f"用户=({info.user_id}) 不存在此chatflow apikey记录.")
        if len(exist_records) > 1:
            raise ValidationException(f"用户=({info.user_id}) 存在多个相同的chatflow apikey记录.")
        if info.platform == ChatFlowPlatform.COZE and info.bot_id is None:
            raise ValidationException("coze平台必须指定bot_id, 此参数位于web链接的bot/xxx")
        self._chatflow_apikey_storage.update_record(filter_query, info.model_dump())

    def list_chatflow_apikey(self, user_id: str) -> List[ChatFlowApiKeyInfo]:
        records = self._chatflow_apikey_storage.find_record({"user_id": user_id})
        return [
            ChatFlowApiKeyInfo(**record)
            for record in records
            if record.get("status") == ApiKeyStatus.ACTIVE
        ]

    # ============ CRUD: chatflow oauth ============
    def add_chatflow_oauth(self, info: JWTOauthInfo):
        filter_query = {
            "user_id": info.user_id,
            "chatflow_name": info.chatflow_name,
        }
        exist_records = self._chatflow_oauth_storage.find_record(filter_query)
        if len(exist_records) > 0:
            raise ValidationException(
                f"用户 {info.user_id} 已存在Coze OAuth配置, 对话流 {info.chatflow_name}"
            )
        self._chatflow_oauth_storage.create_record(info.model_dump())

    def update_chatflow_oauth(self, chatflow_name: str, user_id: str, updated: Dict[str, Any]):
        filter_query = {
            "user_id": user_id,
            "chatflow_name": chatflow_name,
        }
        records = self._chatflow_oauth_storage.find_record(filter_query)
        if len(records) == 0:
            raise ValidationException(f"未找到用户 {user_id} 的Coze OAuth配置, 对话流 {chatflow_name}")
        if len(records) > 1:
            raise ValidationException(f"用户 {user_id} 存在多个Coze OAuth配置, 对话流 {chatflow_name}")

        origin = records[0]
        updated_data = origin.copy()
        updated_data.update({k: v for k, v in updated.items() if v is not None})
        self._chatflow_oauth_storage.update_record({"oauth_key_id": origin["oauth_key_id"]}, updated_data)
        return origin["oauth_key_id"]

    def list_chatflow_oauth(self, user_id: str) -> List[JWTOauthInfo]:
        records = self._chatflow_oauth_storage.find_record({"user_id": user_id})
        return [
            JWTOauthInfo(**record)
            for record in records
            if record.get("status") == ApiKeyStatus.ACTIVE
        ]

    # ============ CRUD: workflow apikey ============
    def add_workflow_apikey(self, info: WorkflowApiKeyInfo):
        filter_query = {
            "user_id": info.user_id,
            "workflow_name": info.workflow_name,
            "platform": info.platform,
            "api_key": info.api_key,
        }
        exist_records = self._workflow_apikey_storage.find_record(filter_query)
        if len(exist_records) > 0:
            raise ValidationException("已存在相同的API key记录")
        if info.platform == ChatFlowPlatform.COZE and info.workflow_id is None:
            raise ValidationException("coze平台工作流必须指定workflow_id, 此参数位于web链接的workflow_id=xxx") 
        self._workflow_apikey_storage.create_record(info.model_dump())

    def list_workflow_apikey(self, user_id: str) -> List[WorkflowApiKeyInfo]:
        records = self._workflow_apikey_storage.find_record({"user_id": user_id})
        return [
            WorkflowApiKeyInfo(**record)
            for record in records
            if record.get("status") == ApiKeyStatus.ACTIVE
        ]
    
    # ============ CRUD: chatflow oauth ============
    def add_workflow_oauth(self, info: WorkFlowJWTOauthInfo):
        filter_query = {
            "user_id": info.user_id,
            "workflow_name": info.workflow_name,
        }
        exist_records = self._workflow_oauth_storage.find_record(filter_query)
        if len(exist_records) > 0:
            raise ValidationException(
                f"用户 {info.user_id} 已存在Coze OAuth配置, 工作流 {info.workflow_name}"
            )
        self._workflow_oauth_storage.create_record(info.model_dump())

    def create_coze_client(self, user_id: str, app_name: str, platform_user: str, is_workflow: bool = False) -> tuple[CozeClient, str]:
        """app_name 复用 chatflow/workflow 的名称；is_workflow 标识取何处 bot_id"""
        if self._coze_auth_mode == "oauth":
            if is_workflow:
                oauth_info = self.get_workflow_oauth_info(user_id=user_id, workflow_name=app_name)
                workflow_id = oauth_info.get("workflow_id")
            else:
                oauth_info = self.get_chatflow_oauth_info(user_id=user_id, chatflow_name=app_name)
            client = CozeClient.with_oauth(
                client_id=oauth_info["oauth_client_id"],
                pub_key=oauth_info["oauth_public_key"],
                pri_key=oauth_info["oauth_private_key"],
                workflow_name=app_name,
                user_id=platform_user,
                token_ttl=self._coze_oauth_token_ttl,
            )
            bot_id = oauth_info.get("bot_id")
            logger.info(
                "[coze_auth] mode=oauth user=({}) app=({}) bot_id=({}) client_id=({}) ttl={}",
                user_id,
                app_name,
                bot_id,
                oauth_info.get("oauth_client_id"),
                self._coze_oauth_token_ttl,
            )
        else:
            if is_workflow:
                apikey_info = self.get_workflow_apikey_info(user_id, app_name, ChatFlowPlatform.COZE)
                workflow_id = apikey_info.get("workflow_id")
            else:
                apikey_info = self.get_chatflow_apikey_info(user_id, app_name, ChatFlowPlatform.COZE)
            client = CozeClient(
                access_api_key=apikey_info["api_key"],
                workflow_name=app_name,
                user_id=platform_user,
            )
            bot_id = apikey_info.get("bot_id")
            logger.info(
                "[coze_auth] mode=api_key user=({}) app=({}) bot_id=({}) key_id=({}) api_key_masked=({})",
                user_id,
                app_name,
                bot_id,
                apikey_info.get("key_id"),
                self._mask_secret(apikey_info.get("api_key")),
            )
        if is_workflow:
            if not workflow_id:
                raise ValidationException("coze工作流必须设置workflow_id")
            return client, bot_id, workflow_id
        else:
            if not bot_id:
                raise ValidationException("coze对话流必须设置bot_id")
            return client, bot_id

    def create_dify_chatflow_client(
        self,
        user_id: str,
        chatflow_name: str,
        platform_user: str,
        dify_url: str,
    ) -> DifyClient:
        apikey_info = self.get_chatflow_apikey_info(
            user_id=user_id,
            chatflow_name=chatflow_name,
            platform=ChatFlowPlatform.DIFY,
        )
        api_key = apikey_info["api_key"]
        return DifyClient(
            dify_url=dify_url,
            access_api_key=api_key,
            workflow_name=chatflow_name,
            user_id=platform_user,
        )

    def create_dify_workflow_client(
        self,
        user_id: str,
        workflow_name: str,
        platform_user: str,
        dify_url: str,
    ) -> DifyClient:
        apikey_info = self.get_workflow_apikey_info(user_id=user_id, workflow_name=workflow_name)
        api_key = apikey_info["api_key"]
        return DifyClient(
            dify_url=dify_url,
            access_api_key=api_key,
            workflow_name=workflow_name,
            user_id=platform_user,
        )

    @staticmethod
    def _mask_secret(value: Optional[str], prefix: int = 4, suffix: int = 4) -> str:
        if not value:
            return ""
        if len(value) <= prefix + suffix:
            return "*" * len(value)
        return f"{value[:prefix]}***{value[-suffix:]}"
