'''
Description: 对话类服务业务逻辑处理器
Author: zyq
Date: 2025-08-26 11:19:24
LastEditors: zyq
LastEditTime: 2025-11-11 17:11:09
'''
from fastapi import UploadFile
from typing import Dict, Any, AsyncGenerator, List
from loguru import logger
import uuid
from datetime import datetime
import tempfile
from pathlib import Path
import asyncio

from core.config import load_llm_cfg, get_app_config
from core.config.error_codes import COMMON_ERROR_REQUEST_PARSE_ERROR
from ..services_err_codes import *
from core.exceptions import ValidationException, BaseBusinessException, WorkflowException
from .schemas import *
from .adapters import ProtocolAdapterFactory, LLMProtocolAdapter
from core.storage.mongo_storage import MongoStorage
from core.workflow_clients.dify_client import DifyClient
import os


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
        self._chatflow_apikey_storage = MongoStorage(db_name=config.get("chat_db_name", "ai_backend_services_chat"),
                                                     collection_name=config.get("chat_apikey_collection_name", "chat_apikey"))

        # 额外的配置初始化, 后续可迁移到services.yml中
        self.__chatflow_uploadfiles_limit = 5  # 单次上传文件数量上限
        self.__chatflow_singlefile_maxsize = 30 * 1024 * 1024  # 单个文件最大大小限制(MB)
        
    
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
    
    def _get_dify_chatflow_apikey_info(self, user_id: str, chatflow_name: str) -> Dict[str, Any]:
        filter_query = {
            "user_id": user_id,
            "chatflow_name": chatflow_name,
            "platform": ChatFlowPlatform.DIFY,
            "status": ApiKeyStatus.ACTIVE
        }
        records = self._chatflow_apikey_storage.find_record(filter_query)
        if len(records) == 0 or len(records) > 1:
            raise ValidationException(
                f"未找到用户 {user_id} 在DIFY平台的对话流 {chatflow_name} 的有效API Key"
            )
        return records[0]
    
    def _get_dify_files_info(self, request: ChatFlowRequest) -> List[Dict[str, Any]]:
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
                dify_chatflow_file_info = DifyChatFlowFileInfo(
                    upload_file_id=file_info.file_id,
                    type=file_type,
                    transfor_method=DifyChatFlowFileTransferMethod.LOCAL_FILE
                )
                dify_files.append(dify_chatflow_file_info.model_dump())
        
        return dify_files
    
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

# ========================工作流/对话流相关接口适配========================
    
    def add_chatflow_apikey_info(self, request: AddChatFlowApiKeyRequest, user_id: str, trace_id: str = None) -> AddChatFlowApiKeyResponse:
        """添加对话流API key信息"""
        logger.info(f"add chatflow apikey info - TraceID: {trace_id}")
        filter = {"user_id": user_id, "chatflow_name": request.chatflow_name, "platform": request.platform, "api_key": request.api_key}
        exist_records = self._chatflow_apikey_storage.find_record(filter)
        if len(exist_records) > 0:
            raise ValidationException("已存在相同的API key记录")
        
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
        )
        
        self._chatflow_apikey_storage.create_record(apikey_info.model_dump())
        
        return AddChatFlowApiKeyResponse(
            key_id=real_key_id,
        )
    
    def get_chatflow_apikey_info(self, user_id: str, trace_id: str = None) -> GetChatFlowApiKeyResponse:
        """获取用户的对话流API key信息列表"""
        logger.info(f"get chatflow apikey info - TraceID: {trace_id}")
        records = self._chatflow_apikey_storage.find_record({"user_id": user_id})
        if len(records) == 0:
            return GetChatFlowApiKeyResponse()
        
        resp = GetChatFlowApiKeyResponse()
        for record in records:
            if record["status"] == ApiKeyStatus.ACTIVE:
                chatflow_apikey_info = ChatFlowApiKeyInfo(**record)
                resp.api_keys_info.append(chatflow_apikey_info)
        
        return resp
    
    async def upload_files_to_chatflow_platform(self,
                                                request: UploadFilesToChatFlowPlatformRequest,
                                                login_user: str, #鉴权用户
                                                files: List[UploadFile],
                                                trace_id: str = None) -> UploadFilesToChatFlowPlatformResponse:
        """上传文件到对话流平台"""
        logger.info(f"upload files to chatflow platform - TraceID: {trace_id}")

        # 验证文件数量
        if len(files) > self.__chatflow_uploadfiles_limit:
            raise ValidationException(f"单次上传文件数量不能超过{self.__chatflow_uploadfiles_limit}个")

        # 目前只支持Dify平台
        if request.platform != ChatFlowPlatform.DIFY:
            raise ValidationException(f"暂不支持平台: {request.platform}")

        # 获取API Key
        apikey_info = self._get_dify_chatflow_apikey_info(user_id=login_user, chatflow_name=request.chatflow_name)
        api_key = apikey_info["api_key"]
        logger.info(f"found api key for user={login_user} key_id={apikey_info.get('key_id')}")

        # 获取Dify平台URL
        dify_url = self.app_config.dify_url
        logger.info(f"dify url from config: {dify_url}")

        # 创建DifyClient实例
        dify_client = DifyClient(
            dify_url=dify_url,
            access_api_key=api_key,
            workflow_name=request.chatflow_name,
            user_id=request.platform_user,
            timeout=120
        )

        # 存储上传结果
        uploaded_files_info = []
        temp_file_paths = []

        try:
            # 处理每个文件
            for file in files:
                # 读取文件内容用于大小校验
                content = await file.read()
                file_size = len(content)

                # 校验文件大小
                if file_size > self.__chatflow_singlefile_maxsize:
                    raise ValidationException(
                        f"文件 {file.filename} 超过最大允许大小 {self.__chatflow_singlefile_maxsize / (1024 * 1024)} MB"
                    )

                # 创建临时文件
                with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as temp_file:
                    temp_file.write(content)
                    temp_file_path = temp_file.name
                    temp_file_paths.append(temp_file_path)

                logger.info(f"temp file created: {temp_file_path} for original file: {file.filename}")

                # 调用DifyClient上传文件
                resp = await dify_client.upload_file(file_path=temp_file_path)
                if resp.status == "error":
                    logger.error(f"failed to upload file {file.filename}: {resp.message}")
                    raise BaseBusinessException(code=CHAT_SERVICE_DIFY_UPLOAD_FILE_ERROR,
                                                message=get_service_error_message(CHAT_SERVICE_DIFY_UPLOAD_FILE_ERROR),
                                                details=resp.message)
                file_info = resp.data
                file_info["file_name"] = file.filename # 保留原始文件名信息
                uploaded_files_info.append(file_info)
                logger.info(f"file uploaded success: {file.filename} -> file_id={file_info.get('id')}")

        finally:
            # 清理所有临时文件
            for temp_path in temp_file_paths:
                try:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                        logger.info(f"temp file cleaned: {temp_path}")
                except Exception as e:
                    logger.warning(f"failed to clean temp file {temp_path}: {str(e)}")

        return UploadFilesToChatFlowPlatformResponse(file_info_list=uploaded_files_info)
    
    async def chatflow_block_mode(self, request: ChatFlowRequest, login_user: str, trace_id: str = None) -> ChatFlowBlockResponse:
        """对话流平台阻塞模式处理"""

        if request.platform == ChatFlowPlatform.DIFY:
            dify_files = self._get_dify_files_info(request)

            # 调用DifyClient执行阻塞对话流
            dify_api_key = self._get_dify_chatflow_apikey_info(
                user_id=login_user,
                chatflow_name=request.chatflow_name
            )["api_key"]

            dify_client = DifyClient(
                dify_url=self.app_config.dify_url,
                access_api_key=dify_api_key,
                workflow_name=request.chatflow_name,
                user_id=request.platform_user,
                timeout=120,
            )

            resp = await dify_client.execute_chatflow_block(request.query, inputs=request.inputs, files=dify_files)
            if resp.status == "error":
                raise WorkflowException(
                    code=CHAT_SERVICE_DIFY_CHAT_ERROR,
                    message=get_service_error_message(CHAT_SERVICE_DIFY_CHAT_ERROR),
                    details=resp.model_dump())

            # 从dify响应中提取需要的字段
            dify_data = resp.data if isinstance(resp.data, dict) else {}
            return ChatFlowBlockResponse(
                answer=dify_data.get("answer", ""),
                conversation_id=dify_data.get("conversation_id", ""),
                metadata=dify_data.get("metadata"),
                message_id=dify_data.get("message_id", ""),
            )

        else:
            raise ValidationException(f"暂不支持平台: {request.platform}")
        
    async def chatflow_stream_mode(self, request: ChatFlowRequest, login_user: str, trace_id: str = None) -> AsyncGenerator[str, None]:
        """对话流平台流式模式处理"""
        if request.platform == ChatFlowPlatform.DIFY:
            dify_files = self._get_dify_files_info(request)
            
            # 调用DifyClient执行流式对话
            dify_api_key = self._get_dify_chatflow_apikey_info(
                user_id=login_user,
                chatflow_name=request.chatflow_name
            )["api_key"]

            dify_client = DifyClient(
                dify_url=self.app_config.dify_url,
                access_api_key=dify_api_key,
                workflow_name=request.chatflow_name,
                user_id=request.platform_user,
                timeout=120,
            )
            
            stop_event = asyncio.Event()
            try:
                async for chunk in dify_client.chat_sse_raw(
                    stop_flag=stop_event,
                    query=request.query,
                    inputs=request.inputs,
                    files=dify_files
                ):
                    yield chunk
            except asyncio.CancelledError:
                stop_event.set()
                raise
            except Exception as e:
                raise WorkflowException(
                    code=CHAT_SERVICE_DIFY_CHAT_ERROR,
                    message=get_service_error_message(CHAT_SERVICE_DIFY_CHAT_ERROR),
                    details=str(e)
                )
        else:
            raise ValidationException(f"暂不支持平台: {request.platform}")
    
    async def stop_chatflow_task(self, request: StopChatTaskRequest, login_user: str, trace_id: str = None):
        """基于task_id停止对话流平台的当前任务"""
        logger.info(f"stop chatflow task - TraceID: {trace_id} task_id={request.task_id} user={login_user}")

        if request.platform == ChatFlowPlatform.DIFY:
            dify_api_key = self._get_dify_chatflow_apikey_info(
                user_id=login_user,
                chatflow_name=request.chatflow_name
            )["api_key"]
            dify_client = DifyClient(
                dify_url=self.app_config.dify_url,
                access_api_key=dify_api_key,
                workflow_name=request.chatflow_name,
                user_id=request.platform_user,
                timeout=120,
            )
            
            resp = await dify_client.stop_task(task_id=request.task_id)
            if resp.status == "error":
                logger.error(f"stop chatflow task failed error={resp.message} | TraceID: {trace_id}")
                raise WorkflowException(
                    code=CHAT_SERVICE_STOP_CHAT_TASK_ERROR,
                    message=get_service_error_message(CHAT_SERVICE_STOP_CHAT_TASK_ERROR),
                    details=resp.message
                )
            return resp.data
        else:
            raise ValidationException(f"暂不支持平台: {request.platform}")

    async def add_feedbacks(self, request: AddFeedBacksRequest, login_user: str, trace_id: str = None):
        """添加消息反馈"""
        logger.info(f"add feedbacks - TraceID: {trace_id} message_id={request.message_id} rating={request.rating}")

        if request.platform == ChatFlowPlatform.DIFY:
            # 获取Dify API Key
            dify_api_key = self._get_dify_chatflow_apikey_info(
                user_id=login_user,
                chatflow_name=request.chatflow_name
            )["api_key"]

            # 创建DifyClient实例
            dify_client = DifyClient(
                dify_url=self.app_config.dify_url,
                access_api_key=dify_api_key,
                workflow_name=request.chatflow_name,
                user_id=request.platform_user,
                timeout=120
            )

            # 调用DifyClient的消息反馈接口
            resp = await dify_client.message_feedback(
                message_id=request.message_id,
                rating=request.rating.value,
                user=request.platform_user,
                content=request.content
            )

            if resp.status == "error":
                logger.error(f"add feedbacks failed error={resp.message} | TraceID: {trace_id}")
                raise WorkflowException(
                    code=CHAT_SERVICE_ADD_FEEDBACK_ERROR,
                    message=get_service_error_message(CHAT_SERVICE_ADD_FEEDBACK_ERROR),
                    details=resp.message
                )

            return resp.data
        else:
            raise ValidationException(f"暂不支持平台: {request.platform}")

    async def get_feedbacks(self, request: GetFeedBacksRequest, login_user: str, trace_id: str = None):
        """获取APP的消息点赞和反馈"""
        logger.info(f"get feedbacks - TraceID: {trace_id} page={request.page} limit={request.limit}")

        if request.platform == ChatFlowPlatform.DIFY:
            # 获取Dify API Key
            dify_api_key = self._get_dify_chatflow_apikey_info(
                user_id=login_user,
                chatflow_name=request.chatflow_name
            )["api_key"]

            # 创建DifyClient实例
            dify_client = DifyClient(
                dify_url=self.app_config.dify_url,
                access_api_key=dify_api_key,
                workflow_name=request.chatflow_name,
                user_id=request.platform_user,
                timeout=120
            )

            # 调用DifyClient获取反馈接口
            resp = await dify_client.get_app_feedbacks(
                page=request.page,
                limit=request.limit
            )

            if resp.status == "error":
                logger.error(f"get feedbacks failed error={resp.message} | TraceID: {trace_id}")
                raise WorkflowException(
                    code=CHAT_SERVICE_GET_FEEDBACK_ERROR,
                    message=get_service_error_message(CHAT_SERVICE_GET_FEEDBACK_ERROR),
                    details=resp.message
                )

            return resp.data
        else:
            raise ValidationException(f"暂不支持平台: {request.platform}")

    async def add_suggested_questions(self, request: AddSuggestedQuestionsRequest, login_user: str, trace_id: str = None):
        """添加建议问题"""
        logger.info(f"add suggested questions - TraceID: {trace_id} message_id={request.message_id}")

        if request.platform == ChatFlowPlatform.DIFY:
            # 获取Dify API Key
            dify_api_key = self._get_dify_chatflow_apikey_info(
                user_id=login_user,
                chatflow_name=request.chatflow_name
            )["api_key"]

            # 创建DifyClient实例
            dify_client = DifyClient(
                dify_url=self.app_config.dify_url,
                access_api_key=dify_api_key,
                workflow_name=request.chatflow_name,
                user_id=request.platform_user,
                timeout=120
            )

            # 调用DifyClient获取建议问题接口
            resp = await dify_client.get_suggested_questions(
                message_id=request.message_id,
                user=request.platform_user
            )

            if resp.status == "error":
                logger.error(f"add suggested questions failed error={resp.message} | TraceID: {trace_id}")
                raise WorkflowException(
                    code=CHAT_SERVICE_ADD_SUGGESTED_QUESTION_ERROR,
                    message=get_service_error_message(CHAT_SERVICE_ADD_SUGGESTED_QUESTION_ERROR),
                    details=resp.message
                )

            return resp.data
        else:
            raise ValidationException(f"暂不支持平台: {request.platform}")

    async def get_history_message(self, request: GetHistoryMessageRequest, login_user: str, trace_id: str = None) -> GetHistoryMessageResponse:
        """获取单个会话的历史消息"""
        logger.info(f"get history message - TraceID: {trace_id} conversation_id={request.conversation_id}")

        if request.platform == ChatFlowPlatform.DIFY:
            # 获取Dify API Key
            dify_api_key = self._get_dify_chatflow_apikey_info(
                user_id=login_user,
                chatflow_name=request.chatflow_name
            )["api_key"]

            # 创建DifyClient实例
            dify_client = DifyClient(
                dify_url=self.app_config.dify_url,
                access_api_key=dify_api_key,
                workflow_name=request.chatflow_name,
                user_id=request.platform_user,
                timeout=120
            )

            # 调用DifyClient获取会话历史接口
            resp = await dify_client.get_conversation_history(
                conversation_id=request.conversation_id,
                user=request.platform_user
            )

            if resp.status == "error":
                logger.error(f"get history message failed error={resp.message} | TraceID: {trace_id}")
                raise WorkflowException(
                    code=CHAT_SERVICE_GET_HISTORY_MESSAGE_ERROR,
                    message=get_service_error_message(CHAT_SERVICE_GET_HISTORY_MESSAGE_ERROR),
                    details=resp.message
                )
            
            dify_data = resp.data if isinstance(resp.data, dict) else {}
            #return dify_data.get("data", [])
            return GetHistoryMessageResponse(message_list=dify_data.get("data", []))
        else:
            raise ValidationException(f"暂不支持平台: {request.platform}")

    async def get_conversation_list(self, request: GetConversationListRequest, login_user: str, trace_id: str = None):
        """获取会话列表"""
        logger.info(f"get conversation list - TraceID: {trace_id} last_id={request.last_id} limit={request.limit}")

        if request.platform == ChatFlowPlatform.DIFY:
            # 获取Dify API Key
            dify_api_key = self._get_dify_chatflow_apikey_info(
                user_id=login_user,
                chatflow_name=request.chatflow_name
            )["api_key"]

            # 创建DifyClient实例
            dify_client = DifyClient(
                dify_url=self.app_config.dify_url,
                access_api_key=dify_api_key,
                workflow_name=request.chatflow_name,
                user_id=request.platform_user,
                timeout=120
            )

            # 调用DifyClient获取会话列表接口
            resp = await dify_client.get_conversations(
                user=request.platform_user,
                last_id=request.last_id,
                limit=request.limit
            )

            if resp.status == "error":
                logger.error(f"get conversation list failed error={resp.message} | TraceID: {trace_id}")
                raise WorkflowException(
                    code=CHAT_SERVICE_GET_CONVERSATION_LIST_ERROR,
                    message=get_service_error_message(CHAT_SERVICE_GET_CONVERSATION_LIST_ERROR),
                    details=resp.message
                )

            return resp.data.get("data", [])
        else:
            raise ValidationException(f"暂不支持平台: {request.platform}")

    async def delete_conversation(self, request: DeleteConversationRequest, login_user: str, trace_id: str = None):
        """删除会话"""
        logger.info(f"delete conversation - TraceID: {trace_id} conversation_id={request.conversation_id}")

        if request.platform == ChatFlowPlatform.DIFY:
            # 获取Dify API Key
            dify_api_key = self._get_dify_chatflow_apikey_info(
                user_id=login_user,
                chatflow_name=request.chatflow_name
            )["api_key"]

            # 创建DifyClient实例
            dify_client = DifyClient(
                dify_url=self.app_config.dify_url,
                access_api_key=dify_api_key,
                workflow_name=request.chatflow_name,
                user_id=request.platform_user,
                timeout=120
            )

            # 调用DifyClient删除会话接口
            resp = await dify_client.delete_conversation(
                conversation_id=request.conversation_id,
                user=request.platform_user
            )

            if resp.status == "error":
                logger.error(f"delete conversation failed error={resp.message} | TraceID: {trace_id}")
                raise WorkflowException(
                    code=CHAT_SERVICE_DELETE_CONVERSATION_ERROR,
                    message=get_service_error_message(CHAT_SERVICE_DELETE_CONVERSATION_ERROR),
                    details=resp.message
                )

            return resp.data
        else:
            raise ValidationException(f"暂不支持平台: {request.platform}")

    async def rename_conversation(self, request: RenameConversationRequest, login_user: str, trace_id: str = None):
        """会话重命名"""
        logger.info(f"rename conversation - TraceID: {trace_id} conversation_id={request.conversation_id} name={request.name}")

        if request.platform == ChatFlowPlatform.DIFY:
            # 获取Dify API Key
            dify_api_key = self._get_dify_chatflow_apikey_info(
                user_id=login_user,
                chatflow_name=request.chatflow_name
            )["api_key"]

            # 创建DifyClient实例
            dify_client = DifyClient(
                dify_url=self.app_config.dify_url,
                access_api_key=dify_api_key,
                workflow_name=request.chatflow_name,
                user_id=request.platform_user,
                timeout=120
            )

            # 调用DifyClient重命名会话接口
            resp = await dify_client.rename_conversation(
                conversation_id=request.conversation_id,
                name=request.name,
                auto_generate=False,
                user=request.platform_user
            )

            if resp.status == "error":
                logger.error(f"rename conversation failed error={resp.message} | TraceID: {trace_id}")
                raise WorkflowException(
                    code=CHAT_SERVICE_RENAME_CONVERSATION_ERROR,
                    message=get_service_error_message(CHAT_SERVICE_RENAME_CONVERSATION_ERROR),
                    details=resp.message
                )

            return resp.data
        else:
            raise ValidationException(f"暂不支持平台: {request.platform}")

# ========================工作流/对话流相关接口适配========================

        
        
        
        
        
