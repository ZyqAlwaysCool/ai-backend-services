'''
Description: LLM协议适配器基类和工厂
Author: zyq
Date: 2025-08-21 16:54:00
LastEditors: zyq
LastEditTime: 2025-09-18 16:30:47
'''
from abc import ABC, abstractmethod
from typing import Dict, Any, AsyncGenerator, List

from ..schemas import ChatResponse, StreamChatChunk


class LLMProtocolAdapter(ABC):
    """LLM协议适配器基类"""
    
    def __init__(self, model_config: Dict[str, Any]):
        self.model_config = model_config
        self.model_name = model_config.get('name')
        self.base_url = model_config.get('base_url')
        self.api_key = model_config.get('api_key')
    
    @abstractmethod
    async def chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float, 
        max_tokens: int,
        **kwargs
    ) -> ChatResponse:
        """非流式对话补全"""
        pass
    
    @abstractmethod
    async def chat_completion_stream(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float, 
        max_tokens: int,
        **kwargs
    ) -> AsyncGenerator[StreamChatChunk, None]:
        """流式对话补全"""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass


class ProtocolAdapterFactory:
    """协议适配器工厂"""
    
    _adapters = {}
    
    @classmethod
    def create_adapter(cls, protocol: str, model_config: Dict[str, Any], **kwargs) -> LLMProtocolAdapter:
        """创建协议适配器"""
        if protocol not in cls._adapters:
            raise ValueError(f"不支持的协议: {protocol}")
        
        adapter_class = cls._adapters[protocol]
        return adapter_class(model_config, **kwargs)
    
    @classmethod
    def register_adapter(cls, protocol: str, adapter_class: type):
        """注册新的协议适配器"""
        cls._adapters[protocol] = adapter_class
    
    @classmethod
    def get_supported_protocols(cls) -> List[str]:
        """获取支持的协议列表"""
        return list(cls._adapters.keys())