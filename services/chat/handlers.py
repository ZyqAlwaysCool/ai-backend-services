'''
Description: 对话类服务业务逻辑处理器
Author: zyq
Date: 2025-08-26 11:19:24
LastEditors: zyq
LastEditTime: 2025-11-21 15:10:04
'''
from fastapi import UploadFile
from typing import Dict, Any, AsyncGenerator, List, Union, Optional
from loguru import logger
import uuid
from datetime import datetime
from pathlib import Path
import json

from core.config import load_llm_cfg, get_app_config
from core.config.error_codes import COMMON_ERROR_REQUEST_PARSE_ERROR
from ..services_err_codes import *
from core.exceptions import ValidationException, BaseBusinessException, WorkflowException
from .schemas import *
from .adapters import ProtocolAdapterFactory, LLMProtocolAdapter
from core.storage.mongo_storage import MongoStorage
import os
from typing import cast
from .platforms.dify_adapter import DifyPlatformAdapter
from .platforms.coze_adapter import CozePlatformAdapter
from .platforms.credential_service import CredentialService


class ChatHandlers:
    """Chat服务纯业务逻辑处理器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled_models = config.get('enabled_models', [])
        self.rate_limits = config.get('rate_limits', {})

        # 加载LLM配置
        self.llm_config = load_llm_cfg("openai")
        self.models_info = {model.name: model for model in self.llm_config.models}

        # 加载应用配置
        self.app_config = get_app_config()

        # 协议适配器缓存
        self._adapters = {}

        # 初始化存储器
        chat_db_name = config.get("chat_db_name", "ai_backend_services_chat")
        self._chatflow_apikey_storage = MongoStorage(
            db_name=chat_db_name,
            collection_name=config.get("chat_apikey_collection_name", "chat_apikey")
        )
        self._workflow_apikey_storage = MongoStorage(
            db_name=chat_db_name,
            collection_name=config.get("workflow_apikey_collection_name", "workflow_apikey")
        )
        self._chatflow_oauth_storage = MongoStorage(
            db_name=chat_db_name,
            collection_name=config.get("chat_oauth_collection_name", "chat_oauth")
        )
        self._workflow_oauth_storage = MongoStorage(
            db_name=chat_db_name,
            collection_name=config.get("workflow_oauth_collection_name", "workflow_oauth")
        )
        self._coze_auth_mode = config.get("coze_auth_mode", "api_key").lower()
        if self._coze_auth_mode not in {"api_key", "oauth"}:
            logger.warning(f"Invalid coze_auth_mode={self._coze_auth_mode}, fallback to api_key")
            self._coze_auth_mode = "api_key"
        self._coze_oauth_token_ttl = config.get("coze_oauth_token_ttl", 3600)

        # 额外的配置初始化, 后续可迁移到services.yml中
        self.__chatflow_uploadfiles_limit = 5  # 单次上传文件数量上限
        self.__chatflow_singlefile_maxsize = 30 * 1024 * 1024  # 单个文件最大大小限制(MB)
        self.__workflow_uploadfiles_limit = 5  # 单次上传文件数量上限
        self.__workflow_singlefile_maxsize = 30 * 1024 * 1024  # 单个文件最大大小限制(MB)

        # 鉴权/客户端服务
        self._credential_service = CredentialService(
            chatflow_apikey_storage=self._chatflow_apikey_storage,
                workflow_apikey_storage=self._workflow_apikey_storage,
            chatflow_oauth_storage=self._chatflow_oauth_storage,
                workflow_oauth_storage=self._workflow_oauth_storage,
            coze_auth_mode=self._coze_auth_mode,
            coze_oauth_token_ttl=self._coze_oauth_token_ttl,
        )

        # 平台适配器
        self._chatflow_adapters = {
            ChatFlowPlatform.DIFY: DifyPlatformAdapter(
                credential_service=self._credential_service,
                get_files_info=self._get_dify_files_info,
                chatflow_upload_limit=self.__chatflow_uploadfiles_limit,
                chatflow_singlefile_maxsize=self.__chatflow_singlefile_maxsize,
                workflow_upload_limit=self.__workflow_uploadfiles_limit,
                workflow_singlefile_maxsize=self.__workflow_singlefile_maxsize,
                safe_json_loads=self._safe_json_loads,
                normalize_workflow_status=self._normalize_workflow_status,
            ),
            ChatFlowPlatform.COZE: CozePlatformAdapter(
                credential_service=self._credential_service,
                get_files_info=self._get_coze_files_info,
                chatflow_upload_limit=self.__chatflow_uploadfiles_limit,
                singlefile_maxsize=self.__chatflow_singlefile_maxsize,
            )
        }
        
    
    async def initialize(self):
        """初始化处理器"""
        # 预初始化所有配置的模型适配器
        await self._initialize_adapters()
    
    async def _initialize_adapters(self):
        """初始化协议适配器"""
        for model_name, model_info in self.models_info.items():
            if model_name in self.enabled_models:
                try:
                    # 根据配置中的provider字段确定协议类型
                    protocol = self.llm_config.provider
                    
                    adapter = ProtocolAdapterFactory.create_adapter(
                        protocol=protocol,
                        model_config=model_info.dict(),
                        timeout=self.llm_config.timeout
                    )
                    
                    self._adapters[model_name] = adapter
                    
                except Exception as e:
                    logger.error(f"Failed to initialize adapter model={model_name} error={str(e)}")
                    continue
    
    
    def _validate_model(self, model: str):
        """验证模型是否在配置中启用"""
        if model not in self.enabled_models:
            raise ValidationException(
                f"模型 {model} 不可用。可用模型: {', '.join(self.enabled_models)}"
            )
    
    def _get_dify_files_info(self, request: Union[ChatFlowRequest, WorkflowRequest]) -> List[Dict[str, Any]]:
        dify_files = []
        if request.files:
            document_exts = {
                'TXT', 'MD', 'MARKDOWN', 'MDX', 'PDF', 'HTML', 'XLSX', 'XLS',
                'VTT', 'PROPERTIES', 'DOC', 'DOCX', 'CSV', 'EML', 'MSG',
                'PPTX', 'PPT', 'XML', 'EPUB'
            }
            for file_info in request.files:
                suffix = Path(file_info.file_name).suffix
                ext_upper = suffix.lstrip('.').upper() if suffix else ""
                file_type = "document" if ext_upper in document_exts else "image" # TODO: 目前只适配dify最常用的文件类型. video/audio等后续支持
                dify_chatflow_file_info = DifyFileInfo(
                    upload_file_id=file_info.file_id,
                    type=file_type,
                    transfor_method=DifyFileTransferMethod.LOCAL_FILE
                )
                dify_files.append(dify_chatflow_file_info.model_dump())
        
        return dify_files

    def _get_coze_files_info(self, request: ChatFlowRequest) -> List[Dict[str, Any]]:
        """将请求中的文件列表转换为coze可识别的格式"""
        coze_files = []
        if request.files:
            for file_info in request.files:
                coze_files.append({
                    "file_id": file_info.file_id,
                    "file_name": file_info.file_name,
                })
        return coze_files

    @staticmethod
    def _safe_json_loads(value: Any, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """安全解析JSON字符串, 已是dict则直接返回, 其它类型返回default"""
        if value is None:
            return default.copy() if isinstance(default, dict) else {}
        if isinstance(value, dict):
            return value
        if isinstance(value, (bytes, bytearray)):
            try:
                value = value.decode()
            except Exception as exc:
                logger.warning(f"failed to decode bytes json payload type=({type(value)}) error=({exc})")
                return default.copy() if isinstance(default, dict) else {}
        if isinstance(value, str):
            if value.strip() == "":
                return default.copy() if isinstance(default, dict) else {}
            try:
                return cast(Dict[str, Any], json.loads(value))
            except Exception as exc:
                logger.warning(f"failed to json.loads value=({value}) error=({exc})")
                return default.copy() if isinstance(default, dict) else {}
        logger.warning(f"unexpected type for json loads type=({type(value)}) value=({value})")
        return default.copy() if isinstance(default, dict) else {}

    @staticmethod
    def _normalize_workflow_status(status_value: Any) -> WorkflowRunStatus:
        """将外部状态值转换为内部枚举, 未知状态兜底为FAILED"""
        if isinstance(status_value, WorkflowRunStatus):
            return status_value
        try:
            return WorkflowRunStatus(status_value)
        except Exception:
            logger.warning(f"unexpected workflow status=({status_value}), fallback to FAILED")
            return WorkflowRunStatus.FAILED

    def _validate_request_params(self, temperature: float = None, max_tokens: int = None):
        """验证请求参数"""
        if temperature is not None and not (0.0 <= temperature <= 1.0):
            raise ValidationException("temperature 必须在 0.0 到 1.0 之间")
        
        if max_tokens is not None and not (1 <= max_tokens <= 8000):
            raise ValidationException("max_tokens 必须在 1 到 8000 之间")
    
    def _get_adapter(self, model: str) -> LLMProtocolAdapter:
        """获取模型对应的协议适配器"""
        if model not in self._adapters:
            raise ValidationException(f"模型 {model} 适配器未找到")
        return self._adapters[model]
    
    def _build_messages(self, query: str, system_prompt: str = None, history: List = None) -> List[Dict[str, str]]:
        """构建消息列表"""
        messages = []
        
        if system_prompt:
            messages.append({
                'role': MessageRole.SYSTEM.value,
                'content': system_prompt
            })
        
        if history:
            for msg in history:
                messages.append({
                    'role': msg.role,
                    'content': msg.content
                })
        
        messages.append({
            'role': MessageRole.USER.value,
            'content': query
        })
        
        return messages
    
    async def chat(self, request: ChatRequest, trace_id: str = None) -> ChatResponse:
        """统一对话处理（单轮/多轮由history字段判断)"""
        is_multi_turn = len(request.history) > 0
        conversation_type = "multi-turn" if is_multi_turn else "single-turn"
        
        
        try:
            # 参数验证
            self._validate_model(request.model)
            self._validate_request_params(request.temperature, request.max_tokens)
            
            # 构建消息列表
            messages = self._build_messages(
                query=request.query,
                system_prompt=request.system_prompt,
                history=request.history if is_multi_turn else None
            )
            
            # 获取协议适配器并调用
            adapter = self._get_adapter(request.model)
            response = await adapter.chat_completion(
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens
            )
            
            return response
                
        except Exception as e:
            logger.error(f"{conversation_type} conversation failed error={str(e)} | TraceID: {trace_id}")
            if isinstance(e, (ValidationException, BaseBusinessException)):
                raise
            else:
                raise BaseBusinessException(
                    code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                    message=f"{conversation_type}对话处理失败: {str(e)}"
                )
    
    async def chat_stream(self, request: ChatRequest, trace_id: str = None) -> AsyncGenerator[StreamChatChunk, None]:
        """统一流式对话处理（单轮/多轮由history字段判断）"""
        is_multi_turn = len(request.history) > 0
        conversation_type = "multi-turn" if is_multi_turn else "single-turn"
        
        
        try:
            # 参数验证
            self._validate_model(request.model)
            self._validate_request_params(request.temperature, request.max_tokens)
            
            # 构建消息列表
            messages = self._build_messages(
                query=request.query,
                system_prompt=request.system_prompt,
                history=request.history if is_multi_turn else None
            )
            
            # 获取协议适配器并调用
            adapter = self._get_adapter(request.model)
            async for chunk in adapter.chat_completion_stream(
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens
            ):
                yield chunk
                
        except Exception as e:
            logger.error(f"{conversation_type} stream conversation failed error={str(e)} | TraceID: {trace_id}")
            if isinstance(e, (ValidationException, BaseBusinessException)):
                raise
            else:
                raise BaseBusinessException(
                    code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                    message=f"{conversation_type}流式对话处理失败: {str(e)}"
                )
    
    def get_enabled_models(self) -> List[str]:
        """获取启用的模型列表"""
        return self.enabled_models.copy()

# ========================对话流相关接口适配========================
    
    def add_chatflow_apikey_info(self, request: AddChatFlowApiKeyRequest, user_id: str, trace_id: str = None) -> AddChatFlowApiKeyResponse:
        """添加对话流API key信息"""
        logger.info(f"add chatflow apikey info - TraceID: {trace_id}")
        real_key_id = "chatflow_apikey_" + str(uuid.uuid4())[:8]
        apikey_info = ChatFlowApiKeyInfo(
            key_id=real_key_id,
            user_id=user_id,
            chatflow_name=request.chatflow_name,
            platform=request.platform,
            api_key=request.api_key,
            description=request.description,
            status=ApiKeyStatus.ACTIVE,
            created_at=datetime.utcnow(),
            bot_id=request.bot_id,
        )
        self._credential_service.add_chatflow_apikey(apikey_info)
        return AddChatFlowApiKeyResponse(key_id=real_key_id)
    
    def get_chatflow_apikey_info(self, user_id: str, trace_id: str = None) -> GetChatFlowApiKeyResponse:
        """获取用户的对话流API key信息列表"""
        logger.info(f"get chatflow apikey info - TraceID: {trace_id}")
        records = self._credential_service.list_chatflow_apikey(user_id=user_id)
        resp = GetChatFlowApiKeyResponse()
        for record in records:
            resp.api_keys_info.append(record)
        return resp
    
    def update_chatflow_apikey_info(self, request: UpdateChatFlowApiKeyRequest, user_id: str, trace_id: str = None) -> UpdateChatFlowApiKeyResponse:
        """更新对话流API key信息"""
        logger.info(f"update chatflow apikey info - TraceID: {trace_id}")
        records = self._credential_service.list_chatflow_apikey(user_id=user_id)
        # 找指定的记录
        apikey_info = None
        for r in records:
            if r.chatflow_name == request.chatflow_name and r.platform == request.platform:
                apikey_info = r
                break
        if not apikey_info:
            raise ValidationException(f"用户=({user_id}) 不存在此chatflow apikey记录. req=({request})")

        updated_info = ChatFlowApiKeyInfo(
            key_id=apikey_info.key_id,
            user_id=user_id,
            chatflow_name=request.chatflow_name,
            platform=request.platform,
            api_key=request.api_key,
            description=request.description,
            status=ApiKeyStatus.ACTIVE,
            created_at=datetime.utcnow(),
            bot_id=request.bot_id,
        )
        self._credential_service.update_chatflow_apikey(updated_info)
        return UpdateChatFlowApiKeyResponse(key_id=updated_info.key_id)



    def add_chatflow_oauth_info(self, request: AddOAuthInfoRequest, user_id: str, trace_id: str = None) -> AddOauthInfoResponse:
        """添加Coze OAuth配置"""
        logger.info(f"add chatflow oauth info - TraceID: {trace_id}")
        oauth_key_id = "chatflow_oauth_" + str(uuid.uuid4())[:8]
        oauth_info = JWTOauthInfo(
            oauth_key_id=oauth_key_id,
            user_id=user_id,
            chatflow_name=request.chatflow_name,
            bot_id=request.bot_id,
            oauth_name=request.oauth_name,
            oauth_client_id=request.oauth_client_id,
            oauth_public_key=request.oauth_public_key,
            oauth_private_key=request.oauth_private_key,
            status=ApiKeyStatus.ACTIVE,
            created_at=datetime.utcnow()
        )

        self._credential_service.add_chatflow_oauth(oauth_info)

        return AddOauthInfoResponse(oauth_key_id=oauth_key_id)

    def get_chatflow_oauth_info(self, user_id: str, trace_id: str = None) -> GetOauthInfoResponse:
        """获取用户的Coze OAuth配置列表"""
        logger.info(f"get chatflow oauth info list - TraceID: {trace_id}")
        records = self._credential_service.list_chatflow_oauth(user_id=user_id)
        resp = GetOauthInfoResponse()
        for record in records:
            resp.oauth_info.append(record)
        return resp

    def update_chatflow_oauth_info(self, request: UpdateOAuthInfoRequest, user_id: str, trace_id: str = None) -> UpdateOauthInfoResponse:
        """更新Coze OAuth配置"""
        logger.info(f"update chatflow oauth info - TraceID: {trace_id}")
        if not any([request.bot_id, request.oauth_client_id, request.oauth_public_key, request.oauth_private_key, request.oauth_name]):
            raise ValidationException("请至少提供一个需要更新的字段")
        updated_data = {
            "bot_id": request.bot_id,
            "oauth_name": request.oauth_name,
            "oauth_client_id": request.oauth_client_id,
            "oauth_public_key": request.oauth_public_key,
            "oauth_private_key": request.oauth_private_key,
        }
        oauth_key_id = self._credential_service.update_chatflow_oauth(
            chatflow_name=request.chatflow_name,
            user_id=user_id,
            updated=updated_data,
        )
        return UpdateOauthInfoResponse(oauth_key_id=oauth_key_id)


    async def upload_files_to_chatflow_platform(self,
                                                request: UploadFilesToChatFlowPlatformRequest,
                                                login_user: str, #鉴权用户
                                                files: List[UploadFile],
                                                trace_id: str = None) -> UploadFilesToChatFlowPlatformResponse:
        """上传文件到对话流平台"""
        logger.info(f"upload files to chatflow platform - TraceID: {trace_id}")

        adapter = self._chatflow_adapters.get(request.platform)
        if not adapter:
            raise ValidationException(f"暂不支持平台: {request.platform}")

        uploaded_files_info = await adapter.upload_files(
            request=request,
            login_user=login_user,
            files=files,
            trace_id=trace_id,
        )
        return UploadFilesToChatFlowPlatformResponse(file_info_list=uploaded_files_info)

    async def upload_files_to_workflow_platform(self,
                                                request: UploadFilesToWorkflowPlatformRequest,
                                                login_user: str, #鉴权用户
                                                files: List[UploadFile],
                                                trace_id: str = None) -> UploadFilesToWorkflowPlatformResponse:
        """上传文件到workflow平台"""
        logger.info(f"upload files to workflow platform - TraceID: {trace_id}")

        adapter = self._chatflow_adapters.get(request.platform)
        if not adapter or not hasattr(adapter, "upload_workflow_files"):
            raise ValidationException(f"暂不支持平台: {request.platform}")

        return await adapter.upload_workflow_files(
            request=request,
            login_user=login_user,
            files=files,
            trace_id=trace_id,
        )

    async def chatflow_block_mode(self, request: ChatFlowRequest, login_user: str, trace_id: str = None) -> ChatFlowBlockResponse:
        """对话流平台阻塞模式处理"""

        adapter = self._chatflow_adapters.get(request.platform)
        if not adapter:
            raise ValidationException(f"暂不支持平台: {request.platform}")

        result = await adapter.chat_block(request=request, login_user=login_user)
        return ChatFlowBlockResponse(
            answer=result.get("answer", ""),
            conversation_id=result.get("conversation_id", ""),
            message_id=result.get("message_id", ""),
            metadata=result.get("metadata"),
        )
        
    async def chatflow_stream_mode(self, request: ChatFlowRequest, login_user: str, trace_id: str = None) -> AsyncGenerator[str, None]:
        """对话流平台流式模式处理"""
        adapter = self._chatflow_adapters.get(request.platform)
        if not adapter:
            raise ValidationException(f"暂不支持平台: {request.platform}")

        async for chunk in adapter.chat_stream(request=request, login_user=login_user):
            yield chunk
    
    async def stop_chatflow_task(self, request: StopChatTaskRequest, login_user: str, trace_id: str = None):
        """基于task_id停止对话流平台的当前任务"""
        logger.info(f"stop chatflow task - TraceID: {trace_id} task_id={request.task_id} user={login_user}")

        adapter = self._chatflow_adapters.get(request.platform)
        if not adapter or not hasattr(adapter, "stop_chatflow_task"):
            raise ValidationException(f"暂不支持平台: {request.platform}")

        return await adapter.stop_chatflow_task(request=request, login_user=login_user)

    async def add_feedbacks(self, request: AddFeedBacksRequest, login_user: str, trace_id: str = None):
        """添加消息反馈"""
        logger.info(f"add feedbacks - TraceID: {trace_id} message_id={request.message_id} rating={request.rating}")

        adapter = self._chatflow_adapters.get(request.platform)
        if not adapter or not hasattr(adapter, "add_feedbacks"):
            raise ValidationException(f"暂不支持平台: {request.platform}")

        return await adapter.add_feedbacks(request=request, login_user=login_user)

    async def get_feedbacks(self, request: GetFeedBacksRequest, login_user: str, trace_id: str = None):
        """获取APP的消息点赞和反馈"""
        logger.info(f"get feedbacks - TraceID: {trace_id} page={request.page} limit={request.limit}")

        adapter = self._chatflow_adapters.get(request.platform)
        if not adapter or not hasattr(adapter, "get_feedbacks"):
            raise ValidationException(f"暂不支持平台: {request.platform}")

        return await adapter.get_feedbacks(request=request, login_user=login_user)

    async def add_suggested_questions(self, request: AddSuggestedQuestionsRequest, login_user: str, trace_id: str = None):
        """添加建议问题"""
        logger.info(f"add suggested questions - TraceID: {trace_id} message_id={request.message_id}")

        adapter = self._chatflow_adapters.get(request.platform)
        if not adapter or not hasattr(adapter, "add_suggested_questions"):
            raise ValidationException(f"暂不支持平台: {request.platform}")

        return await adapter.add_suggested_questions(request=request, login_user=login_user)

    async def get_history_message(self, request: GetHistoryMessageRequest, login_user: str, trace_id: str = None) -> GetHistoryMessageResponse:
        """获取单个会话的历史消息"""
        logger.info(f"get history message - TraceID: {trace_id} conversation_id={request.conversation_id}")

        adapter = self._chatflow_adapters.get(request.platform)
        if not adapter or not hasattr(adapter, "get_history_message"):
            raise ValidationException(f"暂不支持平台: {request.platform}")

        return await adapter.get_history_message(request=request, login_user=login_user)

    async def get_conversation_list(self, request: GetConversationListRequest, login_user: str, trace_id: str = None):
        """获取会话列表"""
        logger.info(f"get conversation list - TraceID: {trace_id} last_id={request.last_id} limit={request.limit}")

        adapter = self._chatflow_adapters.get(request.platform)
        if not adapter:
            raise ValidationException(f"暂不支持平台: {request.platform}")

        resp_data = await adapter.list_conversations(request=request, login_user=login_user)

        if resp_data is None:
            return ConversationListResponse().model_dump()

        if request.platform == ChatFlowPlatform.DIFY:
            dify_data = resp_data if isinstance(resp_data, dict) else {}
            conversations = dify_data.get("data") or dify_data.get("items") or []
            list_resp = ConversationListResponse(
                conversations=conversations,
                has_more=dify_data.get("has_more"),
                cursor=ConversationListCursor(
                    last_id=dify_data.get("last_id"),
                    first_id=dify_data.get("first_id"),
                    page_size=dify_data.get("limit") or request.limit,
                ),
            )
            return list_resp.model_dump()

        coze_data = resp_data if isinstance(resp_data, dict) else {}
        page_num = coze_data.get("page_num")
        list_resp = ConversationListResponse(
            conversations=coze_data.get("conversations", []),
            has_more=coze_data.get("has_more"),
            cursor=ConversationListCursor(
                page_num=page_num,
                page_size=coze_data.get("page_size") or request.limit,
            ),
        )
        return list_resp.model_dump()

    async def delete_conversation(self, request: DeleteConversationRequest, login_user: str, trace_id: str = None):
        """删除会话"""
        logger.info(f"delete conversation - TraceID: {trace_id} conversation_id={request.conversation_id}")

        adapter = self._chatflow_adapters.get(request.platform)
        if not adapter or not hasattr(adapter, "delete_conversation"):
            raise ValidationException(f"暂不支持平台: {request.platform}")

        return await adapter.delete_conversation(request=request, login_user=login_user)

    async def rename_conversation(self, request: RenameConversationRequest, login_user: str, trace_id: str = None):
        """会话重命名"""
        logger.info(f"rename conversation - TraceID: {trace_id} conversation_id={request.conversation_id} name={request.name}")

        adapter = self._chatflow_adapters.get(request.platform)
        if not adapter or not hasattr(adapter, "rename_conversation"):
            raise ValidationException(f"暂不支持平台: {request.platform}")

        return await adapter.rename_conversation(request=request, login_user=login_user)

# ========================工作流相关接口适配========================
    def add_workflow_oauth_info(self, request: AddWorkFlowOAuthInfoRequest, user_id: str, trace_id: str = None) -> AddOauthInfoResponse:
        """添加Coze OAuth配置"""
        logger.info(f"add workflow oauth info - TraceID: {trace_id}")
        oauth_key_id = "workflow_oauth_" + str(uuid.uuid4())[:8]
        oauth_info = WorkFlowJWTOauthInfo(
            oauth_key_id=oauth_key_id,
            user_id=user_id,
            workflow_name=request.workflow_name,
            workflow_id=request.workflow_id,
            bot_id=request.bot_id,
            oauth_name=request.oauth_name,
            oauth_client_id=request.oauth_client_id,
            oauth_public_key=request.oauth_public_key,
            oauth_private_key=request.oauth_private_key,
            status=ApiKeyStatus.ACTIVE,
            created_at=datetime.utcnow()
        )

        self._credential_service.add_workflow_oauth(oauth_info)

        return AddOauthInfoResponse(oauth_key_id=oauth_key_id)
            
    async def workflow_block_mode(self, request: WorkflowRequest, login_user: str, trace_id: str = None) -> WorkflowBlockResponse:
        """工作流平台阻塞模式处理"""
        adapter = self._chatflow_adapters.get(request.platform)
        if not adapter or not hasattr(adapter, "workflow_block_mode"):
            raise ValidationException(f"暂不支持平台: {request.platform}")
        return await adapter.workflow_block_mode(request=request, login_user=login_user)
    
    async def workflow_stream_mode(self, request: WorkflowRequest, login_user: str, trace_id: str = None) -> AsyncGenerator[str, None]:
        adapter = self._chatflow_adapters.get(request.platform)
        if not adapter or not hasattr(adapter, "workflow_stream_mode"):
            raise ValidationException(f"暂不支持平台: {request.platform}")

        async for chunk in adapter.workflow_stream_mode(request=request, login_user=login_user):
            yield chunk

    async def get_workflow_run_status(self, request: GetWorkflowRunRequest, login_user: str, trace_id: str = None) -> GetWorkflowRunResponse:
        """获取workflow执行情况"""
        logger.info(f"get workflow run status - TraceID: {trace_id} workflow_run_id={request.workflow_run_id}")

        adapter = self._chatflow_adapters.get(request.platform)
        if not adapter or not hasattr(adapter, "get_workflow_run_status"):
            raise ValidationException(f"暂不支持平台: {request.platform}")

        return await adapter.get_workflow_run_status(request=request, login_user=login_user)

    async def stop_workflow_task(self, request: StopWorkflowTaskRequest, login_user: str, trace_id: str = None) -> StopWorkflowTaskResponse:
        """停止workflow任务"""
        logger.info(f"stop workflow task - TraceID: {trace_id} task_id={request.task_id}")

        adapter = self._chatflow_adapters.get(request.platform)
        if not adapter or not hasattr(adapter, "stop_workflow_task"):
            raise ValidationException(f"暂不支持平台: {request.platform}")

        return await adapter.stop_workflow_task(request=request, login_user=login_user)

    async def get_workflow_logs(self, request: GetWorkflowLogsRequest, login_user: str, trace_id: str = None) -> GetWorkflowLogsResponse:
        """获取workflow日志"""
        logger.info(f"get workflow logs - TraceID: {trace_id} page={request.page} limit={request.limit}")

        adapter = self._chatflow_adapters.get(request.platform)
        if not adapter or not hasattr(adapter, "get_workflow_logs"):
            raise ValidationException(f"暂不支持平台: {request.platform}")

        return await adapter.get_workflow_logs(request=request, login_user=login_user)

    async def get_workspace_list(self, request: GetWorkspaceListRequest, login_user: str, trace_id: str = None) -> GetWorkspaceListResponse:
        """获取Coze工作空间列表"""
        logger.info(f"get workspace list - TraceID: {trace_id} page={request.page_num} page_size={request.page_size}")

        adapter = self._chatflow_adapters.get(request.platform)
        if not adapter or not hasattr(adapter, "list_workspaces"):
            raise ValidationException(f"暂不支持平台: {request.platform}")

        return await adapter.list_workspaces(request=request, login_user=login_user)

    async def get_app_base_info(self, request: GetAppBaseInfoRequest, login_user: str, trace_id: str = None) -> GetAppBaseInfoResponse:
        """获取应用基本信息"""
        logger.info(f"get app base info - TraceID: {trace_id} app_type=({request.app_type}) apikey_name=({request.apikey_name})")

        adapter = self._chatflow_adapters.get(request.platform)
        if not adapter or not hasattr(adapter, "get_app_base_info"):
            raise ValidationException(f"暂不支持平台: {request.platform}")

        return await adapter.get_app_base_info(request=request, login_user=login_user)

    async def get_webapp_info(self, request: GetWebAppInfoRequest, login_user: str, trace_id: str = None) -> GetWebAppInfoResponse:
        """获取应用WebApp设置"""
        logger.info(f"get webapp info - TraceID: {trace_id} app_type=({request.app_type}) apikey_name=({request.apikey_name})")

        adapter = self._chatflow_adapters.get(request.platform)
        if not adapter or not hasattr(adapter, "get_webapp_info"):
            raise ValidationException(f"暂不支持平台: {request.platform}")

        return await adapter.get_webapp_info(request=request, login_user=login_user)

    def add_workflow_apikey_info(self, request: AddWorkflowApiKeyRequest, user_id: str, trace_id: str = None) -> AddWorkflowApiKeyResponse:
        """添加工作流API key信息"""
        logger.info(f"add workflow apikey info - TraceID: {trace_id}")

        real_key_id = "workflow_apikey_" + str(uuid.uuid4())[:8]
        apikey_info = WorkflowApiKeyInfo(
            key_id=real_key_id,
            user_id=user_id,
            workflow_name=request.workflow_name,
            platform=request.platform,
            api_key=request.api_key,
            workflow_id=request.workflow_id,
            bot_id=request.bot_id,
            description=request.description,
            status=ApiKeyStatus.ACTIVE,
            created_at=datetime.utcnow(),
        )

        self._credential_service.add_workflow_apikey(apikey_info)

        return AddWorkflowApiKeyResponse(
            key_id=real_key_id,
        )

    def get_workflow_apikey_info(self, user_id: str, trace_id: str = None) -> GetWorkflowApiKeyResponse:
        """获取用户的工作流API key信息列表"""
        logger.info(f"get workflow apikey info - TraceID: {trace_id}")
        records = self._credential_service.list_workflow_apikey(user_id=user_id)
        # 补充bot_id对外为空时保留
        resp = GetWorkflowApiKeyResponse()
        resp.api_keys_info.extend(records)
        return resp

# ========================对话流相关接口适配========================

        
        
        
        
        
