'''
Description: 对话类服务业务逻辑处理器
Author: zyq
Date: 2025-08-26 11:19:24
LastEditors: zyq
LastEditTime: 2025-09-18 16:05:33
'''
from typing import Dict, Any, AsyncGenerator, List
from loguru import logger

from core.config import load_llm_cfg
from core.config.error_codes import COMMON_ERROR_REQUEST_PARSE_ERROR
from core.exceptions import ValidationException, BaseBusinessException
from .schemas import (
    ChatRequest,
    ChatResponse, 
    StreamChatChunk,
    MessageRole
)
from .adapters import ProtocolAdapterFactory, LLMProtocolAdapter


class ChatHandlers:
    """Chat服务纯业务逻辑处理器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled_models = config.get('enabled_models', [])
        self.rate_limits = config.get('rate_limits', {})
        
        # 加载LLM配置
        self.llm_config = load_llm_cfg("openai")
        self.models_info = {model.name: model for model in self.llm_config.models}
        
        # 协议适配器缓存
        self._adapters = {}
        
    
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
    
    
    def _validate_model(self, model: str):
        """验证模型是否在配置中启用"""
        if model not in self.enabled_models:
            raise ValidationException(
                f"模型 {model} 不可用。可用模型: {', '.join(self.enabled_models)}"
            )
    
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