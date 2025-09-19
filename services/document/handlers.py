'''
Description: 文档类服务业务逻辑处理器
Author: zyq
Date: 2025-08-27 15:33:18
LastEditors: zyq
LastEditTime: 2025-09-19 10:31:41
'''

from typing import Dict, Any
from datetime import datetime
import uuid
from loguru import logger

from core.schemas.file_models import FileInfo
from core.tasks import TaskManagerFactory
from core.exceptions import BaseBusinessException
from core.config.error_codes import *
from .schemas import (
    PDFParserRequest, PDFParserResponse,
    PDFParserBatchRequest, PDFParserBatchResponse,
    PDFParserTaskStatusResponse,
    DocumentConvertRequest, DocumentConvertResponse,
    ConvertTaskStatusResponse, TextExtractRequest, TextExtractResponse,
    TextExtractBatchRequest, TextExtractBatchResponse,
    ExtractTaskStatusResponse,
    TableExtractRequest, TableExtractResponse,
)
from .processors import PDFProcessor
from .processors.text_processor import TextProcessor
from .processors.table_processor import TableProcessor
from .task_managers import PDFBatchTaskManager
from .task_managers.document_convert_task_manager import DocumentConvertTaskManager
from .task_managers.text_extract_batch_manager import TextExtractBatchTaskManager
from ..services_err_codes import *


class DocumentHandlers:
    """Document服务业务逻辑处理器"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化Document处理器"""
        self.config = config
        # 初始化各种处理器
        self.pdf_processor = PDFProcessor(config)
        self.text_processor = TextProcessor(config)
        self.table_processor = TableProcessor(config)
        # 任务管理器将在初始化时创建
        self.pdf_batch_manager = None
        self.convert_task_manager = None
        self.text_extract_batch_manager = None
    
    async def initialize(self):
        """轻量级初始化Document服务处理器"""
        # 创建任务管理后端
        queue_backend, storage_backend = TaskManagerFactory.create_default_backends()
        
        # 初始化PDF批处理任务管理器
        self.pdf_batch_manager = PDFBatchTaskManager(
            queue_backend, 
            storage_backend, 
            self.config
        )
        
        # 初始化文档转换任务管理器
        self.convert_task_manager = DocumentConvertTaskManager(
            queue_backend,
            storage_backend,
            self.config
        )
        
        # 初始化文本提取批处理任务管理器
        self.text_extract_batch_manager = TextExtractBatchTaskManager(
            queue_backend,
            storage_backend,
            self.config
        )
        
        logger.info("Document handlers initialized")
    
    # ==================== PDF处理接口 ====================
    
    async def pdf_parser(self, request: PDFParserRequest, temp_file_path: str, file_info: FileInfo, trace_id: str = None) -> PDFParserResponse:
        """PDF解析处理,提取文本、图片、表格内容"""
        return await self.pdf_processor.process(request, temp_file_path, file_info, trace_id)
    
    async def pdf_parser_batch(self, request: PDFParserBatchRequest, trace_id: str = None) -> PDFParserBatchResponse:
        """PDF批量解析处理"""
        logger.info(f"PDF batch request started files={len(request.files)} | TraceID: {trace_id}")
        
        if not self.pdf_batch_manager:
            raise BaseBusinessException(code=DOCUMENT_SERVICE_PDF_BATCH_TASK_MANAGER_INIT_ERROR,
                                        message=get_service_error_message(DOCUMENT_SERVICE_PDF_BATCH_TASK_MANAGER_INIT_ERROR))
        
        try:
            # 提交批处理任务到任务管理器
            return await self.pdf_batch_manager.submit_pdf_batch_task(request, trace_id)
        except Exception as e:
            # 捕获任务管理器运行时错误，包括Worker不可用
            logger.error(f"submit pdf batch task failed. error={str(e)} | TraceID: {trace_id}")
            raise BaseBusinessException(code=DOCUMENT_SERVICE_SUBMIT_TASK_ERROR,
                                        message=get_service_error_message(DOCUMENT_SERVICE_SUBMIT_TASK_ERROR))
    
    async def query_pdf_parser_task(self, task_id: str, trace_id: str = None) -> PDFParserTaskStatusResponse:
        """查询PDF批量解析任务状态"""
        logger.info(f"Query PDF parser task task_id={task_id} | TraceID: {trace_id}")
        
        if not self.pdf_batch_manager:
            raise BaseBusinessException(code=DOCUMENT_SERVICE_PDF_BATCH_TASK_MANAGER_INIT_ERROR,
                                        message=get_service_error_message(DOCUMENT_SERVICE_PDF_BATCH_TASK_MANAGER_INIT_ERROR))
        
        # 从任务管理器获取任务状态
        task_status = await self.pdf_batch_manager.get_batch_task_status(task_id)
        
        if not task_status:
            # 任务不存在
            return PDFParserTaskStatusResponse(
                pdf_parser_batch_task_id=task_id,
                status="not_found",
                results=None
            )
        
        # 转换为PDFParserTaskStatusResponse格式
        return PDFParserTaskStatusResponse(
            pdf_parser_batch_task_id=task_id,
            status=task_status['status'],
            results=task_status.get('results', [])
        )
    
    # ==================== 文档转换接口 ====================
    
    async def document_convert(self, request: DocumentConvertRequest, temp_file_path: str, file_info: FileInfo, trace_id: str = None) -> DocumentConvertResponse:
        """文档格式转换处理"""
        logger.info(f"Document convert request started source={request.source_format} target={request.target_format} | TraceID: {trace_id}")
        
        # 1. 前置校验：相同格式拦截
        if request.source_format == request.target_format:
            raise ValueError(f"不支持相同格式转换: {request.source_format}")
        
        # 2. 检查转换类型是否支持
        supported_conversions = [
            ('docx', 'pdf'), ('docx', 'markdown'),
            ('xlsx', 'pdf'), ('xlsx', 'docx'), ('xlsx', 'markdown'),
            ('markdown', 'pdf'), ('markdown', 'docx')
        ]
        
        if (request.source_format, request.target_format) not in supported_conversions:
            raise ValueError(f"不支持的转换类型: {request.source_format} → {request.target_format}")
        
        # 3. 提交异步转换任务
        if not self.convert_task_manager:
            raise BaseBusinessException(code=DOCUMENT_SERVICE_CONVERT_TASK_MANAGER_INIT_ERROR,
                                        message=get_service_error_message(DOCUMENT_SERVICE_CONVERT_TASK_MANAGER_INIT_ERROR))
        
        return await self.convert_task_manager.submit_convert_task(request, temp_file_path, file_info, trace_id)
    
    async def query_convert_task(self, convert_task_id: str, trace_id: str = None) -> ConvertTaskStatusResponse:
        """查询格式转换任务状态"""
        logger.info(f"Query convert task task_id={convert_task_id} | TraceID: {trace_id}")
        
        if not self.convert_task_manager:
            raise BaseBusinessException(code=DOCUMENT_SERVICE_CONVERT_TASK_MANAGER_INIT_ERROR,
                                        message=get_service_error_message(DOCUMENT_SERVICE_CONVERT_TASK_MANAGER_INIT_ERROR))
        
        # 从任务管理器获取状态
        task_status = await self.convert_task_manager.get_convert_task_status(convert_task_id)
        
        if not task_status:
            return ConvertTaskStatusResponse(
                convert_task_id=convert_task_id,
                status="not_found",
                download_url=None,
                error_message="任务不存在",
                created_at="",
                completed_at=None,
                source_format="unknown",
                target_format="unknown"
            )
        
        return ConvertTaskStatusResponse(**task_status)
    
    # ==================== 文本提取接口 ====================
    
    async def text_extract(self, request: TextExtractRequest, temp_file_path: str, file_info: FileInfo, trace_id: str = None) -> TextExtractResponse:
        """文本提取处理"""
        logger.info(f"Text extract request started filename={request.filename} temp_file={temp_file_path} | TraceID: {trace_id}")
        
        # 调用文本处理器进行提取
        return await self.text_processor.process(request, temp_file_path, file_info, trace_id)
    
    async def text_extract_batch(self, request: TextExtractBatchRequest, trace_id: str = None) -> TextExtractBatchResponse:
        """文本提取批处理处理"""
        logger.info(f"Text extract batch request started files={len(request.files)} | TraceID: {trace_id}")
        
        if not self.text_extract_batch_manager:
            raise RuntimeError("Text extract batch task manager not initialized")
        
        try:
            # 提交批处理任务到任务管理器
            return await self.text_extract_batch_manager.submit_text_extract_batch_task(request, trace_id)
        except RuntimeError as e:
            logger.error(f"Text extract batch task submission failed error={str(e)} | TraceID: {trace_id}")
            raise RuntimeError(f"批量处理服务暂时不可用，请稍后重试。详细错误：{str(e)}")
        except Exception as e:
            logger.error(f"Text extract batch request unexpected error error={str(e)} | TraceID: {trace_id}")
            raise RuntimeError(f"处理请求时发生未知错误，请联系系统管理员。")
    
    async def query_extract_task(self, batch_task_id: str, trace_id: str = None) -> ExtractTaskStatusResponse:
        """查询文本提取批处理任务状态"""
        logger.info(f"Query extract task batch_task_id={batch_task_id} | TraceID: {trace_id}")
        
        if not self.text_extract_batch_manager:
            raise BaseBusinessException(code=DOCUMENT_SERVICE_TEXT_EXTRACT_TASK_MANAGER_INIT_ERROR,
                                        message=get_service_error_message(DOCUMENT_SERVICE_TEXT_EXTRACT_TASK_MANAGER_INIT_ERROR))
        
        # 从任务管理器获取任务状态
        task_status = await self.text_extract_batch_manager.get_extract_batch_task_status(batch_task_id)
        
        if not task_status:
            return ExtractTaskStatusResponse(
                text_extract_batch_task_id=batch_task_id,
                status="not_found",
                results=None
            )
        
        # 转换为ExtractTaskStatusResponse格式
        return ExtractTaskStatusResponse(
            text_extract_batch_task_id=batch_task_id,
            status=task_status['status'],
            results=task_status.get('results', [])
        )
    
    # ==================== 表格提取接口 ====================
    
    async def table_extract(self, request: TableExtractRequest, temp_file_path: str, file_info: FileInfo, trace_id: str = None) -> TableExtractResponse:
        """表格提取处理"""
        logger.info(f"Table extract request started filename={request.filename} temp_file={temp_file_path} | TraceID: {trace_id}")
        
        # 调用表格处理器进行提取
        return await self.table_processor.process(request, temp_file_path, file_info, trace_id)