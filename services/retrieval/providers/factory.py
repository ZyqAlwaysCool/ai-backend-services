'''
Description: provider工厂类
Author: zyq
Date: 2025-12-02 15:37:45
LastEditors: zyq
LastEditTime: 2025-12-02 15:37:51
'''
from __future__ import annotations

from typing import Dict, Any

from loguru import logger

from .base import KnowledgeBaseProvider
from .local_provider import LocalKnowledgeBaseProvider
from .dify_provider import DifyKnowledgeBaseProvider
from ..managers.kb_mapping_store import KBMappingStore


class KnowledgeBaseProviderFactory:
    """根据 kb_name 或 provider 提示，创建 provider 实例"""

    def __init__(self, mapping_store: KBMappingStore, config: Dict[str, Any]):
        self.mapping_store = mapping_store
        self.config = config
        self._providers: Dict[str, KnowledgeBaseProvider] = {}

    def get(self, kb_name: str, provider_hint: str | None = None) -> KnowledgeBaseProvider:
        provider = provider_hint
        if not provider:
            mapping = self.mapping_store.get_mapping(kb_name)
            provider = mapping.provider if mapping else None
        provider = provider or "local"

        if provider in self._providers:
            return self._providers[provider]

        if provider == "local":
            instance = LocalKnowledgeBaseProvider(self.mapping_store, self.config)
        elif provider == "dify":
            instance = DifyKnowledgeBaseProvider(self.mapping_store)
        else:
            raise ValueError(f"不支持的 provider: {provider}")

        self._providers[provider] = instance
        logger.info(f"Provider created provider={provider}")
        return instance
