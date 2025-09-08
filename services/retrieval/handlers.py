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

from core.storage.mongo_storage import MongoStorage

from .components.document_processor import DocumentProcessor
from .components.document_cleaner import DocumentCleaner
from .managers.knowledge_manager import KnowledgeBaseManager
from .schemas import (
    RetrievalUploadResponse, FileUploadResult,
    DocumentCleanRequest, DocumentCleanResponse, DocumentCleanSettings,
    FailedFileDetail
)


class RetrievalHandlers:
    """Retrieval服务业务逻辑处理器"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化Retrieval处理器"""
        self.config = config
        self.document_processor = None
        self.document_cleaner = None
        self.knowledge_manager = None
    
    async def initialize(self):
        """轻量级初始化Retrieval服务处理器"""
        self.document_processor = DocumentProcessor(self.config)
        self.document_cleaner = DocumentCleaner(self.config)
        self.knowledge_manager = KnowledgeBaseManager(self.config)
        logger.info("Retrieval handlers初始化完成")
    
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
                        error_message="创建知识库失败"
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
                    # 上传文档
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
    
    async def clean_documents(self,
                             knowledge_base_name: str,
                             clean_settings: DocumentCleanSettings,
                             trace_id: str = None) -> DocumentCleanResponse:
        """
        清洗知识库中的文档
        
        Args:
            knowledge_base_name: 知识库名称
            clean_settings: 清洗设置
            trace_id: 请求追踪ID
            
        Returns:
            清洗结果响应
        """
        logger.info(f"Start cleaning documents - TraceID: {trace_id}, KB: {knowledge_base_name}")
        
        # 1. 验证清洗设置
        self.document_cleaner.validate_settings(clean_settings)
        
        # 2. 检查知识库是否存在
        if not self.knowledge_manager.get_knowledge_base(knowledge_base_name):
            raise ValueError(f"知识库 '{knowledge_base_name}' 不存在")
        
        # 3. 生成清洗设置哈希值，用于判断是否需要重新清洗
        settings_hash = self.document_cleaner.generate_settings_hash(clean_settings)
        
        # 4. 获取需要清洗的文档（跳过已用相同设置清洗过的文档）
        pending_documents = self._get_pending_documents_for_cleaning(
            knowledge_base_name, settings_hash, trace_id
        )
        
        if not pending_documents:
            logger.info(f"No documents need cleaning - TraceID: {trace_id}")
            return DocumentCleanResponse(
                knowledge_base_name=knowledge_base_name,
                total_files=0,
                success_count=0,
                failed_count=0,
                total_chunks=0,
                failed_files=[]
            )
        
        # 5. 判断处理模式
        processing_mode = self.document_cleaner.determine_processing_mode(len(pending_documents))
        logger.info(f"Processing mode determined - TraceID: {trace_id}, Mode: {processing_mode}, Count: {len(pending_documents)}")
        
        # 6. 将数据库记录转换为Haystack Document对象
        haystack_documents = self._convert_to_haystack_documents(pending_documents, trace_id)
        
        # 7. 执行文档清洗
        if processing_mode == 'sync':
            # 同步处理
            chunks, stats, failed_docs = await self.document_cleaner.clean_documents_batch_with_timeout(
                haystack_documents, clean_settings, trace_id
            )
        else:
            # 异步处理
            chunks, stats, failed_docs = await self.document_cleaner.clean_documents_in_chunks_with_timeout(
                haystack_documents, clean_settings, trace_id
            )
        
        # 8. 保存清洗结果和更新文档状态
        self._save_cleaning_results(
            knowledge_base_name, chunks, pending_documents, 
            settings_hash, failed_docs, trace_id
        )
        
        # 9. 构建响应
        failed_file_details = [
            FailedFileDetail(
                filename=failed['filename'],
                error_message=failed['error_message'],
                error_code=failed.get('error_code')
            )
            for failed in failed_docs
        ]
        
        logger.info(f"Document cleaning completed - TraceID: {trace_id}, Success: {stats['success_documents']}, Failed: {len(failed_docs)}, Chunks: {stats['output_chunks']}")
        
        return DocumentCleanResponse(
            knowledge_base_name=knowledge_base_name,
            total_files=len(pending_documents),
            success_count=stats['success_documents'],
            failed_count=len(failed_docs),
            total_chunks=stats['output_chunks'],
            failed_files=failed_file_details
        )
    
    def _get_pending_documents_for_cleaning(self, 
                                           knowledge_base_name: str, 
                                           settings_hash: str,
                                           trace_id: str = None) -> List[Dict]:
        """
        获取需要清洗的文档（跳过已清洗且设置未变的文档）
        
        Args:
            knowledge_base_name: 知识库名称
            settings_hash: 清洗设置哈希值
            trace_id: 请求追踪ID
            
        Returns:
            需要清洗的文档列表
        """
        logger.info(f"Getting pending documents for cleaning - TraceID: {trace_id}, KB: {knowledge_base_name}")
        
        # 获取文档存储实例
        doc_storage = MongoStorage(
            db_name=self.config.get('retrieval_db_name', 'ai_backend_services_retrieval'),
            collection_name=self.config.get('retrieval_document_collection_name', 'retrieval_documents')
        )
        
        # 查询条件：知识库匹配 且 (未清洗过 或 清洗设置变化了)
        query = {
            "knowledge_base_name": knowledge_base_name,
            "$or": [
                {"clean_status": {"$ne": "completed"}},  # 未清洗完成
                {"clean_settings_hash": {"$ne": settings_hash}},  # 设置变化了
                {"clean_settings_hash": {"$exists": False}}  # 从未清洗过
            ]
        }
        
        pending_docs = doc_storage.find_record(query)
        logger.info(f"Found {len(pending_docs)} documents need cleaning - TraceID: {trace_id}")
        
        return pending_docs
    
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
        
        for db_doc in db_documents:
            try:
                filename = db_doc.get("filename", "unknown.docx")
                gridfs_file_id = db_doc.get("gridfs_file_id")
                
                if not gridfs_file_id:
                    logger.error(f"No GridFS file ID for document - TraceID: {trace_id}, File: {filename}")
                    continue
                
                # 从GridFS读取文件内容
                file_content = self.document_processor.mongo_storage.gridfs_get_file(ObjectId(gridfs_file_id))
                
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
                    logger.debug(f"Converted document - TraceID: {trace_id}, File: {filename}, Chunks: {len(converted_docs)}")
                    
                finally:
                    # 清理临时文件
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
                        
            except Exception as e:
                logger.error(f"Failed to convert document - TraceID: {trace_id}, File: {db_doc.get('filename', 'unknown')}: {str(e)}")
                continue
        
        logger.info(f"Converted {len(haystack_docs)} Haystack documents from {len(db_documents)} DB records - TraceID: {trace_id}")
        return haystack_docs
    
    def _save_cleaning_results(self,
                              knowledge_base_name: str,
                              chunks: List[Document],
                              original_documents: List[Dict],
                              settings_hash: str,
                              failed_docs: List[Dict],
                              trace_id: str = None):
        """
        保存清洗结果并更新文档状态
        
        Args:
            knowledge_base_name: 知识库名称
            chunks: 清洗后的文档块
            original_documents: 原始文档记录
            settings_hash: 清洗设置哈希值
            failed_docs: 失败文档列表
            trace_id: 请求追踪ID
        """
        logger.info(f"Saving cleaning results - TraceID: {trace_id}, Chunks: {len(chunks)}, Failed: {len(failed_docs)}")
        
        # TODO: 实现保存逻辑
        # 1. 将chunks保存到专门的chunks集合
        # 2. 更新原始文档的clean_status和clean_settings_hash
        # 3. 更新知识库统计信息
        
        pass