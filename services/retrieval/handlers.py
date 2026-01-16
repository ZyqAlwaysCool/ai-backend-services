'''
Description: Retrieval服务业务逻辑处理器
Author: zyq
Date: 2025-09-15 17:19:58
LastEditors: zyq
LastEditTime: 2025-12-04 16:37:10
'''

import os
import tempfile
from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import UploadFile, Request
from loguru import logger
from bson import ObjectId
from pathlib import Path
from haystack import Document
from haystack.components.converters.docx import DOCXToDocument
from haystack_integrations.document_stores.qdrant import QdrantDocumentStore
from haystack.components.embedders import SentenceTransformersTextEmbedder
from haystack_integrations.components.retrievers.qdrant import QdrantEmbeddingRetriever

from core.storage.mongo_storage import MongoStorage
from ..services_err_codes import (
    RETRIEVAL_SERVICE_CREDENTIAL_MISSING,
    RETRIEVAL_SERVICE_INVALID_CREDENTIAL,
    RETRIEVAL_SERVICE_USER_CTX_MISSING,
    RETRIEVAL_SERVICE_ADD_OR_UPDATE_CREDENTIAL_ERROR,
    RETRIEVAL_SERVICE_MULTIPLE_DOC_FOUND,
    RETRIEVAL_SERVICE_DOC_NOT_FOUND,
    get_service_error_message,
)
from core.config.config_center import get_app_config
from core.exceptions import BaseBusinessException
from core.tasks import TaskManagerFactory

from .components.document_processor import DocumentProcessor
from .components.document_cleaner import DocumentCleaner
from .managers.knowledge_manager import KnowledgeBaseManager
from .task_managers.knowledge_base_build_task_manager import KnowledgeBaseBuildTaskManager
from .providers.factory import KnowledgeBaseProviderFactory
from .managers.kb_mapping_store import KBMappingStore
from .managers.kb_credential_store import KBCredentialStore, KBCredential
from core.storage.mongo_storage import MongoStorage
from .schemas import (
    RetrievalUploadResponse, FileUploadResult,
    KnowledgeBaseBuildResponse, DocumentCleanSettings,
    RetrievalTaskTypePrefix, RetrievalQueryResponse, SearchResult,
    KnowledgeBaseQueryResponse, KnowledgeBaseInfo,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseInfoExternal,
    KnowledgeBaseListResponse,
    KnowledgeBaseDocumentCreateRequest,
    KnowledgeBaseDocumentUpdateRequest,
    KnowledgeBaseDocumentListResponse,
    KnowledgeBaseDocumentInfo,
    KnowledgeBaseIndexStatusResponse,
    KnowledgeBaseSegmentCreateRequest,
    KnowledgeBaseSegmentUpdateRequest,
    KnowledgeBaseSegmentListResponse,
    KnowledgeBaseSegmentInfo,
    KnowledgeBaseMetadataAssignRequest,
    KnowledgeBaseMetadataAssignByNameRequest,
    KnowledgeBaseMetadataListResponse,
    KnowledgeBaseMetadataField,
    KBCredentialCreateRequest,
    KBCredentialInfo,
    KBCredentialListResponse,
    KnowledgeBaseProviderEnum,
    CredentialStatusEnum,
)


class RetrievalConstants:
    """Retrieval服务业务常量定义"""
    # 状态常量
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    
    # 错误消息模板
    MSG_FILE_COUNT_EXCEEDED = "单次请求最多只能上传{max_files}个文件，当前上传{current_files}个"
    MSG_FILE_SIZE_EXCEEDED = "文件大小超出限制，最大允许{max_size}MB，当前{current_size}MB"
    MSG_KB_CREATE_FAILED = "知识库创建失败"
    MSG_PROCESS_FAILED = "处理失败: {error}"
    MSG_UNSUPPORTED_FORMAT = "仅支持DOCX格式文件"


class RetrievalHandlers:
    """Retrieval服务业务逻辑处理器"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化Retrieval处理器"""
        self.config = config
        self.document_processor = None
        self.document_cleaner = None
        self.knowledge_manager = None
        # self.document_stores = {}  # 缓存每个知识库的DocumentStore
        self.build_task_manager = None  # 知识库构建任务管理器
        self.provider_factory = None
        self.kb_mapping_store = None
        self.kb_credential_store = None
        self._app_config = get_app_config()
    
    async def initialize(self):
        """初始化Retrieval服务处理器"""
        # 初始化基础组件
        self.document_processor = DocumentProcessor(self.config)
        self.document_cleaner = DocumentCleaner(self.config)
        self.knowledge_manager = KnowledgeBaseManager(self.config)
        # provider 工厂 & 映射存储
        mongo = MongoStorage(db_name=self.config.get('retrieval_db_name', 'ai_backend_services_retrieval'))
        self.kb_mapping_store = KBMappingStore(mongo)
        cred_col = self.config.get('kb_credential_collection_name', 'kb_credentials')
        self.kb_credential_store = KBCredentialStore(mongo, cred_col)
        self.provider_factory = KnowledgeBaseProviderFactory(self.kb_mapping_store, self.config)
        
        # 创建任务管理后端
        queue_backend, storage_backend = TaskManagerFactory.create_default_backends()
        
        # 初始化知识库构建任务管理器
        self.build_task_manager = KnowledgeBaseBuildTaskManager(
            queue_backend,
            storage_backend,
            self.config
        )
        
        logger.info("Retrieval handlers初始化完成")

    def _build_user_ctx(self, request: Request) -> Dict[str, Any]:
        """从请求上下文构建 user_context, 供 provider 取凭证等"""
        return {
            "user_id": getattr(request.state, "user_id", None),
            "username": getattr(request.state, "username", None),
        }

    def _ensure_credentials(self, cred: Optional[dict]):
        if not cred or not cred.get("api_key"):
            raise BaseBusinessException(
                code=RETRIEVAL_SERVICE_CREDENTIAL_MISSING,
                message=get_service_error_message(RETRIEVAL_SERVICE_CREDENTIAL_MISSING),
            )

    def _build_provider_context(self, provider_value: str, user_ctx: Dict[str, Any]) -> Dict[str, Any]:
        """
        为指定provider构建上下文
        """
        ctx = dict(user_ctx or {})
        if provider_value == KnowledgeBaseProviderEnum.DIFY.value:
            # dify需要注入url和apikey信息
            cred = self.kb_credential_store.get(user_id=ctx.get("user_id"), provider=KnowledgeBaseProviderEnum.DIFY)
            self._ensure_credentials(cred)
            if not self._app_config.dify_url:
                raise BaseBusinessException(
                    code=RETRIEVAL_SERVICE_CREDENTIAL_MISSING,
                    message=get_service_error_message(RETRIEVAL_SERVICE_CREDENTIAL_MISSING)
                )
            ctx = {**ctx, "dify_kb_url": self._app_config.dify_url, "dify_kb_api_key": cred.get("api_key")}
        return ctx

    async def _find_doc_ids_by_name(
        self,
        kb_name: str,
        doc_name: str,
        provider_ins,
        ctx: Dict[str, Any],
        allow_multiple: bool = False,
        allow_not_found: bool = False,
    ) -> List[str]:
        """按文档名查找 doc_id 列表，处理分页"""
        matched_doc_ids: List[str] = []
        page = 1
        limit = 50
        while True:
            docs = await provider_ins.list_documents(kb_name, page, limit, ctx)
            for item in docs.items:
                if item.doc_name == doc_name:
                    matched_doc_ids.append(item.doc_id)
            if not docs.has_more or not docs.items:
                break
            page += 1
        if not allow_multiple and len(matched_doc_ids) > 1:
            raise BaseBusinessException(
                code=RETRIEVAL_SERVICE_MULTIPLE_DOC_FOUND,
                message=get_service_error_message(RETRIEVAL_SERVICE_MULTIPLE_DOC_FOUND),
            )
        if not matched_doc_ids:
            if allow_not_found:
                return []
            raise BaseBusinessException(
                code=RETRIEVAL_SERVICE_DOC_NOT_FOUND,
                message=get_service_error_message(RETRIEVAL_SERVICE_DOC_NOT_FOUND),
            )
        return matched_doc_ids

    # ============== 统一知识库接口 ==============
    async def create_kb(self, request: KnowledgeBaseCreateRequest, provider: KnowledgeBaseProviderEnum, user_ctx: Dict[str, Any]) -> KnowledgeBaseInfoExternal:
        provider_value = provider.value if hasattr(provider, "value") else provider
        provider_ins = self.provider_factory.get(request.name, provider_value)
        ctx = self._build_provider_context(provider_value, user_ctx)
        return await provider_ins.create_kb(request, ctx)

    async def list_kb(self, page: int, limit: int, provider: KnowledgeBaseProviderEnum, user_ctx: Dict[str, Any]) -> KnowledgeBaseListResponse:
        provider_value = provider.value if hasattr(provider, "value") else provider
        provider_ins = self.provider_factory.get("", provider_value)
        ctx = self._build_provider_context(provider_value, user_ctx)
        return await provider_ins.list_kb(page, limit, ctx)

    async def delete_kb(self, kb_name: str, provider: KnowledgeBaseProviderEnum, user_ctx: Dict[str, Any]) -> None:
        provider_value = provider.value if hasattr(provider, "value") else provider
        provider_ins = self.provider_factory.get("", provider_value)
        ctx = self._build_provider_context(provider_value, user_ctx)
        await provider_ins.delete_kb(kb_name, ctx)

    async def create_kb_document(
        self,
        kb_name: str,
        provider: KnowledgeBaseProviderEnum,
        req: KnowledgeBaseDocumentCreateRequest,
        upload_options: Optional[Dict[str, Any]],
        trace_id: str,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseDocumentInfo:
        provider_value = provider.value if hasattr(provider, "value") else provider
        provider_ins = self.provider_factory.get(kb_name, provider_value)
        ctx = self._build_provider_context(provider_value, user_ctx)
        ctx["trace_id"] = trace_id
        return await provider_ins.create_document(kb_name, req, ctx)

    async def update_kb_document(
        self,
        kb_name: str,
        provider: KnowledgeBaseProviderEnum,
        req: KnowledgeBaseDocumentUpdateRequest,
        trace_id: str,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseDocumentInfo:
        provider_value = provider.value if hasattr(provider, "value") else provider
        provider_ins = self.provider_factory.get(kb_name, provider_value)
        ctx = self._build_provider_context(provider_value, user_ctx)
        ctx["trace_id"] = trace_id
        doc_ids = await self._find_doc_ids_by_name(kb_name, req.doc_name, provider_ins, ctx)
        doc_id = doc_ids[0]
        return await provider_ins.update_document(kb_name, doc_id, req, ctx)

    async def list_kb_documents(
        self,
        kb_name: str,
        provider: KnowledgeBaseProviderEnum,
        page: int,
        limit: int,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseDocumentListResponse:
        provider_value = provider.value if hasattr(provider, "value") else provider
        provider_ins = self.provider_factory.get(kb_name, provider_value)
        ctx = self._build_provider_context(provider_value, user_ctx)
        return await provider_ins.list_documents(kb_name, page, limit, ctx)

    async def delete_kb_document(
        self,
        kb_name: str,
        doc_name: str,
        provider: KnowledgeBaseProviderEnum,
        user_ctx: Dict[str, Any],
    ) -> None:
        provider_value = provider.value if hasattr(provider, "value") else provider
        provider_ins = self.provider_factory.get(kb_name, provider_value)
        ctx = self._build_provider_context(provider_value, user_ctx)
        doc_ids = await self._find_doc_ids_by_name(kb_name, doc_name, provider_ins, ctx, True)
        for doc_id in doc_ids:
            await provider_ins.delete_document(kb_name, doc_id, ctx)

    async def get_kb_index_status(
        self,
        kb_name: str,
        batch_id: str,
        provider: KnowledgeBaseProviderEnum,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseIndexStatusResponse:
        provider_value = provider.value if hasattr(provider, "value") else provider
        provider_ins = self.provider_factory.get(kb_name, provider_value)
        ctx = self._build_provider_context(provider_value, user_ctx)
        return await provider_ins.get_index_status(kb_name, batch_id, ctx)

    async def add_kb_segments(
        self,
        kb_name: str,
        doc_name: str,
        provider: KnowledgeBaseProviderEnum,
        req: KnowledgeBaseSegmentCreateRequest,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseSegmentListResponse:
        provider_value = provider.value if hasattr(provider, "value") else provider
        provider_ins = self.provider_factory.get(kb_name, provider_value)
        ctx = self._build_provider_context(provider_value, user_ctx)
        doc_ids = await self._find_doc_ids_by_name(kb_name, doc_name, provider_ins, ctx)
        doc_id = doc_ids[0]
        return await provider_ins.add_segments(kb_name, doc_id, req, ctx)

    async def list_kb_segments(
        self,
        kb_name: str,
        doc_name: str,
        provider: KnowledgeBaseProviderEnum,
        page: int,
        limit: int,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseSegmentListResponse:
        provider_value = provider.value if hasattr(provider, "value") else provider
        provider_ins = self.provider_factory.get(kb_name, provider_value)
        ctx = self._build_provider_context(provider_value, user_ctx)
        doc_ids = await self._find_doc_ids_by_name(kb_name, doc_name, provider_ins, ctx)
        doc_id = doc_ids[0]
        return await provider_ins.list_segments(kb_name, doc_id, page, limit, ctx)

    async def update_kb_segment(
        self,
        kb_name: str,
        doc_name: str,
        segment_id: str,
        provider: KnowledgeBaseProviderEnum,
        req: KnowledgeBaseSegmentUpdateRequest,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseSegmentInfo:
        provider_value = provider.value if hasattr(provider, "value") else provider
        provider_ins = self.provider_factory.get(kb_name, provider_value)
        ctx = self._build_provider_context(provider_value, user_ctx)
        doc_ids = await self._find_doc_ids_by_name(kb_name, doc_name, provider_ins, ctx)
        doc_id = doc_ids[0]
        return await provider_ins.update_segment(kb_name, doc_id, segment_id, req, ctx)

    async def delete_kb_segment(
        self,
        kb_name: str,
        doc_name: str,
        segment_id: str,
        provider: KnowledgeBaseProviderEnum,
        user_ctx: Dict[str, Any],
    ) -> None:
        provider_value = provider.value if hasattr(provider, "value") else provider
        provider_ins = self.provider_factory.get(kb_name, provider_value)
        ctx = self._build_provider_context(provider_value, user_ctx)
        doc_ids = await self._find_doc_ids_by_name(
            kb_name, doc_name, provider_ins, ctx, allow_not_found=True
        )
        if not doc_ids:
            logger.info("delete_kb_segment: 文档未找到，视为已删除 kb={} doc={} segment={}".format(kb_name, doc_name, segment_id))
            return
        doc_id = doc_ids[0]
        await provider_ins.delete_segment(kb_name, doc_id, segment_id, ctx)

    async def add_kb_metadata_field(
        self,
        kb_name: str,
        provider: KnowledgeBaseProviderEnum,
        field_type: str,
        name: str,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseMetadataField:
        provider_value = provider.value if hasattr(provider, "value") else provider
        provider_ins = self.provider_factory.get(kb_name, provider_value)
        ctx = self._build_provider_context(provider_value, user_ctx)
        return await provider_ins.add_metadata_field(kb_name, field_type, name, ctx)

    async def update_kb_metadata_field(
        self,
        kb_name: str,
        provider: KnowledgeBaseProviderEnum,
        old_meta_field_name: str,
        new_meta_field_name: str,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseMetadataField:
        provider_value = provider.value if hasattr(provider, "value") else provider
        provider_ins = self.provider_factory.get(kb_name, provider_value)
        ctx = self._build_provider_context(provider_value, user_ctx)
        meta_list = await provider_ins.list_metadata_fields(kb_name, ctx)
        matched = [item for item in meta_list.fields if item.name == old_meta_field_name]
        if not matched:
            raise ValueError(f"未找到名称为 {old_meta_field_name} 的元数据字段")
        if len(matched) > 1:
            raise ValueError(f"存在多个同名元数据字段 {old_meta_field_name}，请先处理重名再更新")
        metadata_id = matched[0].id
        return await provider_ins.update_metadata_field(kb_name, metadata_id, new_meta_field_name, ctx)

    async def delete_kb_metadata_field(
        self,
        kb_name: str,
        provider: KnowledgeBaseProviderEnum,
        meta_field_name: str,
        user_ctx: Dict[str, Any],
    ) -> None:
        provider_value = provider.value if hasattr(provider, "value") else provider
        provider_ins = self.provider_factory.get(kb_name, provider_value)
        ctx = self._build_provider_context(provider_value, user_ctx)
        meta_list = await provider_ins.list_metadata_fields(kb_name, ctx)
        matched = [item for item in meta_list.fields if item.name == meta_field_name]
        if not matched:
            raise ValueError(f"未找到名称为 {meta_field_name} 的元数据字段")
        if len(matched) > 1:
            raise ValueError(f"存在多个同名元数据字段 {meta_field_name}，请先处理重名再删除")
        metadata_id = matched[0].id
        await provider_ins.delete_metadata_field(kb_name, metadata_id, ctx)

    async def list_kb_metadata_fields(
        self,
        kb_name: str,
        provider: KnowledgeBaseProviderEnum,
        user_ctx: Dict[str, Any],
    ) -> KnowledgeBaseMetadataListResponse:
        provider_value = provider.value if hasattr(provider, "value") else provider
        provider_ins = self.provider_factory.get(kb_name, provider_value)
        ctx = self._build_provider_context(provider_value, user_ctx)
        return await provider_ins.list_metadata_fields(kb_name, ctx)

    async def toggle_kb_built_in_metadata(
        self,
        kb_name: str,
        provider: KnowledgeBaseProviderEnum,
        action: str,
        user_ctx: Dict[str, Any],
    ) -> None:
        provider_value = provider.value if hasattr(provider, "value") else provider
        provider_ins = self.provider_factory.get(kb_name, provider_value)
        ctx = self._build_provider_context(provider_value, user_ctx)
        await provider_ins.toggle_built_in_metadata(kb_name, action, ctx)

    async def assign_kb_documents_metadata(
        self,
        req: KnowledgeBaseMetadataAssignByNameRequest,
        user_ctx: Dict[str, Any],
    ) -> None:
        provider_value = req.provider.value if hasattr(req.provider, "value") else req.provider
        provider_ins = self.provider_factory.get(req.kb_name, provider_value)
        ctx = self._build_provider_context(provider_value, user_ctx)
        # 取元数据列表，按名称映射 id
        meta_list = await provider_ins.list_metadata_fields(req.kb_name, ctx)
        meta_name_to_id = {item.name: item.id for item in meta_list.fields}
        operation_data: List[Dict[str, Any]] = []
        for doc_item in req.documents:
            doc_name = doc_item.get("doc_name")
            metadata_list = doc_item.get("metadata_list", [])
            if not doc_name or not metadata_list:
                raise ValueError("文档名称或 metadata_list 缺失")
            doc_ids = await self._find_doc_ids_by_name(
                req.kb_name, doc_name, provider_ins, ctx, allow_multiple=False
            )
            doc_id = doc_ids[0]
            converted_meta = []
            for meta in metadata_list:
                meta_name = meta.get("name")
                meta_value = meta.get("value")
                if not meta_name:
                    raise ValueError("元数据 name 不能为空")
                meta_id = meta_name_to_id.get(meta_name)
                if not meta_id:
                    raise ValueError(f"未找到名称为 {meta_name} 的元数据字段")
                converted_meta.append({"id": meta_id, "value": meta_value, "name": meta_name})
            operation_data.append({"document_id": doc_id, "metadata_list": converted_meta})
        assign_req = KnowledgeBaseMetadataAssignRequest(operation_data=operation_data)
        await provider_ins.assign_documents_metadata(req.kb_name, assign_req, ctx)

    # ===== 凭证管理 =====
    def _require_user(self, user_ctx: Dict[str, Any]):
        if not user_ctx.get("user_id"):
            raise BaseBusinessException(
                code=RETRIEVAL_SERVICE_USER_CTX_MISSING,
                message=get_service_error_message(RETRIEVAL_SERVICE_USER_CTX_MISSING)
            )

    async def upsert_kb_credential(self, req: KBCredentialCreateRequest, user_ctx: Dict[str, Any]) -> KBCredentialInfo:
        self._require_user(user_ctx)
        # 对 dify 强制要求配置 DIFY_URL
        provider_value = req.provider.value if hasattr(req.provider, "value") else req.provider
        if provider_value == KnowledgeBaseProviderEnum.DIFY.value:
            if not getattr(self._app_config, "dify_url", None):
                raise BaseBusinessException(
                    code=RETRIEVAL_SERVICE_CREDENTIAL_MISSING,
                    message=get_service_error_message(RETRIEVAL_SERVICE_CREDENTIAL_MISSING)
                )
        cred = KBCredential(
            user_id=user_ctx.get("user_id"),
            provider=provider_value,
            name=req.name,
            api_key=req.api_key,
            workspace_id=req.workspace_id,
            is_default=req.is_default,
            description=req.description,
            status=CredentialStatusEnum.ACTIVE.value,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.kb_credential_store.upsert(cred)
        stored = self.kb_credential_store.get(user_id=user_ctx.get("user_id"), provider=provider_value, name=req.name)
        if stored:
            stored.pop("_id", None)
            return KBCredentialInfo(**stored)
        else:
            raise BaseBusinessException(
                code=RETRIEVAL_SERVICE_ADD_OR_UPDATE_CREDENTIAL_ERROR,
                message=get_service_error_message(RETRIEVAL_SERVICE_ADD_OR_UPDATE_CREDENTIAL_ERROR)
            )

    async def list_kb_credentials(self, provider: Optional[KnowledgeBaseProviderEnum], user_ctx: Dict[str, Any]) -> KBCredentialListResponse:
        self._require_user(user_ctx)
        provider_value = provider.value if provider and hasattr(provider, "value") else provider
        docs = self.kb_credential_store.list(user_id=user_ctx.get("user_id"), provider=provider_value)
        items = []
        for d in docs:
            d.pop("_id", None)
            items.append(KBCredentialInfo(**d))
        return KBCredentialListResponse(items=items)

    async def delete_kb_credential(self, provider: KnowledgeBaseProviderEnum, name: str, user_ctx: Dict[str, Any]) -> None:
        self._require_user(user_ctx)
        provider_value = provider.value if hasattr(provider, "value") else provider
        ok = self.kb_credential_store.soft_delete(
            user_id=user_ctx.get("user_id"), provider=provider_value, name=name
        )
        if not ok:
            raise BaseBusinessException(
                code=RETRIEVAL_SERVICE_INVALID_CREDENTIAL,
                message=get_service_error_message(RETRIEVAL_SERVICE_INVALID_CREDENTIAL)
            )
    
    # def _get_document_store(self, knowledge_base_name: str) -> QdrantDocumentStore:
    #     """获取或创建知识库对应的QdrantDocumentStore"""
    #     if knowledge_base_name not in self.document_stores:
    #         # 获取应用配置
    #         app_config = get_app_config()
            
    #         # 为每个知识库创建独立的collection
    #         self.document_stores[knowledge_base_name] = QdrantDocumentStore(
    #             host=app_config.qdrant_host,
    #             port=app_config.qdrant_port,
    #             index=f"kb_{knowledge_base_name}",  # 每个知识库使用独立的index
    #             embedding_dim=app_config.embedding_dim,
    #             recreate_index=False,
    #             return_embedding=True,
    #             wait_result_from_api=True,
    #             timeout=app_config.qdrant_timeout
    #         )
    #         logger.info(f"Created Qdrant DocumentStore for knowledge base: {knowledge_base_name} (host: {app_config.qdrant_host}:{app_config.qdrant_port})")
        
    #     return self.document_stores[knowledge_base_name]
    
    async def upload_documents(self, 
                              files: List[UploadFile], 
                              knowledge_base_name: str,
                              upload_options: Dict[str, Any] = None,
                              trace_id: str = None) -> RetrievalUploadResponse:
        """
        处理文档上传请求
        
        Args:
            files: 上传的文件列表
            knowledge_base_name: 知识库名称
            upload_options: 上传选项
            trace_id: 请求追踪ID
            
        Returns:
            上传结果响应
        """
        logger.info(f"Start uploading documents - TraceID: {trace_id}, KB: {knowledge_base_name}, Files: {len(files)}")
        
        # 业务规则校验
        max_file_size = self.config.get('max_file_size', 52428800)  # 默认50MB
        max_files_per_request = self.config.get('max_files_per_request', 10)  # 默认10个文件
        
        # 校验文件数量
        if len(files) > max_files_per_request:
            # 所有文件标记为失败
            upload_results = []
            for file in files:
                upload_results.append(FileUploadResult(
                    filename=file.filename,
                    file_size=0,
                    upload_time=datetime.now(),
                    status=RetrievalConstants.STATUS_FAILED,
                    error_message=RetrievalConstants.MSG_FILE_COUNT_EXCEEDED.format(
                        max_files=max_files_per_request,
                        current_files=len(files)
                    )
                ))
            
            return RetrievalUploadResponse(
                knowledge_base_name=knowledge_base_name,
                total_files=len(files),
                success_count=0,
                failed_count=len(files),
                upload_results=upload_results
            )
        
        upload_results = []
        success_count = 0
        failed_count = 0
        
        # 确保知识库存在
        if not self.knowledge_manager.get_knowledge_base(knowledge_base_name):
            if not self.knowledge_manager.create_knowledge_base(knowledge_base_name):
                # 如果创建知识库失败，所有文件都标记为失败
                for file in files:
                    upload_results.append(FileUploadResult(
                        filename=file.filename,
                        file_size=0,
                        upload_time=datetime.now(),
                        status=RetrievalConstants.STATUS_FAILED,
                        error_message=RetrievalConstants.MSG_KB_CREATE_FAILED
                    ))
                    failed_count += 1
                
                return RetrievalUploadResponse(
                    knowledge_base_name=knowledge_base_name,
                    total_files=len(files),
                    success_count=0,
                    failed_count=len(files),
                    upload_results=upload_results
                )
        
        # 处理每个文件
        for file in files:
            try:
                # 读取文件内容用于大小校验
                content = await file.read()
                file_size = len(content)
                
                # 校验文件大小
                if file_size > max_file_size:
                    upload_results.append(FileUploadResult(
                        filename=file.filename,
                        file_size=file_size,
                        upload_time=datetime.now(),
                        status=RetrievalConstants.STATUS_FAILED,
                        error_message=RetrievalConstants.MSG_FILE_SIZE_EXCEEDED.format(
                            max_size=max_file_size // 1024 // 1024,
                            current_size=file_size // 1024 // 1024
                        )
                    ))
                    failed_count += 1
                    continue
                
                # 验证文件格式
                if not file.filename.lower().endswith('.docx'):
                    upload_results.append(FileUploadResult(
                        filename=file.filename,
                        file_size=file_size,
                        upload_time=datetime.now(),
                        status=RetrievalConstants.STATUS_FAILED,
                        error_message=RetrievalConstants.MSG_UNSUPPORTED_FORMAT
                    ))
                    failed_count += 1
                    continue
                
                # 创建临时文件
                with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as temp_file:
                    temp_file.write(content)  # 使用已读取的content
                    temp_file_path = temp_file.name
                
                try:
                    # 上传文档至gridfs并记录元信息
                    result = self.document_processor.upload_document(
                        file_path=temp_file_path,
                        original_filename=file.filename,
                        knowledge_base_name=knowledge_base_name,
                        overwrite_existing=upload_options.get("overwrite_existing", False) if upload_options else False
                    )
                    
                    # 转换为FileUploadResult格式
                    upload_result = FileUploadResult(
                        filename=file.filename,
                        file_size=result.get("file_size", len(content)),
                        upload_time=result.get("upload_time", datetime.now()),
                        status=result["status"],
                        error_message=result.get("error_message"),
                        file_path=result.get("file_path")
                    )
                    
                    upload_results.append(upload_result)
                    
                    if result["status"] == RetrievalConstants.STATUS_SUCCESS:
                        success_count += 1
                        # 更新知识库统计
                        self.knowledge_manager.update_knowledge_base_stats(
                            knowledge_base_name=knowledge_base_name,
                            document_count_delta=1,
                            size_delta=len(content)
                        )
                    else:
                        failed_count += 1
                
                finally:
                    # 清理临时文件
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
                        
            except Exception as e:
                logger.error(f"Failed to process file {file.filename} - TraceID: {trace_id}: {str(e)}")
                upload_results.append(FileUploadResult(
                    filename=file.filename,
                    file_size=0,
                    upload_time=datetime.now(),
                    status=RetrievalConstants.STATUS_FAILED,
                    error_message=RetrievalConstants.MSG_PROCESS_FAILED.format(error=str(e))
                ))
                failed_count += 1
        
        logger.info(f"Documents upload completed - TraceID: {trace_id}, Success: {success_count}, Failed: {failed_count}")
        
        return RetrievalUploadResponse(
            knowledge_base_name=knowledge_base_name,
            total_files=len(files),
            success_count=success_count,
            failed_count=failed_count,
            upload_results=upload_results
        )
    
    def _validate_build_task_id(self, task_id: str) -> bool:
        """验证构建任务ID格式
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否为有效的构建任务ID格式
        """
        if not task_id:
            return False
            
        # 检查任务ID前缀
        expected_prefix = RetrievalTaskTypePrefix.BUILD_TASK.value
        if not task_id.startswith(expected_prefix):
            logger.warning(f"Invalid build task ID format: {task_id}, expected prefix: {expected_prefix}")
            return False
            
        return True
    
    async def submit_build_task(self,
                               knowledge_base_name: str,
                               clean_settings: DocumentCleanSettings,
                               trace_id: str = None) -> KnowledgeBaseBuildResponse:
        """
        提交知识库构建异步任务（文档清洗+向量化）
        
        Args:
            knowledge_base_name: 知识库名称
            clean_settings: 清洗设置
            trace_id: 请求追踪ID
            
        Returns:
            知识库构建任务响应
        """
        logger.info(f"Submit build task - TraceID: {trace_id}, KB: {knowledge_base_name}")
        
        # 提交任务
        return await self.build_task_manager.submit_build_task(
            knowledge_base_name=knowledge_base_name,
            clean_settings=clean_settings,
            trace_id=trace_id
        )
    
    async def get_build_task_status(self,
                                   task_id: str,
                                   trace_id: str = None) -> Dict[str, Any]:
        """
        获取知识库构建任务状态
        
        Args:
            task_id: 任务ID
            trace_id: 请求追踪ID
            
        Returns:
            任务状态信息，如果任务不存在或ID格式错误则返回None
        """
        logger.info(f"Get build task status - TraceID: {trace_id}, TaskID: {task_id}")
        
        # 验证任务ID格式
        if not self._validate_build_task_id(task_id):
            logger.warning(f"Invalid build task ID format - TraceID: {trace_id}, TaskID: {task_id}")
            return None
        
        # 获取任务状态
        return await self.build_task_manager.get_build_task_status(task_id)

    async def build_knowledge_base(self,
                                  knowledge_base_name: str,
                                  clean_settings: DocumentCleanSettings,
                                  trace_id: str = None) -> KnowledgeBaseBuildResponse:
        """
        构建知识库（文档清洗+向量化）
        
        Args:
            knowledge_base_name: 知识库名称
            clean_settings: 清洗设置
            trace_id: 请求追踪ID
            
        Returns:
            知识库构建任务响应
        """
        logger.info(f"Build knowledge base - TraceID: {trace_id}, KB: {knowledge_base_name}")
        
        # 调用知识库构建任务提交方法
        return await self.submit_build_task(
            knowledge_base_name=knowledge_base_name,
            clean_settings=clean_settings,
            trace_id=trace_id
        )
        
    def _get_knowledge_base(self, kb_name_with_version: str, trace_id: str = None):
        logger.info(f"Get knowledge base - TraceID: {trace_id}, KB_with_version: {kb_name_with_version}")
        document_store = None
        
        document_store = QdrantDocumentStore(
            host=self._app_config.qdrant_host,
            port=self._app_config.qdrant_port,
            index=kb_name_with_version,  # 使用版本化索引
            embedding_dim=self._app_config.embedding_dim,
            return_embedding=True,
            wait_result_from_api=True,
            timeout=self._app_config.qdrant_timeout
        )
        
        return document_store
    
    def _get_qdrant_index_name(self, knowledge_base_name: str, version: str) -> str:
        """
        根据知识库名称和版本号生成Qdrant索引名
        
        Args:
            knowledge_base_name: 知识库名称
            version: 版本号
            
        Returns:
            Qdrant索引名
        """
        # 将版本号中的'-'替换为'_'以符合Qdrant索引命名规范
        safe_version = version.replace('-', '_')
        return f"kb_{knowledge_base_name}_{safe_version}"
    
    async def _get_qdrant_chunk_count(self, qdrant_index: str, trace_id: str = None) -> int:
        """
        获取Qdrant索引中的文档块数量
        
        Args:
            qdrant_index: Qdrant索引名
            trace_id: 链路追踪ID
            
        Returns:
            文档块数量
        """
        try:
            document_store = self._get_knowledge_base(qdrant_index, trace_id)
            count = document_store.count_documents()
            logger.debug(f"Qdrant index chunk count - Index: {qdrant_index}, Count: {count}")
            return count
        except Exception as e:
            logger.warning(f"Failed to get Qdrant chunk count - Index: {qdrant_index}: {str(e)}")
            return 0
    
    async def get_knowledge_base_info(self, knowledge_base_name: str, 
                                     trace_id: str = None) -> KnowledgeBaseQueryResponse:
        """
        获取知识库版本详情信息
        
        Args:
            knowledge_base_name: 知识库名称
            trace_id: 链路追踪ID
            
        Returns:
            知识库版本详情响应
        """
        logger.info(f"Get knowledge base info - TraceID: {trace_id}, KB: {knowledge_base_name}")
        
        try:
            # 获取知识库所有版本信息
            versions = self.knowledge_manager.get_knowledge_base_versions(knowledge_base_name)
            
            if not versions:
                logger.info(f"No versions found for knowledge base: {knowledge_base_name}")
                return KnowledgeBaseQueryResponse(
                    knowledge_base_name=knowledge_base_name,
                    knowledge_base_details=[]
                )
            
            knowledge_base_details = []
            
            # 为每个版本组装详情信息
            for version_record in versions:
                try:
                    version = version_record['version']
                    
                    # 获取Qdrant实际chunk数量
                    qdrant_index = self._get_qdrant_index_name(knowledge_base_name, version)
                    chunk_count = await self._get_qdrant_chunk_count(qdrant_index, trace_id)
                    
                    # 解析版本信息
                    version_info = self.knowledge_manager.parse_version_info(version)
                    
                    # 组装KnowledgeBaseInfo
                    kb_info = KnowledgeBaseInfo(
                        knowledge_base_name=knowledge_base_name,
                        kb_version=version,
                        document_count=version_record.get('document_count', 0),
                        chunk_count=chunk_count,  # 使用Qdrant实际数量
                        chunk_method=version_record.get('chunk_method', ''),
                        chunk_settings=version_record.get('chunk_settings', {}),
                        created_at=version_record['created_at'].isoformat() if version_record.get('created_at') else '',
                        metadata={
                            "is_latest": version_record.get('is_latest', False),
                            "settings_hash": version_record.get('settings_hash', ''),
                            "version_info": version_info,
                            "qdrant_index": qdrant_index
                        }
                    )
                    
                    knowledge_base_details.append(kb_info)
                    
                except Exception as e:
                    logger.error(f"Failed to process version {version_record.get('version', 'unknown')}: {str(e)}")
                    continue
            
            logger.info(f"Retrieved {len(knowledge_base_details)} versions for KB: {knowledge_base_name}")
            
            return KnowledgeBaseQueryResponse(
                knowledge_base_name=knowledge_base_name,
                knowledge_base_details=knowledge_base_details
            )
            
        except Exception as e:
            logger.error(f"Failed to get knowledge base info - KB: {knowledge_base_name}, TraceID: {trace_id}: {str(e)}")
            # 返回空结果而不是抛出异常
            return KnowledgeBaseQueryResponse(
                knowledge_base_name=knowledge_base_name,
                knowledge_base_details=[]
            )

    async def query_knowledge_base(self,
                                   knowledge_base_name: str,
                                   kb_version: str,
                                   query_text: str,
                                   trace_id: str = None) -> RetrievalQueryResponse:
        """
        查询知识库
        
        Args:
            knowledge_base_name: 知识库名称
            kb_version: 知识库版本
            query_text: 查询内容
            trace_id: 请求追踪ID
            
        Returns:
            查询结果
        """
        logger.info(f"Query knowledge base - TraceID: {trace_id}, KB: {knowledge_base_name}, Version: {kb_version}, Query: {query_text}")
        
        # 根据知识库名称和版本号生成实际的索引名
        qdrant_index = self._get_qdrant_index_name(knowledge_base_name, kb_version)
        logger.info(f"Using Qdrant index: {qdrant_index}")
        
        project_root = Path(__file__).parent.parent.parent
        embedder_model_absolute_path = str(project_root / self._app_config.embedding_model_path)
        
        text_embedder = SentenceTransformersTextEmbedder(model=embedder_model_absolute_path)
        text_embedder.warm_up()
        query_with_embeddings = text_embedder.run(query_text)["embedding"]
        
        document_store = self._get_knowledge_base(qdrant_index, trace_id)

        if document_store is None:
            raise ValueError(f"No document store found for KB: {knowledge_base_name}, Version: {kb_version}")
        
        retriever = QdrantEmbeddingRetriever(document_store=document_store)
        retrieval_docs = retriever.run(query_embedding=query_with_embeddings)["documents"]
        
        # 封装检索结果
        resp = RetrievalQueryResponse(
            knowledge_base_name=knowledge_base_name, 
            kb_version=kb_version, 
            query_text=query_text, 
            results=[]
        )
        if len(retrieval_docs) < 1:
            logger.warning(f"No results found for query={query_text} in KB: {knowledge_base_name}, Version: {kb_version}")
            return resp

        for doc in retrieval_docs:
            sr = SearchResult(
                    chunk_id=doc.id,
                    content=doc.content,
                    score=doc.score,
                    source_document=doc.meta["file_path"],
                    metadata=doc.meta)
            resp.results.append(sr)
        
        # 删除embedder实例
        del text_embedder
        text_embedder = None
        
        # 强制清理GPU缓存
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            logger.info("GPU cache cleared and synchronized")
    
        return resp
        
        
        
        
        
        
