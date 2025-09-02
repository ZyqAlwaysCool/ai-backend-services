'''
Description: 文档类服务业务逻辑处理器
Author: zyq
Date: 2025-08-27 15:33:18
LastEditors: zyq
LastEditTime: 2025-09-01 16:36:45
'''

from typing import Dict, Any
from datetime import datetime
import uuid
from loguru import logger

from core.schemas.file_models import FileInfo
from core.tasks import TaskManagerFactory
from .schemas import (
    PDFParserRequest, PDFParserResponse,
    PDFParserBatchRequest, PDFParserBatchResponse,
    PDFParserTaskStatusResponse,
    DocumentConvertRequest, DocumentConvertResponse,
    ConvertTaskStatusResponse, TextExtractRequest, TextExtractResponse,
    TextExtractBatchRequest, TextExtractBatchResponse,
    ExtractTaskStatusResponse,
    TableExtractRequest, TableExtractResponse
)
from .processors import PDFProcessor
from .task_managers import PDFBatchTaskManager
from .task_managers.document_convert_task_manager import DocumentConvertTaskManager


class DocumentHandlers:
    """Document服务业务逻辑处理器"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化Document处理器"""
        self.config = config
        # 初始化各种处理器
        self.pdf_processor = PDFProcessor(config)
        # 任务管理器将在初始化时创建
        self.pdf_batch_manager = None
        self.convert_task_manager = None
    
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
        
        logger.info("Document handlers initialized with task managers")
    
    # ==================== PDF处理接口 ====================
    
    async def pdf_parser(self, request: PDFParserRequest, temp_file_path: str, file_info: FileInfo, trace_id: str = None) -> PDFParserResponse:
        """PDF解析处理,提取文本、图片、表格内容"""
        return await self.pdf_processor.process(request, temp_file_path, file_info, trace_id)
    
    async def pdf_parser_batch(self, request: PDFParserBatchRequest, trace_id: str = None) -> PDFParserBatchResponse:
        """PDF批量解析处理"""
        logger.info(f"PDF parser batch request - TraceID: {trace_id} | Files count: {len(request.files)}")
        
        if not self.pdf_batch_manager:
            raise RuntimeError("PDF batch task manager not initialized")
        
        try:
            # 提交批处理任务到任务管理器
            return await self.pdf_batch_manager.submit_pdf_batch_task(request, trace_id)
        except RuntimeError as e:
            # 捕获任务管理器的运行时错误，包括Worker不可用
            logger.error(f"PDF batch task submission failed - TraceID: {trace_id} | Error: {str(e)}")
            raise RuntimeError(f"批量处理服务暂时不可用，请稍后重试。如果问题持续存在，请联系系统管理员。详细错误：{str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in PDF batch processing - TraceID: {trace_id} | Error: {str(e)}")
            raise RuntimeError(f"处理请求时发生未知错误，请联系系统管理员。")
    
    async def query_pdf_parser_task(self, task_id: str, trace_id: str = None) -> PDFParserTaskStatusResponse:
        """查询PDF批量解析任务状态"""
        logger.info(f"Query PDF parser task - TraceID: {trace_id} | TaskID: {task_id}")
        
        if not self.pdf_batch_manager:
            raise RuntimeError("PDF batch task manager not initialized")
        
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
        logger.info(f"Document convert request - TraceID: {trace_id} | Source: {request.source_format} | Target: {request.target_format}")
        
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
            raise RuntimeError("Document convert task manager not initialized")
        
        return await self.convert_task_manager.submit_convert_task(request, temp_file_path, file_info, trace_id)
    
    async def query_convert_task(self, convert_task_id: str, trace_id: str = None) -> ConvertTaskStatusResponse:
        """查询格式转换任务状态"""
        logger.info(f"Query convert task - TraceID: {trace_id} | TaskID: {convert_task_id}")
        
        if not self.convert_task_manager:
            raise RuntimeError("Document convert task manager not initialized")
        
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
        logger.info(f"Text extract request - TraceID: {trace_id} | Filename: {request.filename} | TempFile: {temp_file_path}")
        
        # TODO: 实现文本提取逻辑
        # 1. 根据文件类型使用不同的文本提取方法
        # 2. 支持PDF、Word、Excel、PPT等格式的文本提取
        # 3. 根据extract_options配置提取参数
        # 4. 统计字数并返回文件元信息
        
        # 模拟提取的文本内容
        extracted_text = "这是从文档中提取的文本内容示例。包含了文档的主要内容，支持多种文件格式的文本提取功能。"
        
        # 返回模拟成功响应
        return TextExtractResponse(
            text_content=extracted_text,
            word_count=len(extracted_text),
            file_info={
                "filename": request.filename,
                "file_size": file_info.file_size,
                "file_type": file_info.content_type,
                "input_type": request.input_type,
                "extract_options": request.extract_options
            }
        )
    
    async def text_extract_batch(self, request: TextExtractBatchRequest, trace_id: str = None) -> TextExtractBatchResponse:
        """文本提取批处理处理"""
        logger.info(f"Text extract batch request - TraceID: {trace_id} | Files count: {len(request.files)}")
        
        # TODO: 实现文本提取批处理逻辑
        # 1. 创建批量任务ID
        # 2. 异步处理文件列表
        # 3. 对每个文件进行文本提取
        
        batch_task_id = f"text_extract_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
        
        # 返回模拟成功响应
        return TextExtractBatchResponse(
            text_extract_batch_task_id=batch_task_id,
            total_files=len(request.files),
            created_at=datetime.now().isoformat()
        )
    
    async def query_extract_task(self, batch_task_id: str, trace_id: str = None) -> ExtractTaskStatusResponse:
        """查询文本提取批处理任务状态"""
        logger.info(f"Query extract task - TraceID: {trace_id} | BatchTaskID: {batch_task_id}")
        
        # TODO: 实现文本提取批处理任务状态查询逻辑
        # 1. 根据batch_task_id查询任务状态
        # 2. 返回任务详细信息
        
        # 返回模拟成功响应
        return ExtractTaskStatusResponse(
            text_extract_batch_task_id=batch_task_id,
            status="completed",
            results=[]
        )
    
    # ==================== 表格提取接口 ====================
    
    async def table_extract(self, request: TableExtractRequest, temp_file_path: str, file_info: FileInfo, trace_id: str = None) -> TableExtractResponse:
        """表格提取处理"""
        logger.info(f"Table extract request - TraceID: {trace_id} | Filename: {request.filename} | TempFile: {temp_file_path}")
        
        # TODO: 实现表格提取逻辑
        # 可以考虑创建一个专门的TableProcessor来处理
        
        # 模拟提取的HTML表格内容
        mock_html_table = """
<table border="1" style="border-collapse: collapse;">
    <thead>
        <tr>
            <th>序号</th>
            <th>姓名</th>
            <th>年龄</th>
            <th>部门</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>1</td>
            <td>张三</td>
            <td>25</td>
            <td>技术部</td>
        </tr>
        <tr>
            <td>2</td>
            <td>李四</td>
            <td>28</td>
            <td>市场部</td>
        </tr>
    </tbody>
</table>"""
        
        # 返回HTML格式的表格内容
        return TableExtractResponse(
            html_content=mock_html_table,
            download_url=None
        )