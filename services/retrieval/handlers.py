'''
Description: Retrieval服务业务逻辑处理器
Author: zyq
Date: 2025-09-15 17:19:58
LastEditors: zyq
LastEditTime: 2025-10-11 10:26:27
'''

import os
import tempfile
from typing import Dict, Any, List
from datetime import datetime
from fastapi import UploadFile
from loguru import logger
from bson import ObjectId
from pathlib import Path
from haystack import Document
from haystack.components.converters.docx import DOCXToDocument
from haystack_integrations.document_stores.qdrant import QdrantDocumentStore
from haystack.components.embedders import SentenceTransformersTextEmbedder
from haystack_integrations.components.retrievers.qdrant import QdrantEmbeddingRetriever

from core.storage.mongo_storage import MongoStorage
from core.config.config_center import get_app_config
from core.tasks import TaskManagerFactory

from .components.document_processor import DocumentProcessor
from .components.document_cleaner import DocumentCleaner
from .managers.knowledge_manager import KnowledgeBaseManager
from .task_managers.knowledge_base_build_task_manager import KnowledgeBaseBuildTaskManager
from .schemas import (
    RetrievalUploadResponse, FileUploadResult,
    KnowledgeBaseBuildResponse, DocumentCleanSettings,
    RetrievalTaskTypePrefix, RetrievalQueryResponse, SearchResult,
    KnowledgeBaseQueryResponse, KnowledgeBaseInfo
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
    
    async def initialize(self):
        """轻量级初始化Retrieval服务处理器"""
        # 初始化基础组件
        self.document_processor = DocumentProcessor(self.config)
        self.document_cleaner = DocumentCleaner(self.config)
        self.knowledge_manager = KnowledgeBaseManager(self.config)
        
        # 创建任务管理后端
        queue_backend, storage_backend = TaskManagerFactory.create_default_backends()
        
        # 初始化知识库构建任务管理器
        self.build_task_manager = KnowledgeBaseBuildTaskManager(
            queue_backend,
            storage_backend,
            self.config
        )
        
        logger.info("Retrieval handlers初始化完成")
    
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
        app_config = get_app_config()
        document_store = None
        
        document_store = QdrantDocumentStore(
            host=app_config.qdrant_host,
            port=app_config.qdrant_port,
            index=kb_name_with_version,  # 使用版本化索引
            embedding_dim=app_config.embedding_dim,
            return_embedding=True,
            wait_result_from_api=True,
            timeout=app_config.qdrant_timeout
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
        
        app_config = get_app_config()
        
        project_root = Path(__file__).parent.parent.parent
        embedder_model_absolute_path = str(project_root / app_config.embedding_model_path)
        
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
        
        
        
        
        
        