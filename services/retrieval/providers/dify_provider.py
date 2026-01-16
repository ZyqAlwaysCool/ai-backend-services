'''
Description: dify知识库provider
Author: zyq
Date: 2025-12-02 15:39:33
LastEditors: zyq
LastEditTime: 2025-12-04 16:49:39
'''
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from loguru import logger

from core.workflow_clients import DifyKBClient, DifyKBClientError
from .base import KnowledgeBaseProvider
from ..managers.kb_mapping_store import KBMappingStore, KBMapping
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


class DifyKnowledgeBaseProvider(KnowledgeBaseProvider):
    """Dify provider，实现字段映射与客户端调用"""

    def __init__(self, mapping_store: KBMappingStore):
        self.mapping_store = mapping_store

    def _get_client(self, user_ctx: Dict[str, Any]) -> DifyKBClient:
        base_url = user_ctx.get("dify_kb_url")
        api_key = user_ctx.get("dify_kb_api_key")
        if not base_url or not api_key:
            raise ValueError("缺少 Dify 知识库访问凭证")
        timeout = int(user_ctx.get("dify_timeout", 120))
        return DifyKBClient(base_url=base_url, api_key=api_key, timeout=timeout)

    def _get_dataset_id(self, kb_name: str) -> str:
        mapping = self.mapping_store.get_mapping(kb_name)
        if not mapping or not mapping.external_kb_id:
            raise ValueError(f"未找到知识库映射或外部ID缺失: {kb_name}")
        return mapping.external_kb_id

    async def _sync_mapping_from_remote(self, user_ctx: Dict[str, Any]) -> None:
        """全量拉取 Dify 知识库并刷新本地映射，用于删除等场景的兜底"""
        logger.info("start sync mapping from remote dify. user_ctx: %s", user_ctx)
        client = self._get_client(user_ctx)
        page = 1
        limit = 50
        while True:
            try:
                resp = await client.list_datasets(page=page, limit=limit)
            except DifyKBClientError as exc:
                raise ValueError(f"Dify 知识库列表失败: {exc}") from exc
            data_list = resp.get("data", [])
            for item in data_list:
                kb_name = item.get("name")
                dataset_id = item.get("id")
                if kb_name and dataset_id:
                    self.mapping_store.upsert_mapping(
                        KBMapping(
                            kb_name=kb_name,
                            provider="dify",
                            external_kb_id=dataset_id,
                            workspace_id=user_ctx.get("workspace_id"),
                            ext_metadata={"description": item.get("description")},
                        )
                    )
            has_more = resp.get("has_more", False)
            if has_more and data_list:
                page += 1
                continue
            break

    # ===== 知识库 =====
    async def create_kb(self, req: KnowledgeBaseCreateRequest, user_ctx: Dict[str, Any]) -> KnowledgeBaseInfoExternal:
        client = self._get_client(user_ctx)
        try:
            resp = await client.create_dataset(name=req.name, description=req.description)
        except DifyKBClientError as exc:
            raise ValueError(f"Dify 创建知识库失败: {exc}") from exc

        dataset_id = resp.get("id")
        mapping = KBMapping(
            kb_name=req.name,
            provider="dify",
            external_kb_id=dataset_id,
            workspace_id=user_ctx.get("workspace_id"),
            created_by=user_ctx.get("user_id"),
            ext_metadata={"description": req.description},
        )
        self.mapping_store.upsert_mapping(mapping)
        return KnowledgeBaseInfoExternal(
            kb_name=req.name,
            provider="dify",
            description=req.description,
            external_kb_id=dataset_id,
        )

    async def list_kb(self, page: int, limit: int, user_ctx: Dict[str, Any]) -> KnowledgeBaseListResponse:
        client = self._get_client(user_ctx)
        try:
            resp = await client.list_datasets(page=page, limit=limit)
        except DifyKBClientError as exc:
            raise ValueError(f"Dify 知识库列表失败: {exc}") from exc

        items: List[KnowledgeBaseInfoExternal] = []
        for item in resp.get("data", []):
            kb_name = item.get("name")
            dataset_id = item.get("id")
            info = KnowledgeBaseInfoExternal(
                kb_name=kb_name,
                provider="dify",
                description=item.get("description"),
                external_kb_id=dataset_id,
            )
            items.append(info)
            if kb_name and dataset_id:
                self.mapping_store.upsert_mapping(
                    KBMapping(
                        kb_name=kb_name,
                        provider="dify",
                        external_kb_id=dataset_id,
                        workspace_id=user_ctx.get("workspace_id"),
                        ext_metadata={"description": item.get("description")},
                    )
                )
        return KnowledgeBaseListResponse(
            items=items,
            page=resp.get("page", page),
            limit=resp.get("limit", limit),
            total=resp.get("total", len(items)),
            has_more=resp.get("has_more", False),
        )

    async def delete_kb(self, kb_name: str, user_ctx: Dict[str, Any]) -> None:
        client = self._get_client(user_ctx)
        try:
            dataset_id = self._get_dataset_id(kb_name)
        except ValueError:
            await self._sync_mapping_from_remote(user_ctx)
            dataset_id = self._get_dataset_id(kb_name)
        try:
            await client.delete_dataset(dataset_id)
        except DifyKBClientError as exc:
            raise ValueError(f"Dify 删除知识库失败: {exc}") from exc
        self.mapping_store.delete_mapping(kb_name)

    # ===== 文档 =====
    async def create_document(
        self,
        kb_name: str,
        req: KnowledgeBaseDocumentCreateRequest,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseDocumentInfo:
        client = self._get_client(user_ctx)
        dataset_id = self._get_dataset_id(kb_name)
        if req.process_rule is None:
            req.process_rule = {"mode": "automatic"}
        try:
            if req.input_type == "text":
                resp = await client.create_document_by_text(
                    dataset_id=dataset_id,
                    name=req.doc_name,
                    text=req.text or "",
                    indexing_technique=req.indexing_technique or "high_quality",
                    process_rule=req.process_rule,
                )
            elif req.input_type == "file":
                if not req.file_path:
                    raise ValueError("文件路径缺失")
                resp = await client.create_document_by_file(
                    dataset_id=dataset_id,
                    file_path=req.file_path,
                    process_rule=req.process_rule,
                    indexing_technique=req.indexing_technique or "high_quality",
                    name=req.doc_name,
                )
            else:
                raise ValueError(f"不支持的 input_type: {req.input_type}")
        except DifyKBClientError as exc:
            raise ValueError(f"Dify 创建文档失败: {exc}") from exc

        doc = resp.get("document", {})
        return KnowledgeBaseDocumentInfo(
            doc_id=doc.get("id") or "",
            doc_name=doc.get("name") or req.doc_name,
            indexing_status=doc.get("indexing_status", "waiting"),
            provider="dify",
            external_batch_task_id=resp.get("batch"),
        )

    async def update_document(
        self,
        kb_name: str,
        doc_id: str,
        req: KnowledgeBaseDocumentUpdateRequest,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseDocumentInfo:
        client = self._get_client(user_ctx)
        dataset_id = self._get_dataset_id(kb_name)
        if req.process_rule is None:
            req.process_rule = {"mode": "automatic"}
        try:
            if req.input_type == "text":
                resp = await client.update_document_by_text(
                    dataset_id=dataset_id,
                    document_id=doc_id,
                    name=req.doc_name or "",
                    text=req.text or "",
                )
            elif req.input_type == "file":
                if not req.file_path:
                    raise ValueError("文件路径缺失")
                resp = await client.update_document_by_file(
                    dataset_id=dataset_id,
                    document_id=doc_id,
                    file_path=req.file_path,
                    process_rule=req.process_rule,
                    indexing_technique=req.indexing_technique,
                    name=req.doc_name,
                )
            else:
                raise ValueError(f"不支持的 input_type: {req.input_type}")
        except DifyKBClientError as exc:
            raise ValueError(f"Dify 更新文档失败: {exc}") from exc

        doc = resp.get("document", {})
        return KnowledgeBaseDocumentInfo(
            doc_id=doc.get("id") or doc_id,
            doc_name=doc.get("name") or req.doc_name or "",
            indexing_status=doc.get("indexing_status", "waiting"),
            provider="dify",
            external_batch_task_id=resp.get("batch"),
        )

    async def list_documents(
        self,
        kb_name: str,
        page: int,
        limit: int,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseDocumentListResponse:
        client = self._get_client(user_ctx)
        dataset_id = self._get_dataset_id(kb_name)
        try:
            resp = await client.list_documents(dataset_id=dataset_id, page=page, limit=limit)
        except DifyKBClientError as exc:
            raise ValueError(f"Dify 文档列表失败: {exc}") from exc

        docs: List[KnowledgeBaseDocumentInfo] = []
        for item in resp.get("data", []):
            docs.append(
                KnowledgeBaseDocumentInfo(
                    doc_id=item.get("id") or "",
                    doc_name=item.get("name") or "",
                    indexing_status=item.get("indexing_status", ""),
                    provider="dify",
                )
            )
        return KnowledgeBaseDocumentListResponse(
            items=docs,
            page=resp.get("page", page),
            limit=resp.get("limit", limit),
            total=resp.get("total", len(docs)),
            has_more=resp.get("has_more", False),
        )

    async def delete_document(self, kb_name: str, doc_id: str, user_ctx: Dict[str, Any]) -> None:
        client = self._get_client(user_ctx)
        dataset_id = self._get_dataset_id(kb_name)
        try:
            await client.delete_document(dataset_id=dataset_id, document_id=doc_id)
        except DifyKBClientError as exc:
            raise ValueError(f"Dify 删除文档失败: {exc}") from exc

    async def get_index_status(
        self, kb_name: str, batch_id: str, user_ctx: Dict[str, Any]
    ) -> KnowledgeBaseIndexStatusResponse:
        client = self._get_client(user_ctx)
        dataset_id = self._get_dataset_id(kb_name)
        try:
            resp = await client.get_indexing_status(dataset_id=dataset_id, batch=batch_id)
        except DifyKBClientError as exc:
            raise ValueError(f"Dify 索引状态查询失败: {exc}") from exc

        items = []
        for item in resp.get("data", []):
            items.append(
                KnowledgeBaseIndexStatusItem(
                    doc_id=item.get("id", ""),
                    status=item.get("indexing_status", ""),
                    completed_segments=item.get("completed_segments"),
                    total_segments=item.get("total_segments"),
                    error=item.get("error"),
                )
            )
        return KnowledgeBaseIndexStatusResponse(items=items)

    # ===== 分段 =====
    async def add_segments(
        self,
        kb_name: str,
        doc_id: str,
        req: KnowledgeBaseSegmentCreateRequest,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseSegmentListResponse:
        client = self._get_client(user_ctx)
        dataset_id = self._get_dataset_id(kb_name)
        try:
            resp = await client.add_segments(
                dataset_id=dataset_id,
                document_id=doc_id,
                segments=[seg.model_dump() for seg in req.segments],
            )
        except DifyKBClientError as exc:
            raise ValueError(f"Dify 新增分段失败: {exc}") from exc
        return self._parse_segments(resp)

    async def list_segments(
        self,
        kb_name: str,
        doc_id: str,
        page: int,
        limit: int,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseSegmentListResponse:
        client = self._get_client(user_ctx)
        dataset_id = self._get_dataset_id(kb_name)
        try:
            resp = await client.list_segments(
                dataset_id=dataset_id, document_id=doc_id, page=page, limit=limit
            )
        except DifyKBClientError as exc:
            raise ValueError(f"Dify 查询分段失败: {exc}") from exc
        return self._parse_segments(resp, page, limit)

    async def update_segment(
        self,
        kb_name: str,
        doc_id: str,
        segment_id: str,
        req: KnowledgeBaseSegmentUpdateRequest,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseSegmentInfo:
        client = self._get_client(user_ctx)
        dataset_id = self._get_dataset_id(kb_name)
        try:
            resp = await client.update_segment(
                dataset_id=dataset_id,
                document_id=doc_id,
                segment_id=segment_id,
                segment=req.segment.dict(),
            )
        except DifyKBClientError as exc:
            raise ValueError(f"Dify 更新分段失败: {exc}") from exc
        parsed = self._parse_segments(resp)
        if parsed.items:
            return parsed.items[0]
        logger.warning("Dify 更新分段未返回数据，使用请求数据回填 segment_id={} doc_id={}", segment_id, doc_id)
        segment_payload = req.segment
        return KnowledgeBaseSegmentInfo(
            segment_id=segment_id,
            doc_id=doc_id,
            content=segment_payload.content,
            answer=segment_payload.answer,
            enabled=segment_payload.enabled if segment_payload.enabled is not None else True,
            status="",
        )

    async def delete_segment(
        self,
        kb_name: str,
        doc_id: str,
        segment_id: str,
        user_ctx: Dict[str, Any],
    ) -> None:
        client = self._get_client(user_ctx)
        dataset_id = self._get_dataset_id(kb_name)
        try:
            await client.delete_segment(dataset_id=dataset_id, document_id=doc_id, segment_id=segment_id)
        except DifyKBClientError as exc:
            if exc.status_code == 404:
                logger.warning(
                    "Dify 删除分段返回404,忽略错误 dataset={} doc_id={} segment_id={} msg={}",
                    kb_name,
                    doc_id,
                    segment_id,
                    exc.error,
                )
                return
            raise ValueError(f"Dify 删除分段失败: {exc}") from exc

    # ===== 元数据 =====
    async def add_metadata_field(
        self,
        kb_name: str,
        field_type: str,
        name: str,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseMetadataField:
        client = self._get_client(user_ctx)
        dataset_id = self._get_dataset_id(kb_name)
        try:
            resp = await client.add_metadata_field(dataset_id=dataset_id, field_type=field_type, name=name)
        except DifyKBClientError as exc:
            raise ValueError(f"Dify 新增元数据字段失败: {exc}") from exc
        return KnowledgeBaseMetadataField(id=resp.get("id", ""), type=resp.get("type", field_type), name=resp.get("name", name))

    async def update_metadata_field(
        self,
        kb_name: str,
        metadata_id: str,
        name: Optional[str],
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseMetadataField:
        client = self._get_client(user_ctx)
        dataset_id = self._get_dataset_id(kb_name)
        try:
            resp = await client.update_metadata_field(dataset_id=dataset_id, metadata_id=metadata_id, name=name)
        except DifyKBClientError as exc:
            raise ValueError(f"Dify 更新元数据字段失败: {exc}") from exc
        return KnowledgeBaseMetadataField(id=resp.get("id", metadata_id), type=resp.get("type", ""), name=resp.get("name", name or ""))

    async def delete_metadata_field(
        self,
        kb_name: str,
        metadata_id: str,
        user_ctx: Dict[str, Any],
    ) -> None:
        client = self._get_client(user_ctx)
        dataset_id = self._get_dataset_id(kb_name)
        try:
            await client.delete_metadata_field(dataset_id=dataset_id, metadata_id=metadata_id)
        except DifyKBClientError as exc:
            raise ValueError(f"Dify 删除元数据字段失败: {exc}") from exc

    async def list_metadata_fields(
        self,
        kb_name: str,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseMetadataListResponse:
        client = self._get_client(user_ctx)
        dataset_id = self._get_dataset_id(kb_name)
        try:
            resp = await client.list_metadata_fields(dataset_id=dataset_id)
        except DifyKBClientError as exc:
            raise ValueError(f"Dify 元数据列表失败: {exc}") from exc
        fields = []
        for item in resp.get("doc_metadata", []):
            fields.append(
                KnowledgeBaseMetadataField(
                    id=item.get("id", ""),
                    type=item.get("type", ""),
                    name=item.get("name", ""),
                )
            )
        built_in_enabled = resp.get("built_in_field_enabled", True)
        return KnowledgeBaseMetadataListResponse(fields=fields, built_in_field_enabled=built_in_enabled)

    async def toggle_built_in_metadata(
        self,
        kb_name: str,
        action: str,
        user_ctx: Dict[str, Any],
    ) -> None:
        client = self._get_client(user_ctx)
        dataset_id = self._get_dataset_id(kb_name)
        try:
            await client.toggle_built_in_metadata(dataset_id=dataset_id, action=action)
        except DifyKBClientError as exc:
            raise ValueError(f"Dify 内置元数据切换失败: {exc}") from exc

    async def assign_documents_metadata(
        self,
        kb_name: str,
        req: KnowledgeBaseMetadataAssignRequest,
        user_ctx: Dict[str, Any],
    ) -> None:
        client = self._get_client(user_ctx)
        dataset_id = self._get_dataset_id(kb_name)
        try:
            await client.assign_documents_metadata(dataset_id=dataset_id, operation_data=req.operation_data)
        except DifyKBClientError as exc:
            raise ValueError(f"Dify 赋值文档元数据失败: {exc}") from exc

    # ===== 辅助解析 =====
    def _parse_segments(
        self,
        resp: Any,
        page: int = 1,
        limit: int = 20,
    ) -> KnowledgeBaseSegmentListResponse:
        if isinstance(resp, str):
            try:
                resp = json.loads(resp)
            except Exception:
                logger.warning("Dify 分段接口返回非 JSON 字符串，原始响应={}", resp[:200])
                resp = {}
        if not isinstance(resp, dict):
            logger.warning("Dify 分段接口返回类型异常 type={} resp={}", type(resp), resp)
            resp = {}

        items = []
        data_list: Any = resp.get("data", [])
        if isinstance(resp, list) and not data_list:
            data_list = resp
        if isinstance(data_list, dict):
            data_list = [data_list]
        elif not isinstance(data_list, list):
            logger.warning("Dify 分段接口 data 字段类型异常 data={}", data_list)
            data_list = []
        for item in data_list:
            if not isinstance(item, dict):
                logger.warning("跳过异常分段项 item={}", item)
                continue
            items.append(
                KnowledgeBaseSegmentInfo(
                    segment_id=item.get("id", ""),
                    doc_id=item.get("document_id", ""),
                    content=item.get("content", ""),
                    answer=item.get("answer"),
                    enabled=item.get("enabled", True),
                    status=item.get("status", ""),
                )
            )
        return KnowledgeBaseSegmentListResponse(
            items=items,
            page=resp.get("page", page),
            limit=resp.get("limit", limit),
            total=resp.get("total", len(items)),
            has_more=resp.get("has_more", False),
        )
