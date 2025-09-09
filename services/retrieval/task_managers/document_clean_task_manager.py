'''
Description: 文档清洗异步任务管理器, 负责文档清洗任务的管理和执行
Author: zyq
Date: 2025-09-09 15:29:58
LastEditors: zyq
LastEditTime: 2025-09-09 15:50:49
'''

import os
import tempfile
from typing import Dict, Any, List
from datetime import datetime
from loguru import logger
from bson import ObjectId
from haystack import Document
from haystack.components.converters.docx import DOCXToDocument

from core.tasks import (
    BaseTaskManager, TaskType, TaskStatus, BaseTask, BatchTask, TaskPriority,
    generate_task_id
)
from core.tasks.registry import task_registry, collection_registry
from core.storage.mongo_storage import MongoStorage

from ..schemas import (
    DocumentCleanRequest, DocumentCleanTaskResponse, CleanTaskStatusResponse,
    DocumentCleanSettings, FailedFileDetail, RetrievalTaskTypePrefix
)
from ..components.document_cleaner import DocumentCleaner
from ..managers.knowledge_manager import KnowledgeBaseManager


class DocumentCleanTaskManager(BaseTaskManager):
    """文档清洗异步任务管理器"""
    
    def __init__(self, queue_backend, storage_backend, config: Dict[str, Any] = None):
        """
        初始化文档清洗任务管理器
        
        Args:
            queue_backend: 队列后端
            storage_backend: 存储后端
            config: 配置参数
        """
        super().__init__(queue_backend, storage_backend, config)
        
        # 初始化相关组件
        self.document_cleaner = DocumentCleaner(config or {})
        self.knowledge_manager = KnowledgeBaseManager(config or {})
        
        # 注册任务函数到全局注册表
        task_registry.register('_process_document_clean', self._process_document_clean)
        self.task_id_prefix = RetrievalTaskTypePrefix.CLEAN_TASK.value
        
        # 注册collection映射和task_id前缀到全局注册表
        collection_registry.register(
            'document_clean_processing', 
            'document_clean_tasks',
            self.task_id_prefix  # 约束task_id前缀
        )
    
    def get_task_type(self) -> TaskType:
        """获取任务类型"""
        return TaskType.BATCH_PROCESSING
    
    
    async def submit_clean_task(
        self, 
        knowledge_base_name: str,
        clean_settings: DocumentCleanSettings,
        trace_id: str = None
    ) -> DocumentCleanTaskResponse:
        """
        提交文档清洗任务
        
        Args:
            knowledge_base_name: 知识库名称
            clean_settings: 清洗设置
            trace_id: 链路追踪ID
            
        Returns:
            文档清洗任务响应
        """
        logger.info(f"Submitting document clean task - TraceID: {trace_id} | KB: {knowledge_base_name}")
        
        try:
            # 1. 验证清洗设置
            self.document_cleaner.validate_settings(clean_settings)
            
            # 2. 检查知识库是否存在
            if not self.knowledge_manager.get_knowledge_base(knowledge_base_name):
                raise ValueError(f"知识库 '{knowledge_base_name}' 不存在")
            
            # 3. 生成清洗设置哈希值，用于版本化分块
            settings_hash = self.document_cleaner.generate_settings_hash(clean_settings)
            
            # 4. 获取知识库中所有文档（简化逻辑，不再检查状态）
            all_documents = self._get_knowledge_base_documents(knowledge_base_name, trace_id)
            
            if not all_documents:
                logger.info(f"No documents in knowledge base - TraceID: {trace_id}")
                # 知识库中没有文档，返回空任务
                task_id = generate_task_id(self.task_id_prefix)
                return DocumentCleanTaskResponse(
                    clean_task_id=task_id,
                    knowledge_base_name=knowledge_base_name,
                    total_pending_files=0,
                    created_at=datetime.now().isoformat()
                )
            
            # 5. 统一构建任务参数
            task_params = {
                'knowledge_base_name': knowledge_base_name,
                'clean_settings': clean_settings.model_dump(),
                'settings_hash': settings_hash,
                'documents': all_documents,
                'total_files': len(all_documents),
                'trace_id': trace_id
            }
            
            # 6. 提交任务到队列
            task_id = await self.submit_task(
                self._process_document_clean,
                task_params
            )
            
            return DocumentCleanTaskResponse(
                clean_task_id=task_id,
                knowledge_base_name=knowledge_base_name,
                total_pending_files=len(all_documents),
                created_at=datetime.now().isoformat()
            )
            
        except Exception as e:
            logger.error(f"Failed to submit document clean task: {str(e)}")
            raise
    
    async def create_task_instance(self, **kwargs) -> BatchTask:
        """
        创建批处理任务实例（版本化支持）
        
        Args:
            **kwargs: 任务创建参数，包含:
                - total_files: 待处理文件数量
                - knowledge_base_name: 知识库名称
                - settings_hash: 清洗设置哈希值
                - trace_id: 追踪ID等
                
        Returns:
            BatchTask实例
        """
        task_id = generate_task_id(self.task_id_prefix)
        total_files = kwargs.get('total_files', 0)
        knowledge_base_name = kwargs.get('knowledge_base_name', '')
        settings_hash = kwargs.get('settings_hash', '')
        
        return BatchTask(
            task_id=task_id,
            task_type='batch_processing',
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            total_items=total_files,  # 这是关键字段
            processed_items=0,
            timeout=self.config.get('task_timeout', 3600),
            max_retries=self.config.get('max_retries', 2),
            metadata={
                'collection_type': 'document_clean_processing',  # 添加collection映射
                'knowledge_base_name': knowledge_base_name,
                'total_files': total_files,
                'clean_settings': kwargs.get('clean_settings'),
                'settings_hash': settings_hash,
                'version_info': f"kb_{knowledge_base_name}_{settings_hash[:8]}" if settings_hash else f"kb_{knowledge_base_name}_default"
            },
            trace_id=kwargs.get('trace_id')
        )

    async def get_clean_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        获取文档清洗任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            符合CleanTaskStatusResponse格式的任务状态信息
        """
        try:
            # 直接从MongoDB存储中获取完整文档（包含result字段）
            task_type_key = self.storage_backend._extract_task_type_key_from_id(task_id)
            storage = self.storage_backend.get_storage_instance(task_type_key)
            
            records = storage.find_record({'task_id': task_id})
            if not records:
                return None
                
            task_doc = records[0]  # MongoDB文档包含所有字段
            
            # 构建符合CleanTaskStatusResponse的响应格式
            status_value = task_doc.get('status', 'unknown').lower()
            
            # 从任务metadata中获取基本信息
            metadata = task_doc.get('metadata', {})
            knowledge_base_name = metadata.get('knowledge_base_name', 'unknown')
            total_files = metadata.get('total_files', 0)
            
            result = {
                'clean_task_id': task_id,
                'status': status_value,  # pending | processing | completed | failed | cancelled
                'knowledge_base_name': knowledge_base_name,
                'total_files': total_files,
                'processed_files': 0,
                'successful_files': 0,
                'failed_files': 0,
                'total_chunks': 0,
                'created_at': task_doc.get('created_at', datetime.now().isoformat()),
                'started_at': task_doc.get('started_at'),
                'completed_at': task_doc.get('completed_at'),
                'error_message': task_doc.get('error_message'),
                'failed_files_detail': []
            }
            
            # 从MongoDB文档的result字段中提取详细统计信息
            task_result = task_doc.get('result')
            if task_result and isinstance(task_result, dict):
                result.update({
                    'processed_files': task_result.get('processed_files', 0),
                    'successful_files': task_result.get('successful_files', 0),
                    'failed_files': task_result.get('failed_files', 0),
                    'total_chunks': task_result.get('total_chunks', 0),
                    'failed_files_detail': task_result.get('failed_files_detail', [])
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get document clean task status: {str(e)}")
            return None
    
    async def _process_document_clean(
        self,
        knowledge_base_name: str,
        clean_settings: Dict[str, Any],
        settings_hash: str,
        documents: List[Dict],
        total_files: int,
        trace_id: str = None,
        task_id: str = None
    ) -> Dict[str, Any]:
        """
        处理文档清洗任务的核心函数（版本化分块）
        
        Args:
            knowledge_base_name: 知识库名称
            clean_settings: 清洗设置字典
            settings_hash: 设置哈希值（用于版本化）
            documents: 文档列表
            total_files: 文件总数
            trace_id: 链路追踪ID
            task_id: 任务ID
            
        Returns:
            处理结果字典
        """
        # 如果没有传递task_id，尝试从ARQ context获取
        if not task_id:
            try:
                from arq.worker import current_ctx
                ctx = current_ctx.get()
                if ctx and hasattr(ctx, 'job_id'):
                    task_id = ctx.job_id
            except:
                pass
        
        logger.info(f"Processing document clean task: {task_id} | KB: {knowledge_base_name} | Files: {total_files} | Hash: {settings_hash[:8]}...")
        
        # 更新任务状态为处理中
        if task_id:
            await self.storage_backend.update_task_status(task_id, TaskStatus.PROCESSING)
        
        try:
            # 重构清洗设置对象
            clean_settings_obj = DocumentCleanSettings(**clean_settings)
            
            # 将数据库记录转换为Haystack Document对象
            haystack_documents = self._convert_to_haystack_documents(documents, trace_id)
            
            if not haystack_documents:
                raise Exception("没有有效的文档可供清洗")
            
            # 执行文档清洗（统一异步处理）
            chunks, stats, failed_docs = await self.document_cleaner.clean_documents_batch_with_timeout(
                haystack_documents, clean_settings_obj, trace_id
            )
            
            # 保存清洗结果到版本化的Qdrant索引（不再更新文档状态）
            self._save_versioned_chunks(
                knowledge_base_name, chunks, settings_hash, failed_docs, trace_id
            )
            
            # 构建符合CleanTaskStatusResponse格式的结果
            failed_file_details = [
                {
                    'filename': failed['filename'],
                    'error_message': failed['error_message'],
                    'error_code': failed.get('error_code')
                }
                for failed in failed_docs
            ]
            
            result = {
                'clean_task_id': task_id,
                'status': 'completed',
                'knowledge_base_name': knowledge_base_name,
                'settings_hash': settings_hash,
                'total_files': len(documents),
                'processed_files': len(documents),
                'successful_files': stats['success_documents'],
                'failed_files': len(failed_docs),
                'total_chunks': stats['output_chunks'],
                'failed_files_detail': failed_file_details
            }
            
            # 更新任务状态为完成
            if task_id:
                await self.storage_backend.update_task_status(
                    task_id,
                    TaskStatus.COMPLETED,
                    completed_at=datetime.now(),
                    processed_items=len(documents),  # 添加processed_items字段
                    result=result
                )
            
            logger.info(f"Document clean task completed: {task_id} | Success: {stats['success_documents']} | Failed: {len(failed_docs)} | Chunks: {stats['output_chunks']}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to process document clean task {task_id}: {str(e)}")
            
            # 构建失败结果
            result = {
                'clean_task_id': task_id,
                'status': 'failed',
                'knowledge_base_name': knowledge_base_name,
                'settings_hash': settings_hash,
                'total_files': total_files,
                'processed_files': 0,
                'successful_files': 0,
                'failed_files': total_files,
                'total_chunks': 0,
                'failed_files_detail': []
            }
            
            # 更新任务状态为失败
            if task_id:
                await self.storage_backend.update_task_status(
                    task_id,
                    TaskStatus.FAILED,
                    completed_at=datetime.now(),
                    error_message=str(e),
                    result=result
                )
            
            return result
    
    def _get_knowledge_base_documents(self, 
                                     knowledge_base_name: str,
                                     trace_id: str = None) -> List[Dict]:
        """
        获取知识库中的所有文档（简化逻辑，不再检查清洗状态）
        
        Args:
            knowledge_base_name: 知识库名称
            trace_id: 请求追踪ID
            
        Returns:
            文档列表
        """
        logger.info(f"Getting all documents in knowledge base - TraceID: {trace_id}, KB: {knowledge_base_name}")
        
        # 获取文档存储实例
        doc_storage = MongoStorage(
            db_name=self.config.get('retrieval_db_name', 'ai_backend_services_retrieval'),
            collection_name=self.config.get('retrieval_document_collection_name', 'retrieval_documents')
        )
        
        # 简化查询：只匹配知识库名称
        query = {"knowledge_base_name": knowledge_base_name}
        
        documents = doc_storage.find_record(query)
        logger.info(f"Found {len(documents)} documents in knowledge base - TraceID: {trace_id}")
        
        return documents
    
    def _convert_to_haystack_documents(self, 
                                     db_documents: List[Dict], 
                                     trace_id: str = None) -> List[Document]:
        """
        将数据库文档记录转换为Haystack Document对象
        
        Args:
            db_documents: 数据库文档记录列表
            trace_id: 请求追踪ID
            
        Returns:
            Haystack Document对象列表
        """
        logger.info(f"Converting to Haystack documents - TraceID: {trace_id}, Count: {len(db_documents)}")
        
        haystack_docs = []
        docx_converter = DOCXToDocument()
        
        # 获取文档存储实例用于读取GridFS文件
        doc_storage = MongoStorage(
            db_name=self.config.get('retrieval_db_name', 'ai_backend_services_retrieval'),
            collection_name=self.config.get('retrieval_document_collection_name', 'retrieval_documents')
        )
        
        for db_doc in db_documents:
            try:
                filename = db_doc.get("original_filename", db_doc.get("filename", "unknown.docx"))
                gridfs_file_id = db_doc.get("gridfs_file_id")
                
                if not gridfs_file_id:
                    logger.error(f"No GridFS file ID for document - TraceID: {trace_id}, File: {filename}")
                    continue
                
                # 从GridFS读取文件内容
                file_content = doc_storage.get_file_content_from_gridfs(ObjectId(gridfs_file_id))
                
                if not file_content:
                    logger.error(f"Failed to read from GridFS - TraceID: {trace_id}, File: {filename}")
                    continue
                
                # 创建临时文件进行转换
                with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as temp_file:
                    temp_file.write(file_content)
                    temp_file_path = temp_file.name
                
                try:
                    # 使用Haystack DOCXToDocument转换器
                    result = docx_converter.run(sources=[temp_file_path])
                    converted_docs = result.get("documents", [])
                    
                    # 更新每个转换后的Document的元数据
                    for doc in converted_docs:
                        doc.meta.update({
                            "filename": filename,
                            "knowledge_base_name": db_doc.get("knowledge_base_name", ""),
                            "document_id": str(db_doc.get("_id", "")),
                            "original_file_size": db_doc.get("file_size", 0),
                            "upload_time": db_doc.get("upload_time")
                        })
                    haystack_docs.extend(converted_docs)
                finally:
                    # 清理临时文件
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
                        
            except Exception as e:
                logger.error(f"Failed to convert document - TraceID: {trace_id}, File: {db_doc.get('filename', 'unknown')}: {str(e)}")
                continue
        
        logger.info(f"Converted {len(haystack_docs)} Haystack documents from {len(db_documents)} DB records - TraceID: {trace_id}")
        return haystack_docs
    
    def _save_versioned_chunks(self,
                              knowledge_base_name: str,
                              chunks: List[Document],
                              settings_hash: str,
                              failed_docs: List[Dict],
                              trace_id: str = None):
        """
        保存清洗结果到版本化的Qdrant索引（不再更新文档状态）
        
        Args:
            knowledge_base_name: 知识库名称
            chunks: 清洗后的文档块
            settings_hash: 清洗设置哈希值（用于版本化）
            failed_docs: 失败文档列表
            trace_id: 请求追踪ID
        """
        logger.info(f"Saving versioned chunks - TraceID: {trace_id}, KB: {knowledge_base_name}, Hash: {settings_hash[:8]}..., Chunks: {len(chunks)}")
        
        try:
            if chunks:
                from core.config.config_center import get_app_config
                from haystack_integrations.document_stores.qdrant import QdrantDocumentStore
                
                # 获取应用配置
                app_config = get_app_config()
                
                # 创建版本化的Qdrant索引名称：kb_{知识库名}_{设置hash前8位}
                versioned_index = f"kb_{knowledge_base_name}_{settings_hash[:8]}"
                
                document_store = QdrantDocumentStore(
                    host=app_config.qdrant_host,
                    port=app_config.qdrant_port,
                    index=versioned_index,  # 使用版本化索引
                    embedding_dim=app_config.embedding_dim,
                    recreate_index=True,  # 总是重新创建，确保版本纯净
                    return_embedding=True,
                    wait_result_from_api=True,
                    timeout=app_config.qdrant_timeout
                )
                
                # 为每个chunk添加版本化的元数据
                for i, chunk in enumerate(chunks):
                    chunk.meta.update({
                        "chunk_index": i,
                        "chunk_size": len(chunk.content or ""),
                        "settings_hash": settings_hash,
                        "created_at": datetime.now().isoformat(),
                        "knowledge_base_name": knowledge_base_name,
                        "version_index": versioned_index
                    })
                
                # 批量写入版本化的Qdrant索引
                document_store.write_documents(chunks)
                logger.info(f"Saved {len(chunks)} chunks to versioned Qdrant index: {versioned_index} - TraceID: {trace_id}")
            
            # 不再更新文档状态 - 这是关键简化！
            logger.info(f"Versioned chunks saved successfully - TraceID: {trace_id}")
            
        except Exception as e:
            logger.error(f"Failed to save versioned chunks - TraceID: {trace_id}: {str(e)}")
            raise