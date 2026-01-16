'''
Description: MCP独立的OpenAI协议LLM适配器
Author: zyq
Date: 2025-12-24 11:00:00
LastEditors: zyq
LastEditTime: 2025-12-22 17:31:43
'''
import asyncio
import os
from typing import Dict, Any, List
from loguru import logger

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_community.callbacks.manager import get_openai_callback

from core.exceptions import BaseBusinessException
from core.config.error_codes import COMMON_ERROR_REQUEST_PARSE_ERROR


class MCPChatResponse:
    """简化的响应结构"""
    def __init__(self, answer: str, model: str, usage: Dict[str, int]):
        self.answer = answer
        self.model = model
        self.usage = usage
        self.finish_reason = 'stop'


class MCPOpenAIAdapter:
    def __init__(self, model_config: Dict[str, Any], timeout: int = 30):
        self.model_config = model_config
        self.model_name = model_config.get('model_name')
        self.base_url = model_config.get('base_url') or os.getenv("MCP_LLM_BASE_URL")
        self.api_key = self._resolve_api_key(model_config.get('api_key'))
        self.timeout = timeout
        self._llm_client = None
        self._stream_client = None

    def _resolve_api_key(self, api_key: str | None) -> str:
        """统一处理api_key来源与占位符"""
        candidate = (api_key or "").strip()
        if candidate.startswith("${") and candidate.endswith("}"):
            env_key = candidate[2:-1]
            candidate = os.getenv(env_key, "").strip()
        if not candidate:
            candidate = os.getenv("MODEL_API_KEY", "").strip()
        if not candidate:
            raise BaseBusinessException(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                message="MCP模型api_key缺失，请在配置或环境变量MODEL_API_KEY中设置"
            )
        return candidate

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
        if not self._llm_client:
            self._llm_client = ChatOpenAI(
                model=self.model_name,
                base_url=self.base_url,
                api_key=self.api_key,
                streaming=False,
                timeout=self.timeout
            )
        return self._llm_client

    def _convert_messages(self, messages: List[Dict[str, str]]):
        """转换为LangChain消息格式"""
        lc_messages = []
        for msg in messages:
            role = msg.get('role')
            content = msg.get('content', '')
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
        return lc_messages

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        timeout_ms: int | None = None,
        **kwargs
    ) -> MCPChatResponse:
        """非流式对话补全"""
        try:
            llm_client = self._get_llm_client()
            llm_client.temperature = temperature
            llm_client.max_tokens = max_tokens
            lc_messages = self._convert_messages(messages)
            with get_openai_callback() as cb:
                if timeout_ms:
                    response = await asyncio.wait_for(llm_client.ainvoke(lc_messages), timeout=timeout_ms / 1000)
                else:
                    response = await llm_client.ainvoke(lc_messages)
            return MCPChatResponse(
                answer=response.content,
                model=self.model_name,
                usage={
                    'prompt_tokens': cb.prompt_tokens,
                    'completion_tokens': cb.completion_tokens,
                    'total_tokens': cb.total_tokens
                }
            )
        except Exception as e:
            logger.error(f"MCP模型调用失败 model=({self.model_name}) error=({str(e)})")
            raise BaseBusinessException(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                message=f"MCP模型调用失败: {str(e)}"
            )

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        timeout_ms: int | None = None,
        **kwargs
    ):
        """流式对话补全，逐段yield字符串"""
        try:
            llm_client = self._get_llm_client(stream=True)
            llm_client.temperature = temperature
            llm_client.max_tokens = max_tokens
            lc_messages = self._convert_messages(messages)
            async for chunk in llm_client.astream(lc_messages):
                if hasattr(chunk, "content") and chunk.content:
                    yield chunk.content
        except Exception as e:
            logger.error(f"MCP模型调用失败 model=({self.model_name}) error=({str(e)})")
            raise BaseBusinessException(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                message=f"MCP模型调用失败: {str(e)}"
            )
