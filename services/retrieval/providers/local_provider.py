"""
Description: 本地知识库 Provider（复用现有本地逻辑）
Author: codex
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime

from loguru import logger

from .base import KnowledgeBaseProvider
from ..managers.kb_mapping_store import KBMappingStore, KBMapping
from ..managers.knowledge_manager import KnowledgeBaseManager
from ..components.document_processor import DocumentProcessor
from ..schemas import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseInfoExternal,
    KnowledgeBaseListResponse,
    KnowledgeBaseDocumentCreateRequest,
    KnowledgeBaseDocumentInfo,
    KnowledgeBaseDocumentListResponse,
    KnowledgeBaseDocumentUpdateRequest,
    KnowledgeBaseIndexStatusItem,
    KnowledgeBaseIndexStatusResponse,
    KnowledgeBaseSegmentCreateRequest,
    KnowledgeBaseSegmentInfo,
    KnowledgeBaseSegmentListResponse,
    KnowledgeBaseSegmentUpdateRequest,
    KnowledgeBaseMetadataField,
    KnowledgeBaseMetadataAssignRequest,
    KnowledgeBaseMetadataListResponse,
)


class LocalKnowledgeBaseProvider(KnowledgeBaseProvider):
    """
    本地 provider：调用现有本地逻辑（Mongo + GridFS + Qdrant 构建流程的前置上传部分）
    说明：仅支持 file 上传（docx），不支持分段/元数据操作，索引状态为占位。
    """

    def __init__(self, mapping_store: KBMappingStore, config: Dict[str, Any]):
        self.mapping_store = mapping_store
        self.kb_manager = KnowledgeBaseManager(config)
        self.doc_processor = DocumentProcessor(config)

    async def create_kb(self, req: KnowledgeBaseCreateRequest, user_ctx: Dict[str, Any]) -> KnowledgeBaseInfoExternal:
        ok = self.kb_manager.create_knowledge_base(req.name)
        if not ok:
            raise ValueError(f"创建知识库失败: {req.name}")
        mapping = KBMapping(
            kb_name=req.name,
            provider="local",
            external_kb_id=None,
            workspace_id=user_ctx.get("workspace_id"),
            created_by=user_ctx.get("user_id"),
            ext_metadata={"description": req.description},
        )
        self.mapping_store.upsert_mapping(mapping)
        return KnowledgeBaseInfoExternal(
            kb_name=req.name,
            provider="local",
            description=req.description,
            external_kb_id=None,
        )

    async def list_kb(self, page: int, limit: int, user_ctx: Dict[str, Any]) -> KnowledgeBaseListResponse:
        records = self.kb_manager.list_knowledge_bases() or []
        items: List[KnowledgeBaseInfoExternal] = []
        for item in records:
            items.append(
                KnowledgeBaseInfoExternal(
                    kb_name=item.get("knowledge_base_name"),
                    provider="local",
                    description=item.get("description"),
                    external_kb_id=None,
                )
            )
        total = len(items)
        start = (page - 1) * limit
        end = start + limit
        return KnowledgeBaseListResponse(
            items=items[start:end],
            page=page,
            limit=limit,
            total=total,
            has_more=end < total,
        )

    async def delete_kb(self, kb_name: str, user_ctx: Dict[str, Any]) -> None:
        ok = self.kb_manager.delete_knowledge_base(kb_name)
        if not ok:
            raise ValueError(f"删除知识库失败: {kb_name}")
        self.mapping_store.delete_mapping(kb_name)

    async def create_document(
        self,
        kb_name: str,
        req: KnowledgeBaseDocumentCreateRequest,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseDocumentInfo:
        if req.input_type != "file":
            raise ValueError("本地 provider 仅支持文件上传")
        if not req.file_path:
            raise ValueError("缺少文件路径")
        result = self.doc_processor.upload_document(
            file_path=req.file_path,
            original_filename=req.doc_name,
            knowledge_base_name=kb_name,
            overwrite_existing=req.process_rule.get("overwrite_existing", False) if req.process_rule else False,
        )
        if result.get("status") != "success":
            raise ValueError(result.get("error_message", "上传失败"))
        return KnowledgeBaseDocumentInfo(
            doc_id=result.get("file_path", ""),
            doc_name=req.doc_name,
            indexing_status="uploaded",
            provider="local",
            external_batch_task_id=None,
        )

    async def update_document(
        self,
        kb_name: str,
        doc_id: str,
        req: KnowledgeBaseDocumentUpdateRequest,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseDocumentInfo:
        # 本地更新等价于覆盖上传
        return await self.create_document(kb_name, req, user_ctx)

    async def list_documents(
        self,
        kb_name: str,
        page: int,
        limit: int,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseDocumentListResponse:
        docs = self.doc_processor.mongo_storage.find_record({"knowledge_base_name": kb_name})
        items: List[KnowledgeBaseDocumentInfo] = []
        for doc in docs:
            items.append(
                KnowledgeBaseDocumentInfo(
                    doc_id=str(doc.get("gridfs_filename", "")),
                    doc_name=doc.get("original_filename", ""),
                    indexing_status="uploaded",
                    provider="local",
                )
            )
        total = len(items)
        start = (page - 1) * limit
        end = start + limit
        return KnowledgeBaseDocumentListResponse(
            items=items[start:end],
            page=page,
            limit=limit,
            total=total,
            has_more=end < total,
        )

    async def delete_document(self, kb_name: str, doc_id: str, user_ctx: Dict[str, Any]) -> None:
        # doc_id 在本地实现中使用 gridfs_filename
        # 删除文档记录与 GridFS 文件
        # 先查记录
        records = self.doc_processor.mongo_storage.find_record(
            {"knowledge_base_name": kb_name, "gridfs_filename": doc_id}
        )
        if not records:
            raise ValueError("文档不存在")
        for rec in records:
            self.doc_processor.mongo_storage.delete_record({"_id": rec.get("_id")})
            self.doc_processor.mongo_storage.delete_from_gridfs(rec.get("gridfs_filename"))
        logger.info(f"Deleted local document kb={kb_name}, doc={doc_id}")

    async def get_index_status(
        self, kb_name: str, batch_id: str, user_ctx: Dict[str, Any]
    ) -> KnowledgeBaseIndexStatusResponse:
        # 本地暂未有独立索引任务状态，返回占位信息
        return KnowledgeBaseIndexStatusResponse(
            items=[
                KnowledgeBaseIndexStatusItem(
                    doc_id=batch_id,
                    status="uploaded",
                    completed_segments=None,
                    total_segments=None,
                    error="provider=local暂不支持索引状态查询",
                )
            ]
        )

    # 本地暂不支持分段/元数据操作，直接抛出不支持
    async def add_segments(
        self,
        kb_name: str,
        doc_id: str,
        req: KnowledgeBaseSegmentCreateRequest,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseSegmentListResponse:
        raise NotImplementedError("当前 provider 暂不支持分段操作")

    async def list_segments(
        self,
        kb_name: str,
        doc_id: str,
        page: int,
        limit: int,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseSegmentListResponse:
        raise NotImplementedError("当前 provider 暂不支持分段操作")

    async def update_segment(
        self,
        kb_name: str,
        doc_id: str,
        segment_id: str,
        req: KnowledgeBaseSegmentUpdateRequest,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseSegmentInfo:
        raise NotImplementedError("当前 provider 暂不支持分段操作")

    async def delete_segment(
        self,
        kb_name: str,
        doc_id: str,
        segment_id: str,
        user_ctx: Dict[str, Any],
    ) -> None:
        raise NotImplementedError("当前 provider 暂不支持分段操作")

    async def add_metadata_field(
        self,
        kb_name: str,
        field_type: str,
        name: str,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseMetadataField:
        raise NotImplementedError("当前 provider 暂不支持元数据操作")

    async def update_metadata_field(
        self,
        kb_name: str,
        metadata_id: str,
        name: Optional[str],
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseMetadataField:
        raise NotImplementedError("当前 provider 暂不支持元数据操作")

    async def delete_metadata_field(
        self,
        kb_name: str,
        metadata_id: str,
        user_ctx: Dict[str, Any],
    ) -> None:
        raise NotImplementedError("当前 provider 暂不支持元数据操作")

    async def list_metadata_fields(
        self,
        kb_name: str,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseMetadataListResponse:
        raise NotImplementedError("当前 provider 暂不支持元数据操作")

    async def toggle_built_in_metadata(
        self,
        kb_name: str,
        action: str,
        user_ctx: Dict[str, Any],
    ) -> None:
        raise NotImplementedError("当前 provider 暂不支持元数据操作")

    async def assign_documents_metadata(
        self,
        kb_name: str,
        req: KnowledgeBaseMetadataAssignRequest,
        user_ctx: Dict[str, Any],
    ) -> None:
        raise NotImplementedError("当前 provider 暂不支持元数据操作")
