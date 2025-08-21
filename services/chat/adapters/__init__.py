'''
Description: 协议适配器模块
Author: zyq
Date: 2025-01-21
'''
from .base import LLMProtocolAdapter, ProtocolAdapterFactory
from .openai_adapter import OpenAIProtocolAdapter

# 注册支持OpenAI协议的具体模型供应商
ProtocolAdapterFactory.register_adapter('qwen', OpenAIProtocolAdapter)
ProtocolAdapterFactory.register_adapter('deepseek', OpenAIProtocolAdapter)
ProtocolAdapterFactory.register_adapter('llama', OpenAIProtocolAdapter)