import uuid
from typing import Union
from fastapi import APIRouter, Request, File, UploadFile, Form, Body
from fastapi.responses import FileResponse
import json
import base64
import os
from loguru import logger

from core.schemas.base_resp_model_define import BaseResponse
from core.config.error_codes import COMMON_ERROR_REQUEST_PARSE_ERROR
from .schemas import PDFParserRequest, PDFParserBatchRequest, DocumentConvertRequest, TextExtractRequest, TextExtractBatchRequest, TableExtractRequest, DocumentTaskTypePrefix

document_router = APIRouter(tags=["文档服务"])


@document_router.post("/pdf-parser", response_model=BaseResponse, summary="PDF解析(同步接口)")
async def pdf_parser(http_request: Request):
    """PDF解析接口"""
    trace_id = str(uuid.uuid4())
    logger.info(f"Received PDF parser request - TraceID: {trace_id}")
    
    try:
        # 从中间件获取处理后的数据
        temp_file_path = getattr(http_request.state, 'temp_file_path', None)
        file_info = getattr(http_request.state, 'file_info', None)
        processed_body = getattr(http_request.state, 'processed_request_body', None)
        
        if not temp_file_path or not file_info or not processed_body:
            return BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg="文件处理失败，请检查请求格式",
                trace_id=trace_id
            )
        
        # 构建请求对象
        request = PDFParserRequest(**processed_body)
        
        # 从service_registry获取document服务的handlers实例
        service_registry = getattr(http_request.app.state, 'service_registry', None)
        document_service = service_registry.get_service('document') if service_registry else None
        handlers = document_service.handlers if document_service else None
        
        if not handlers:
            return BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg="Document服务未初始化",
                trace_id=trace_id
            )
        
        # 调用业务逻辑，传入临时文件路径和文件信息
        response = await handlers.pdf_parser(request, temp_file_path, file_info, trace_id)
        
        return BaseResponse.success(
            data=response.model_dump(),
            trace_id=trace_id
        )
        
    except ValueError as ve:
        logger.error(f"Invalid request parameter - TraceID: {trace_id} | Error: {str(ve)}")
        return BaseResponse.error(
            code=400,
            msg=str(ve),
            trace_id=trace_id
        )
    except Exception as e:
        logger.error(f"PDF parser error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="PDF解析服务异常",
            trace_id=trace_id
        )


@document_router.post("/pdf-parser-batch", response_model=BaseResponse, summary="PDF批量解析(异步接口)")
async def pdf_parser_batch(request: PDFParserBatchRequest, http_request: Request):
    """PDF批量解析接口（异步响应）"""
    trace_id = str(uuid.uuid4())
    logger.info(f"Received PDF parser batch request - TraceID: {trace_id}")
    
    try:
        # 从service_registry获取document服务的handlers实例
        service_registry = getattr(http_request.app.state, 'service_registry', None)
        document_service = service_registry.get_service('document') if service_registry else None
        handlers = document_service.handlers if document_service else None
        
        if not handlers:
            return BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg="Document服务未初始化",
                trace_id=trace_id
            )
        
        # 调用业务逻辑
        response = await handlers.pdf_parser_batch(request, trace_id)
        
        return BaseResponse.success(
            data=response.model_dump(),
            trace_id=trace_id
        )
        
    except Exception as e:
        logger.error(f"PDF parser batch error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="PDF批量解析服务异常",
            trace_id=trace_id
        )


@document_router.post("/convert", response_model=BaseResponse, summary="文档格式转换")
async def document_convert(http_request: Request):
    """文档格式转换接口"""
    trace_id = str(uuid.uuid4())
    logger.info(f"Received document convert request - TraceID: {trace_id}")
    
    try:
        # 从中间件获取处理后的数据
        temp_file_path = getattr(http_request.state, 'temp_file_path', None)
        file_info = getattr(http_request.state, 'file_info', None)
        processed_body = getattr(http_request.state, 'processed_request_body', None)
        
        if not temp_file_path or not file_info or not processed_body:
            return BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg="文件处理失败，请检查请求格式",
                trace_id=trace_id
            )
        
        # 构建请求对象
        request = DocumentConvertRequest(**processed_body)
        
        # 从service_registry获取document服务的handlers实例
        service_registry = getattr(http_request.app.state, 'service_registry', None)
        document_service = service_registry.get_service('document') if service_registry else None
        handlers = document_service.handlers if document_service else None
        
        if not handlers:
            return BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg="Document服务未初始化",
                trace_id=trace_id
            )
        
        # 调用业务逻辑，传入临时文件路径和文件信息
        response = await handlers.document_convert(request, temp_file_path, file_info, trace_id)
        
        return BaseResponse.success(
            data=response.model_dump(),
            trace_id=trace_id
        )
        
    except Exception as e:
        logger.error(f"Document convert error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="文档格式转换服务异常",
            trace_id=trace_id
        )


@document_router.get("/query-convert-task/{convert_task_id}", response_model=BaseResponse, summary="查询格式转换任务状态")
async def query_convert_task(convert_task_id: str, http_request: Request):
    """查询格式转换任务状态接口"""
    trace_id = str(uuid.uuid4())
    logger.info(f"Received query convert task request - TraceID: {trace_id} | TaskID: {convert_task_id}")
    
    try:
        # 从service_registry获取document服务的handlers实例
        service_registry = getattr(http_request.app.state, 'service_registry', None)
        document_service = service_registry.get_service('document') if service_registry else None
        handlers = document_service.handlers if document_service else None
        
        if not handlers:
            return BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg="Document服务未初始化",
                trace_id=trace_id
            )
        
        # 调用业务逻辑
        response = await handlers.query_convert_task(convert_task_id, trace_id)
        
        return BaseResponse.success(
            data=response.model_dump(),
            trace_id=trace_id
        )
        
    except Exception as e:
        logger.error(f"Query convert task error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="查询格式转换任务状态服务异常",
            trace_id=trace_id
        )


@document_router.post("/text-extract", response_model=BaseResponse, summary="文本提取")
async def text_extract(http_request: Request):
    """文本提取接口"""
    trace_id = str(uuid.uuid4())
    logger.info(f"Received text extract request - TraceID: {trace_id}")
    
    try:
        # 从中间件获取处理后的数据
        temp_file_path = getattr(http_request.state, 'temp_file_path', None)
        file_info = getattr(http_request.state, 'file_info', None)
        processed_body = getattr(http_request.state, 'processed_request_body', None)
        
        if not temp_file_path or not file_info or not processed_body:
            return BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg="文件处理失败，请检查请求格式",
                trace_id=trace_id
            )
        
        # 构建请求对象
        request = TextExtractRequest(**processed_body)
        
        # 从service_registry获取document服务的handlers实例
        service_registry = getattr(http_request.app.state, 'service_registry', None)
        document_service = service_registry.get_service('document') if service_registry else None
        handlers = document_service.handlers if document_service else None
        
        if not handlers:
            return BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg="Document服务未初始化",
                trace_id=trace_id
            )
        
        # 调用业务逻辑，传入临时文件路径和文件信息
        response = await handlers.text_extract(request, temp_file_path, file_info, trace_id)
        
        return BaseResponse.success(
            data=response.model_dump(),
            trace_id=trace_id
        )
        
    except Exception as e:
        logger.error(f"Text extract error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="文本提取服务异常",
            trace_id=trace_id
        )


@document_router.post("/text-extract-batch", response_model=BaseResponse, summary="文本提取批处理(异步接口)")
async def text_extract_batch(request: TextExtractBatchRequest, http_request: Request):
    """文本提取批处理接口（异步响应）"""
    trace_id = str(uuid.uuid4())
    logger.info(f"Received text extract batch request - TraceID: {trace_id}")
    
    try:
        # 从service_registry获取document服务的handlers实例
        service_registry = getattr(http_request.app.state, 'service_registry', None)
        document_service = service_registry.get_service('document') if service_registry else None
        handlers = document_service.handlers if document_service else None
        
        if not handlers:
            return BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg="Document服务未初始化",
                trace_id=trace_id
            )
        
        # 调用业务逻辑
        response = await handlers.text_extract_batch(request, trace_id)
        
        return BaseResponse.success(
            data=response.model_dump(),
            trace_id=trace_id
        )
        
    except Exception as e:
        logger.error(f"Text extract batch error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="文本提取批处理服务异常",
            trace_id=trace_id
        )


@document_router.get("/query-extract-task/{batch_task_id}", response_model=BaseResponse, summary="查询文本提取批处理任务状态")
async def query_extract_task(batch_task_id: str, http_request: Request):
    """查询文本提取批处理任务状态接口"""
    trace_id = str(uuid.uuid4())
    logger.info(f"Received query extract task request - TraceID: {trace_id} | BatchTaskID: {batch_task_id}")
    
    try:
        # 从service_registry获取document服务的handlers实例
        service_registry = getattr(http_request.app.state, 'service_registry', None)
        document_service = service_registry.get_service('document') if service_registry else None
        handlers = document_service.handlers if document_service else None
        
        if not handlers:
            return BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg="Document服务未初始化",
                trace_id=trace_id
            )
        
        # 调用业务逻辑
        response = await handlers.query_extract_task(batch_task_id, trace_id)
        
        return BaseResponse.success(
            data=response.model_dump(),
            trace_id=trace_id
        )
        
    except Exception as e:
        logger.error(f"Query extract task error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="查询文本提取批处理任务状态服务异常",
            trace_id=trace_id
        )


@document_router.get("/query-pdf-parser-task/{pdf_parser_batch_task_id}", response_model=BaseResponse, summary="查询PDF批量解析任务状态")
async def query_pdf_parser_task(pdf_parser_batch_task_id: str, http_request: Request):
    """查询PDF批量解析任务状态接口"""
    trace_id = str(uuid.uuid4())
    logger.info(f"Received query PDF parser task request - TraceID: {trace_id} | TaskID: {pdf_parser_batch_task_id}")
    
    try:
        # 从service_registry获取document服务的handlers实例
        service_registry = getattr(http_request.app.state, 'service_registry', None)
        document_service = service_registry.get_service('document') if service_registry else None
        handlers = document_service.handlers if document_service else None
        
        if not handlers:
            return BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg="Document服务未初始化",
                trace_id=trace_id
            )
        
        if not pdf_parser_batch_task_id.startswith(DocumentTaskTypePrefix.PDF_BATCH_PARSE_TASK):
            return BaseResponse.error(
                code=400,
                msg=f"无效的PDF批量解析任务ID, 前缀应为: {DocumentTaskTypePrefix.PDF_BATCH_PARSE_TASK.value}",
                trace_id=trace_id
            )
        
        # 调用业务逻辑
        response = await handlers.query_pdf_parser_task(pdf_parser_batch_task_id, trace_id)
        
        return BaseResponse.success(
            data=response.model_dump(),
            trace_id=trace_id
        )
        
    except Exception as e:
        logger.error(f"Query PDF parser task error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="查询PDF批量解析任务状态服务异常",
            trace_id=trace_id
        )


@document_router.post("/table-extract", response_model=BaseResponse, summary="表格提取")
async def table_extract(http_request: Request):
    """表格提取接口（同步接口）"""
    trace_id = str(uuid.uuid4())
    logger.info(f"Received table extract request - TraceID: {trace_id}")
    
    try:
        # 从中间件获取处理后的数据
        temp_file_path = getattr(http_request.state, 'temp_file_path', None)
        file_info = getattr(http_request.state, 'file_info', None)
        processed_body = getattr(http_request.state, 'processed_request_body', None)
        
        if not temp_file_path or not file_info or not processed_body:
            return BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg="文件处理失败，请检查请求格式",
                trace_id=trace_id
            )
        
        # 构建请求对象
        request = TableExtractRequest(**processed_body)
        
        # 从service_registry获取document服务的handlers实例
        service_registry = getattr(http_request.app.state, 'service_registry', None)
        document_service = service_registry.get_service('document') if service_registry else None
        handlers = document_service.handlers if document_service else None
        
        if not handlers:
            return BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg="Document服务未初始化",
                trace_id=trace_id
            )
        
        # 调用业务逻辑，传入临时文件路径和文件信息
        response = await handlers.table_extract(request, temp_file_path, file_info, trace_id)
        
        return BaseResponse.success(
            data=response.model_dump(),
            trace_id=trace_id
        )
        
    except Exception as e:
        logger.error(f"Table extract error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="表格提取服务异常",
            trace_id=trace_id
        )


@document_router.get("/pdf-parser-download", summary="PDF解析结果文件下载")
async def pdf_parser_download(task_id: str, http_request: Request):
    """PDF解析结果文件下载接口"""
    trace_id = str(uuid.uuid4())
    logger.info(f"Received file download request - TraceID: {trace_id} | TaskID: {task_id}")
    
    try:
        # 从service_registry获取document服务的handlers实例
        service_registry = getattr(http_request.app.state, 'service_registry', None)
        document_service = service_registry.get_service('document') if service_registry else None
        handlers = document_service.handlers if document_service else None
        
        if not handlers:
            return BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg="Document服务未初始化",
                trace_id=trace_id
            )
        
        if not task_id.startswith(DocumentTaskTypePrefix.PDF_PARSE_TASK):
            return BaseResponse.error(
                code=400,
                msg=f"无效的PDF解析任务ID, 前缀应为: {DocumentTaskTypePrefix.PDF_PARSE_TASK.value}",
                trace_id=trace_id
            )
        
        # 获取文件管理器
        file_manager = handlers.pdf_processor.file_manager
        
        # 获取文件信息和路径
        file_info = file_manager.get_file_info(task_id)
        if not file_info:
            return BaseResponse.error(
                code=404,
                msg="文件不存在或已过期，请重新生成文档",
                trace_id=trace_id
            )
        
        file_path = file_manager.get_file_path(task_id)
        if not file_path or not os.path.exists(file_path):
            return BaseResponse.error(
                code=404,
                msg="文件不存在或已被删除，请重新生成文档",
                trace_id=trace_id
            )
        
        logger.info(f"File download initiated - TraceID: {trace_id} | File: {file_info['filename']}")
        
        # 返回文件响应
        return FileResponse(
            path=file_path,
            filename=file_info['filename'],
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        
    except Exception as e:
        logger.error(f"File download error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="文件下载服务异常",
            trace_id=trace_id
        )


@document_router.get("/convert-download", summary="文档转换结果文件下载")
async def convert_download(task_id: str, http_request: Request):
    """文档转换结果文件下载接口"""
    trace_id = str(uuid.uuid4())
    logger.info(f"Received convert file download request - TraceID: {trace_id} | TaskID: {task_id}")
    
    try:
        # 从service_registry获取document服务的handlers实例
        service_registry = getattr(http_request.app.state, 'service_registry', None)
        document_service = service_registry.get_service('document') if service_registry else None
        handlers = document_service.handlers if document_service else None
        
        if not handlers:
            return BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg="Document服务未初始化",
                trace_id=trace_id
            )
        
        if not task_id.startswith(DocumentTaskTypePrefix.CONVERT_TASK):
            return BaseResponse.error(
                code=400,
                msg=f"无效的转换任务ID, 前缀应为: {DocumentTaskTypePrefix.CONVERT_TASK.value}",
                trace_id=trace_id
            )
        
        # 获取文件管理器（从convert_processor中获取）
        if not handlers.convert_task_manager:
            return BaseResponse.error(
                code=500,
                msg="转换任务管理器未初始化",
                trace_id=trace_id
            )
        
        # 创建临时的ConvertProcessor来访问file_manager
        from .processors.convert_processor import ConvertProcessor
        convert_processor = ConvertProcessor(handlers.config)
        file_manager = convert_processor.file_manager
        
        # 获取文件信息和路径
        file_info = file_manager.get_file_info(task_id)
        if not file_info:
            return BaseResponse.error(
                code=404,
                msg="文件不存在或已过期，请重新转换文档",
                trace_id=trace_id
            )
        
        file_path = file_manager.get_file_path(task_id)
        if not file_path or not os.path.exists(file_path):
            return BaseResponse.error(
                code=404,
                msg="文件不存在或已被删除，请重新转换文档",
                trace_id=trace_id
            )
        
        logger.info(f"Convert file download initiated - TraceID: {trace_id} | File: {file_info['filename']}")
        
        # 根据文件扩展名确定media_type
        filename = file_info['filename']
        if filename.endswith('.pdf'):
            media_type = 'application/pdf'
        elif filename.endswith('.docx'):
            media_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif filename.endswith('.md'):
            media_type = 'text/markdown'
        else:
            media_type = 'application/octet-stream'
        
        # 返回文件响应
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type=media_type
        )
        
    except Exception as e:
        logger.error(f"Convert file download error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="转换文件下载服务异常",
            trace_id=trace_id
        )