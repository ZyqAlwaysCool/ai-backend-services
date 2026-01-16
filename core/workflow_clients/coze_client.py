'''
Description: coze平台client, 封装coze平台接口
Author: zyq
Date: 2025-11-18 10:18:42
LastEditors: zyq
LastEditTime: 2025-11-20 15:44:44
'''
import json
from functools import lru_cache
from pathlib import Path

from loguru import logger
from typing import Optional, Dict, Any, AsyncGenerator, List, Tuple

from cozepy import (
    COZE_CN_BASE_URL,
    AsyncCoze,
    AsyncJWTAuth,
    AsyncJWTOAuthApp,
    AsyncTokenAuth,
    ChatEventType,
    ChatStatus,
    Coze,
    JWTOAuthApp,
    JWTAuth,
    Message,
    MessageObjectString,
    MessageRole,
    MessageType,
    TokenAuth,
)
from .base_workflow import BaseWorkflowClient, WorkflowResponse

_IMAGE_FILE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".gif",
    ".webp",
}

_DEFAULT_OAUTH_TOKEN_TTL = 3600
_MIN_OAUTH_TOKEN_TTL = 60
_MAX_OAUTH_TOKEN_TTL = 24 * 60 * 60


def _normalize_token_ttl(token_ttl: Optional[int]) -> int:
    """确保TTL处于coze平台要求范围"""
    ttl = token_ttl if isinstance(token_ttl, int) else _DEFAULT_OAUTH_TOKEN_TTL
    if ttl < _MIN_OAUTH_TOKEN_TTL:
        ttl = _MIN_OAUTH_TOKEN_TTL
    if ttl > _MAX_OAUTH_TOKEN_TTL:
        ttl = _MAX_OAUTH_TOKEN_TTL
    return ttl


@lru_cache(maxsize=64)
def _get_oauth_auth(
    client_id: str,
    pub_key: str,
    pri_key: str,
    ttl: int,
) -> Tuple[JWTAuth, AsyncJWTAuth]:
    """缓存oauth_app, 避免频繁重新创建并触发token刷新"""
    oauth_app = JWTOAuthApp(
        client_id=client_id,
        private_key=pri_key,
        public_key_id=pub_key,
        base_url=COZE_CN_BASE_URL
    )
    async_oauth_app = AsyncJWTOAuthApp(
        client_id=client_id,
        private_key=pri_key,
        public_key_id=pub_key,
        base_url=COZE_CN_BASE_URL
    )
    return (
        JWTAuth(oauth_app=oauth_app, ttl=ttl),
        AsyncJWTAuth(oauth_app=async_oauth_app, ttl=ttl),
    )

class CozeResponse(WorkflowResponse):
    pass

class CozeClient(BaseWorkflowClient):
    def __init__(self, access_api_key: str, bot_id: Optional[str] = None, workflow_name: Optional[str] = None, user_id: Optional[str] = None):
        """主要的构造函数：通过API Key初始化client"""
        self.coze_client = Coze(auth=TokenAuth(access_api_key), base_url=COZE_CN_BASE_URL)  # 同步client用于block模式
        self.async_coze_client = AsyncCoze(auth=AsyncTokenAuth(access_api_key), base_url=COZE_CN_BASE_URL)  # 异步client用于stream模式
        self.bot_id = bot_id
        self.workflow_name = workflow_name
        self.user_id = user_id

    @classmethod
    def with_access_token(cls, access_token: str, workflow_name: str, user_id: str):
        """通过个人token初始化client"""
        return cls(access_api_key=access_token, workflow_name=workflow_name, user_id=user_id)

    @classmethod
    def with_oauth(
        cls,
        client_id: str,
        pub_key: str,
        pri_key: str,
        workflow_name: str,
        user_id: str,
        token_ttl: Optional[int] = None,
    ):
        """通过oauth信息初始化client"""
        ttl = _normalize_token_ttl(token_ttl)
        sync_auth, async_auth = _get_oauth_auth(
            client_id=client_id,
            pub_key=pub_key,
            pri_key=pri_key,
            ttl=ttl,
        )

        # 创建实例并设置属性
        instance = cls.__new__(cls)
        instance.coze_client = Coze(auth=sync_auth, base_url=COZE_CN_BASE_URL)
        instance.async_coze_client = AsyncCoze(auth=async_auth, base_url=COZE_CN_BASE_URL)
        instance.workflow_name = workflow_name
        instance.user_id = user_id
        instance.bot_id = None

        return instance
    
    @staticmethod
    def _normalize_message_content(content: Any) -> str:
        """将coze返回的content/ reasoning_content统一处理为字符串"""
        if not content:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            return content.get("delta") or content.get("text") or content.get("content") or ""
        if isinstance(content, list):
            normalized = []
            for item in content:
                if isinstance(item, str):
                    normalized.append(item)
                elif isinstance(item, dict):
                    normalized.append(item.get("delta") or item.get("text") or item.get("content") or "")
                else:
                    normalized.append(
                        getattr(item, "delta", "") or getattr(item, "text", "") or getattr(item, "content", "") or str(item)
                    )
            return "".join(normalized)
        return str(content)

    @staticmethod
    def _build_sse_chunk(payload: Dict[str, Any]) -> str:
        """格式化SSE数据块"""
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def chat_stream(
        self,
        query: str,
        bot_id: str,
        inputs: Optional[Dict[str, Any]] = None,
        files: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[str, None]:
        """
        ref: https://www.coze.cn/open/docs/developer_guides/chat_v3#38cb7046
        """
        additional_messages = self._build_additional_messages(query, files)
        stream = self.async_coze_client.chat.stream(
            bot_id=bot_id,
            user_id=self.user_id,
            additional_messages=additional_messages,
            parameters=inputs if inputs else None,
        )

        try:
            async for event in stream:
                if event.event == ChatEventType.CONVERSATION_MESSAGE_DELTA:
                    reasoning_content = self._normalize_message_content(
                        getattr(event.message, "reasoning_content", None)
                    )
                    answer_content = self._normalize_message_content(
                        getattr(event.message, "content", None)
                    )
                    chunk = {
                        "event": event.event.value if hasattr(event.event, "value") else str(event.event),
                        "content": answer_content,
                        "reasoning_content": reasoning_content,
                        "conversation_id": getattr(event.message, "conversation_id", ""),
                        "message_id": getattr(event.message, "id", ""),
                    }
                    if answer_content or reasoning_content:
                        yield self._build_sse_chunk(chunk)

                elif event.event == ChatEventType.CONVERSATION_CHAT_COMPLETED:
                    usage = {}
                    if getattr(event, "chat", None) and getattr(event.chat, "usage", None):
                        try:
                            usage = event.chat.usage.model_dump()
                        except AttributeError:
                            usage = getattr(event.chat.usage, "__dict__", {})
                    chunk = {
                        "event": event.event.value if hasattr(event.event, "value") else str(event.event),
                        "finish_reason": "stop",
                        "conversation_id": getattr(event.chat, "conversation_id", ""),
                        "message_id": getattr(event.chat, "last_message_id", ""),
                        "usage": usage,
                    }
                    yield self._build_sse_chunk(chunk)
                    break

                elif event.event == ChatEventType.CONVERSATION_CHAT_FAILED:
                    error_msg = ""
                    if getattr(event, "chat", None) and getattr(event.chat, "last_error", None):
                        error_msg = getattr(event.chat.last_error, "msg", "") or str(event.chat.last_error)
                    chunk = {
                        "event": event.event.value if hasattr(event.event, "value") else str(event.event),
                        "finish_reason": "error",
                        "error": error_msg or "coze chat failed",
                    }
                    yield self._build_sse_chunk(chunk)
                    break
        except Exception as exc:
            logger.exception(f"coze chat stream failed workflow_name=({self.workflow_name}) error=({exc})")
            error_chunk = {
                "event": "error",
                "finish_reason": "error",
                "error": str(exc),
            }
            yield self._build_sse_chunk(error_chunk)
            raise
        finally:
            close_fn = getattr(stream, "aclose", None)
            if callable(close_fn):
                await close_fn()
    
    async def workflow_stream(
        self,
        workflow_id: str,
        bot_id: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[str, None]:
        """Coze workflow stream_run"""        
        stream = self.async_coze_client.workflows.runs.stream(
            workflow_id=workflow_id,
            bot_id=bot_id,
            parameters=parameters,
        )
        try:
            async for event in stream:
                message = event.message.model_dump() if event.message else None  
                payload = {
                    "event": getattr(event, "event", ""),
                    "message": message,
                    "error": getattr(getattr(event, "error", None), "__dict__", None),
                    "interrupt": getattr(getattr(event, "interrupt", None), "__dict__", None),
                }
                yield self._build_sse_chunk(payload)
        except Exception as exc:
            logger.exception(f"coze workflow stream failed workflow_name=({self.workflow_name}) error=({exc})")
            error_chunk = {
                "event": "error",
                "finish_reason": "error",
                "error": str(exc),
            }
            yield self._build_sse_chunk(error_chunk)
            raise
        finally:
            close_fn = getattr(stream, "aclose", None)
            if callable(close_fn):
                await close_fn()

    def workflow_block(
        self,
        workflow_id: str,
        bot_id: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> CozeResponse:
        """Coze workflow create (non-stream)"""
        try:
            resp = self.coze_client.workflows.runs.create(
                workflow_id=workflow_id,
                bot_id=bot_id,
                parameters=parameters,
            )
            data = getattr(resp, "__dict__", {})
            return CozeResponse.success(data=data)
        except Exception as exc:
            logger.error(f"coze workflow block failed workflow_name=({self.workflow_name}) error=({exc})")
            return CozeResponse.error(msg=str(exc))

    def chat_block(
        self,
        query: str,
        bot_id: str,
        inputs: Optional[Dict[str, Any]] = None,
        files: Optional[List[Dict[str, Any]]] = None
    ) -> CozeResponse:
        """
        ref: https://github.com/coze-dev/coze-py/blob/main/examples/chat_no_stream.py
        """
        logger.info(f"start chat block. workflow_name=({self.workflow_name}) query=({query}) bot_id=({bot_id}) inputs=({inputs})")
        additional_messages = self._build_additional_messages(query, files)
        chat_poll = self.coze_client.chat.create_and_poll(
            bot_id=bot_id,
            user_id=self.user_id,
            additional_messages=additional_messages,
            parameters=inputs if inputs else None,
        )

        if chat_poll.chat.status == ChatStatus.COMPLETED:
            for message in chat_poll.messages:
                if message.type == MessageType.ANSWER and message.role == MessageRole.ASSISTANT:
                    llm_answer = message
                    return CozeResponse.success(
                        data={
                            "answer": llm_answer.content,
                            "usages": chat_poll.chat.usage.model_dump(),
                            "conversation_id": llm_answer.conversation_id,
                            "message_id": llm_answer.id
                        })
        else:
            logger.error(f"chat failed: {chat_poll.chat.last_error}")
            return CozeResponse.error(msg=chat_poll.chat.last_error.msg)

    async def upload_file(self, file_path: str) -> CozeResponse:
        """异步上传文件到Coze平台"""
        logger.info(f"upload file to coze. file_path=({file_path})")
        path = Path(file_path)
        if not path.exists():
            return CozeResponse.error(msg=f"文件不存在: {file_path}")

        try:
            uploaded = await self.async_coze_client.files.upload(file=path)
            data = {
                "file_id": uploaded.id,
                "file_name": uploaded.file_name or path.name,
                "bytes": uploaded.bytes,
                "created_at": uploaded.created_at,
            }
            return CozeResponse.success(data=data)
        except Exception as exc:
            logger.error(f"coze upload file failed. error=({exc})")
            return CozeResponse.error(msg=str(exc))

    async def list_conversations(
        self,
        bot_id: str,
        page_num: int = 1,
        page_size: int = 20,
    ) -> CozeResponse:
        """获取会话列表"""
        page_num = page_num if page_num > 0 else 1
        page_size = page_size if page_size > 0 else 20
        logger.info(
            "list coze conversations workflow_name=({}) bot_id=({}) page_num=({}) page_size=({})",
            self.workflow_name,
            bot_id,
            page_num,
            page_size,
        )
        try:
            conversations_page = await self.async_coze_client.conversations.list(
                bot_id=bot_id,
                page_num=page_num,
                page_size=page_size,
            )
        except Exception as exc:
            logger.error(
                "coze list conversations failed workflow_name=({}) bot_id=({}) error=({})",
                self.workflow_name,
                bot_id,
                exc,
            )
            return CozeResponse.error(msg=str(exc))

        try:
            conversations = [
                conversation.model_dump(exclude_none=True)
                for conversation in conversations_page.items
            ]
        except Exception as exc:
            logger.error(
                "normalize coze conversations failed workflow_name=({}) bot_id=({}) error=({})",
                self.workflow_name,
                bot_id,
                exc,
            )
            return CozeResponse.error(msg=str(exc))

        return CozeResponse.success(
            data={
                "conversations": conversations,
                "has_more": conversations_page.has_more,
                "page_num": page_num,
                "page_size": page_size,
            }
        )

    def _build_additional_messages(
        self,
        query: str,
        files: Optional[List[Dict[str, Any]]]
    ) -> List[Message]:
        """根据query与文件信息构造additional_messages"""
        if not files:
            return [Message.build_user_question_text(query)]

        message_objects = [MessageObjectString.build_text(query)]
        for file_info in files:
            file_id = file_info.get("file_id") or file_info.get("id")
            if not file_id:
                continue
            file_name = file_info.get("file_name") or ""
            suffix = Path(file_name).suffix.lower()
            try:
                if suffix in _IMAGE_FILE_SUFFIXES:
                    message_objects.append(MessageObjectString.build_image(file_id=file_id))
                else:
                    message_objects.append(MessageObjectString.build_file(file_id=file_id))
            except ValueError as exc:
                logger.warning(f"skip invalid coze file payload. file_id=({file_id}) error=({exc})")

        if len(message_objects) == 1:
            return [Message.build_user_question_text(query)]

        return [Message.build_user_question_objects(message_objects)]
        
