"""
Description: 知识库 provider 映射存储
Author: codex
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from core.storage.mongo_storage import MongoStorage
from loguru import logger


@dataclass
class KBMapping:
    kb_name: str
    provider: str
    external_kb_id: Optional[str] = None
    workspace_id: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime = datetime.utcnow()
    status: str = "active"
    ext_metadata: Optional[Dict[str, Any]] = None


class KBMappingStore:
    """管理 kb_name 与 provider 映射"""

    def __init__(self, mongo: MongoStorage):
        self.mongo = mongo
        self.collection = self.mongo.db["kb_provider_mapping"]
        # 唯一索引 kb_name
        self.collection.create_index("kb_name", unique=True)

    def upsert_mapping(self, mapping: KBMapping) -> None:
        data = {
            "kb_name": mapping.kb_name,
            "provider": mapping.provider,
            "external_kb_id": mapping.external_kb_id,
            "workspace_id": mapping.workspace_id,
            "created_by": mapping.created_by,
            "created_at": mapping.created_at,
            "status": mapping.status,
            "ext_metadata": mapping.ext_metadata or {},
        }
        self.collection.update_one({"kb_name": mapping.kb_name}, {"$set": data}, upsert=True)
        logger.info(f"Upsert kb mapping kb={mapping.kb_name} provider={mapping.provider}")

    def get_mapping(self, kb_name: str) -> Optional[KBMapping]:
        doc = self.collection.find_one({"kb_name": kb_name})
        if not doc:
            return None
        return KBMapping(
            kb_name=doc.get("kb_name"),
            provider=doc.get("provider"),
            external_kb_id=doc.get("external_kb_id"),
            workspace_id=doc.get("workspace_id"),
            created_by=doc.get("created_by"),
            created_at=doc.get("created_at", datetime.utcnow()),
            status=doc.get("status", "active"),
            ext_metadata=doc.get("ext_metadata", {}),
        )

    def delete_mapping(self, kb_name: str) -> None:
        self.collection.delete_one({"kb_name": kb_name})
        logger.info(f"Delete kb mapping kb={kb_name}")
