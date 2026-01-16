"""
Description: 知识库平台凭证存储（按 user_id + provider + name 管理，软删）
Author: codex
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

from core.storage.mongo_storage import MongoStorage
from loguru import logger
from services.retrieval.schemas import CredentialStatusEnum, KnowledgeBaseProviderEnum


@dataclass
class KBCredential:
    user_id: str
    provider: KnowledgeBaseProviderEnum
    name: str
    api_key: str
    workspace_id: Optional[str] = None
    is_default: bool = False
    status: str = CredentialStatusEnum.ACTIVE.value  # active/deleted
    description: Optional[str] = None
    created_at: datetime = datetime.utcnow()
    updated_at: datetime = datetime.utcnow()


class KBCredentialStore:
    def __init__(self, mongo: MongoStorage, collection_name: str = "kb_credentials"):
        self.mongo = mongo
        self.col = self.mongo.db[collection_name]
        self.col.create_index(
            [
                ("user_id", 1),
                ("provider", 1),
                ("name", 1),
                ("status", 1),
            ],
            unique=True,
        )

    def upsert(self, cred: KBCredential):
        provider_value = cred.provider.value if hasattr(cred.provider, "value") else cred.provider
        data = {**cred.__dict__, "provider": provider_value}
        # 如果存在，保留原 created_at
        existing = self.col.find_one({"user_id": cred.user_id, "provider": provider_value, "name": cred.name})
        if existing and existing.get("created_at"):
            data["created_at"] = existing.get("created_at")
        self.col.update_one(
            {
                "user_id": cred.user_id,
                "provider": provider_value,
                "name": cred.name,
            },
            {"$set": data},
            upsert=True,
        )
        logger.info(f"Upsert kb credential user={cred.user_id} provider={provider_value} name={cred.name}")

    def list(self, user_id: str, provider: Optional[KnowledgeBaseProviderEnum] = None) -> List[dict]:
        query = {"user_id": user_id, "status": {"$ne": CredentialStatusEnum.DELETED.value}}
        provider_value = provider.value if provider and hasattr(provider, "value") else provider
        if provider_value:
            query["provider"] = provider_value
        docs = list(self.col.find(query))
        for d in docs:
            d.pop("_id", None)
        return docs

    def soft_delete(self, user_id: str, provider: KnowledgeBaseProviderEnum, name: str) -> bool:
        provider_value = provider.value if hasattr(provider, "value") else provider
        result = self.col.update_one(
            {"user_id": user_id, "provider": provider_value, "name": name, "status": {"$ne": CredentialStatusEnum.DELETED.value}},
            {"$set": {"status": CredentialStatusEnum.DELETED.value, "updated_at": datetime.utcnow()}},
        )
        return result.modified_count > 0

    def get(self, user_id: str, provider: KnowledgeBaseProviderEnum, name: Optional[str] = None) -> Optional[dict]:
        provider_value = provider.value if hasattr(provider, "value") else provider
        query = {"user_id": user_id, "provider": provider_value, "status": {"$ne": CredentialStatusEnum.DELETED.value}}
        if name:
            query["name"] = name
            doc = self.col.find_one(query)
        else:
            doc = self.col.find_one({**query, "is_default": True}) or self.col.find_one(query)
        if not doc:
            return None
        doc.pop("_id", None)
        return doc
