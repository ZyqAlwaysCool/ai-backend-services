'''
Description: Retrieval服务业务逻辑处理器
Author: zyq
Date: 2025-09-08
'''

import os
import tempfile
from typing import Dict, Any, List
from datetime import datetime
from fastapi import UploadFile
from loguru import logger
from bson import ObjectId
from haystack import Document
from haystack.components.converters.docx import DOCXToDocument
from haystack_integrations.document_stores.qdrant import QdrantDocumentStore

from core.storage.mongo_storage import MongoStorage
from core.config.config_center import get_app_config
from core.tasks import TaskManagerFactory

from .components.document_processor import DocumentProcessor
from .components.document_cleaner import DocumentCleaner
from .managers.knowledge_manager import KnowledgeBaseManager
from .task_managers.knowledge_base_build_task_manager import KnowledgeBaseBuildTaskManager
from .schemas import (
    RetrievalUploadResponse, FileUploadResult,
    KnowledgeBaseBuildRequest, KnowledgeBaseBuildResponse, BuildTaskStatusResponse, DocumentCleanSettings,
    FailedFileDetail, RetrievalTaskTypePrefix
)


class RetrievalHandlers:
    """Retrieval服务业务逻辑处理器"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化Retrieval处理器"""
        self.config = config
        self.document_processor = None
        self.document_cleaner = None
        self.knowledge_manager = None
        self.document_stores = {}  # 缓存每个知识库的DocumentStore
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
    
    def _get_document_store(self, knowledge_base_name: str) -> QdrantDocumentStore:
        """获取或创建知识库对应的QdrantDocumentStore"""
        if knowledge_base_name not in self.document_stores:
            # 获取应用配置
            app_config = get_app_config()
            
            # 为每个知识库创建独立的collection
            self.document_stores[knowledge_base_name] = QdrantDocumentStore(
                host=app_config.qdrant_host,
                port=app_config.qdrant_port,
                index=f"kb_{knowledge_base_name}",  # 每个知识库使用独立的index
                embedding_dim=app_config.embedding_dim,
                recreate_index=False,
                return_embedding=True,
                wait_result_from_api=True,
                timeout=app_config.qdrant_timeout
            )
            logger.info(f"Created Qdrant DocumentStore for knowledge base: {knowledge_base_name} (host: {app_config.qdrant_host}:{app_config.qdrant_port})")
        
        return self.document_stores[knowledge_base_name]
    
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
                    status="failed",
                    error_message=f"单次请求最多只能上传{max_files_per_request}个文件，当前上传{len(files)}个"
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
                        status="failed",
                        error_message="知识库创建失败"
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
                        status="failed",
                        error_message=f"文件大小超出限制，最大允许{max_file_size // 1024 // 1024}MB，当前{file_size // 1024 // 1024}MB"
                    ))
                    failed_count += 1
                    continue
                
                # 验证文件格式
                if not file.filename.lower().endswith('.docx'):
                    upload_results.append(FileUploadResult(
                        filename=file.filename,
                        file_size=file_size,
                        upload_time=datetime.now(),
                        status="failed",
                        error_message="仅支持DOCX格式文件"
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
                    
                    if result["status"] == "success":
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
                    status="failed",
                    error_message=f"处理失败: {str(e)}"
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
