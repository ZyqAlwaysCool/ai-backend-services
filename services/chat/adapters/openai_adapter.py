'''
Description: OpenAI协议适配器(兼容所有OpenAI协议的模型)
Author: zyq
Date: 2025-09-03 18:30:51
LastEditors: zyq
LastEditTime: 2025-09-29 16:15:03
'''
from typing import Dict, Any, AsyncGenerator, List
from loguru import logger

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_community.callbacks.manager import get_openai_callback

from core.config.error_codes import COMMON_ERROR_REQUEST_PARSE_ERROR
from core.exceptions import BaseBusinessException
from ..schemas import ChatResponse, StreamChatChunk, MessageRole
from .base import LLMProtocolAdapter


class OpenAIProtocolAdapter(LLMProtocolAdapter):
    """OpenAI协议适配器(兼容qwen、deepseek、llama等所有OpenAI协议的模型)"""
    
    def __init__(self, model_config: Dict[str, Any], timeout: int = 30):
        super().__init__(model_config)
        self.timeout = timeout
        self._llm_client = None
        self._stream_client = None
    
    def _get_llm_client(self, stream: bool = False) -> ChatOpenAI:
        """获取LangChain客户端"""
        if stream:
            if not self._stream_client:
                self._stream_client = ChatOpenAI(
                    model=self.model_name,
                    base_url=self.base_url,
                    api_key=self.api_key,
                    streaming=True,
                    timeout=self.timeout
                )
            return self._stream_client
        else:
            if not self._llm_client:
                self._llm_client = ChatOpenAI(
                    model=self.model_name,
                    base_url=self.base_url,
                    api_key=self.api_key,
                    streaming=False,
                    timeout=self.timeout
                )
            return self._llm_client
    
    def _convert_messages_to_langchain(self, messages: List[Dict[str, str]]):
        """将消息格式转换为LangChain格式"""
        lc_messages = []
        for msg in messages:
            role = msg.get('role')
            content = msg.get('content', '')
            
            if role == MessageRole.SYSTEM.value:
                lc_messages.append(SystemMessage(content=content))
            elif role == MessageRole.USER.value:
                lc_messages.append(HumanMessage(content=content))
            elif role == MessageRole.ASSISTANT.value:
                lc_messages.append(AIMessage(content=content))
        
        return lc_messages
    
    async def chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float, 
        max_tokens: int,
        **kwargs
    ) -> ChatResponse:
        """非流式对话补全"""
        try:
            llm_client = self._get_llm_client(stream=False)
            llm_client.temperature = temperature
            llm_client.max_tokens = max_tokens
            
            lc_messages = self._convert_messages_to_langchain(messages)
            
            # 使用callback统计token
            with get_openai_callback() as cb:
                response = await llm_client.ainvoke(lc_messages)
            
            return ChatResponse(
                answer=response.content,
                model=self.model_name,
                usage={
                    'prompt_tokens': cb.prompt_tokens,
                    'completion_tokens': cb.completion_tokens,
                    'total_tokens': cb.total_tokens
                },
                finish_reason='stop'
            )
            
        except Exception as e:
            logger.error(f"OpenAI chat completion failed model={self.model_name} error={str(e)}")
            raise BaseBusinessException(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                message=f"模型 {self.model_name} 调用失败: {str(e)}"
            )
    
    async def chat_completion_stream(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float, 
        max_tokens: int,
        **kwargs
    ) -> AsyncGenerator[StreamChatChunk, None]:
        """流式对话补全"""
        try:
            llm_client = self._get_llm_client(stream=True)
            llm_client.temperature = temperature
            llm_client.max_tokens = max_tokens
            
            lc_messages = self._convert_messages_to_langchain(messages)
            
            async for chunk in llm_client.astream(lc_messages):
                if chunk.content:
                    yield StreamChatChunk(
                        content=chunk.content,
                        finish_reason=None,
                        model=self.model_name
                    )
            
            # 发送结束标记
            yield StreamChatChunk(
                content="",
                finish_reason="stop",
                model=self.model_name
            )
            
        except Exception as e:
            logger.error(f"OpenAI stream completion failed model={self.model_name} error={str(e)}")
            raise BaseBusinessException(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                message=f"模型 {self.model_name} 流式调用失败: {str(e)}"
            )
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 发送一个简单的测试消息
            test_messages = [{'role': 'user', 'content': 'hello'}]
            llm_client = self._get_llm_client(stream=False)
            llm_client.temperature = 0.1
            llm_client.max_tokens = 10
            
            lc_messages = self._convert_messages_to_langchain(test_messages)
            response = await llm_client.ainvoke(lc_messages)
            
            return bool(response.content)
            
        except Exception as e:
            logger.warning(f"Health check failed model={self.model_name} error={str(e)}")
            return False