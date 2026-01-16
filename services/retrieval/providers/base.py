'''
Description: 知识库provider抽象
Author: zyq
Date: 2025-12-02 15:36:56
LastEditors: zyq
LastEditTime: 2025-12-02 15:37:03
'''
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol

from ..schemas import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseInfoExternal,
    KnowledgeBaseListResponse,
    KnowledgeBaseDocumentCreateRequest,
    KnowledgeBaseDocumentInfo,
    KnowledgeBaseDocumentListResponse,
    KnowledgeBaseDocumentUpdateRequest,
    KnowledgeBaseIndexStatusResponse,
    KnowledgeBaseSegmentCreateRequest,
    KnowledgeBaseSegmentInfo,
    KnowledgeBaseSegmentListResponse,
    KnowledgeBaseSegmentUpdateRequest,
    KnowledgeBaseMetadataField,
    KnowledgeBaseMetadataAssignRequest,
    KnowledgeBaseMetadataListResponse,
)


class KnowledgeBaseProvider(Protocol):
    """统一的知识库 Provider 接口"""

    async def create_kb(self, req: KnowledgeBaseCreateRequest, user_ctx: Dict[str, Any]) -> KnowledgeBaseInfoExternal:
        ...

    async def list_kb(self, page: int, limit: int, user_ctx: Dict[str, Any]) -> KnowledgeBaseListResponse:
        ...

    async def delete_kb(self, kb_name: str, user_ctx: Dict[str, Any]) -> None:
        ...

    async def create_document(
        self,
        kb_name: str,
        req: KnowledgeBaseDocumentCreateRequest,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseDocumentInfo:
        ...

    async def update_document(
        self,
        kb_name: str,
        doc_id: str,
        req: KnowledgeBaseDocumentUpdateRequest,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseDocumentInfo:
        ...

    async def list_documents(
        self,
        kb_name: str,
        page: int,
        limit: int,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseDocumentListResponse:
        ...

    async def delete_document(self, kb_name: str, doc_id: str, user_ctx: Dict[str, Any]) -> None:
        ...

    async def get_index_status(
        self, kb_name: str, batch_id: str, user_ctx: Dict[str, Any]
    ) -> KnowledgeBaseIndexStatusResponse:
        ...

    async def add_segments(
        self,
        kb_name: str,
        doc_id: str,
        req: KnowledgeBaseSegmentCreateRequest,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseSegmentListResponse:
        ...

    async def list_segments(
        self,
        kb_name: str,
        doc_id: str,
        page: int,
        limit: int,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseSegmentListResponse:
        ...

    async def update_segment(
        self,
        kb_name: str,
        doc_id: str,
        segment_id: str,
        req: KnowledgeBaseSegmentUpdateRequest,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseSegmentInfo:
        ...

    async def delete_segment(
        self,
        kb_name: str,
        doc_id: str,
        segment_id: str,
        user_ctx: Dict[str, Any],
    ) -> None:
        ...

    async def add_metadata_field(
        self,
        kb_name: str,
        field_type: str,
        name: str,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseMetadataField:
        ...

    async def update_metadata_field(
        self,
        kb_name: str,
        metadata_id: str,
        name: Optional[str],
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseMetadataField:
        ...

    async def delete_metadata_field(
        self,
        kb_name: str,
        metadata_id: str,
        user_ctx: Dict[str, Any],
    ) -> None:
        ...

    async def list_metadata_fields(
        self,
        kb_name: str,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseMetadataListResponse:
        ...

    async def toggle_built_in_metadata(
        self,
        kb_name: str,
        action: str,
        user_ctx: Dict[str, Any],
    ) -> None:
        ...

    async def assign_documents_metadata(
        self,
        kb_name: str,
        req: KnowledgeBaseMetadataAssignRequest,
        user_ctx: Dict[str, Any],
    ) -> None:
        ...
