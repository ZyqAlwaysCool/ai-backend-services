'''
Description: 文档服务API路由定义
Author: zyq
Date: 2025-09-18 15:43:43
LastEditors: zyq
LastEditTime: 2025-09-19 15:28:16
'''
import uuid
from typing import Union
from fastapi import APIRouter, Request, File, UploadFile, Form, Body
from fastapi.responses import FileResponse
import json
import base64
import os
from loguru import logger

from core.schemas.base_resp_model_define import BaseResponse
from core.config.error_codes import *
from core.exceptions.exceptions import BaseBusinessException, ValidationException
from .schemas import (
    PDFParserRequest, 
    PDFParserBatchRequest, 
    DocumentConvertRequest, 
    TextExtractRequest, 
    TextExtractBatchRequest, 
    TableExtractRequest, 
    DocumentTaskTypePrefix
)
from .processors.convert_processor import ConvertProcessor
from ..services_err_codes import *

document_router = APIRouter(tags=["文档服务"])


@document_router.post("/pdf-parser", response_model=BaseResponse, summary="PDF解析(同步接口)")
async def pdf_parser(http_request: Request):
    """PDF解析接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"PDF parser request started - TraceID: {trace_id}")
    
    # 从中间件获取处理后的数据
    temp_file_path = getattr(http_request.state, 'temp_file_path', None)
    file_info = getattr(http_request.state, 'file_info', None)
    processed_body = getattr(http_request.state, 'processed_request_body', None)
    
    if not temp_file_path or not file_info or not processed_body:
        raise BaseBusinessException(
            code=FILE_ERROR_PREPROCESS_FAILED,
            message=get_error_message(FILE_ERROR_PREPROCESS_FAILED)
        )
    
    # 构建请求对象
    request = PDFParserRequest(**processed_body)
    
    # 从service_registry获取document服务的handlers实例
    service_registry = getattr(http_request.app.state, 'service_registry', None)
    document_service = service_registry.get_service('document') if service_registry else None
    handlers = document_service.handlers if document_service else None
    
    if not handlers:
        raise BaseBusinessException(
            code=COMMON_ERROR_SERVICE_INIT_FAILED,
            message=get_error_message(COMMON_ERROR_SERVICE_INIT_FAILED)
        )
    
    # 调用业务逻辑，传入临时文件路径和文件信息
    response = await handlers.pdf_parser(request, temp_file_path, file_info, trace_id)
    
    logger.info(f"PDF parser request completed - TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.model_dump(),
        trace_id=trace_id
    )


@document_router.post("/pdf-parser-batch", response_model=BaseResponse, summary="PDF批量解析(异步接口)")
async def pdf_parser_batch(http_request: Request):
    """PDF批量解析接口(异步响应)"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"PDF parser batch request started - TraceID: {trace_id}")
    
    # 从中间件获取处理后的数据
    processed_body = getattr(http_request.state, 'processed_request_body', None)
    
    if not processed_body:
        raise BaseBusinessException(
            code=FILE_ERROR_PREPROCESS_FAILED,
            message=get_error_message(FILE_ERROR_PREPROCESS_FAILED)
        )
    
    # 保存原始files数据（包含temp_file_path信息）
    original_files = processed_body.get('files', [])
    
    # 构建请求对象
    request = PDFParserBatchRequest(**processed_body)
    
    # 从service_registry获取document服务的handlers实例
    service_registry = getattr(http_request.app.state, 'service_registry', None)
    document_service = service_registry.get_service('document') if service_registry else None
    handlers = document_service.handlers if document_service else None
    
    if not handlers:
        raise BaseBusinessException(
            code=DOCUMENT_SERVICE_INIT_ERROR,
            message=get_service_error_message(DOCUMENT_SERVICE_INIT_ERROR)
        )
    
    # 调用业务逻辑，传递原始files数据
    response = await handlers.pdf_parser_batch(request, trace_id, original_files)
    
    logger.info(f"PDF parser batch request completed - TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.model_dump(),
        trace_id=trace_id
    )


@document_router.post("/convert", response_model=BaseResponse, summary="文档格式转换")
async def document_convert(http_request: Request):
    """文档格式转换接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Document convert request started - TraceID: {trace_id}")
    
    # 从中间件获取处理后的数据
    temp_file_path = getattr(http_request.state, 'temp_file_path', None)
    file_info = getattr(http_request.state, 'file_info', None)
    processed_body = getattr(http_request.state, 'processed_request_body', None)
    
    if not temp_file_path or not file_info or not processed_body:
        raise BaseBusinessException(
            code=FILE_ERROR_PREPROCESS_FAILED,
            message=get_service_error_message(FILE_ERROR_PREPROCESS_FAILED)
        )
    
    # 构建请求对象
    request = DocumentConvertRequest(**processed_body)
    
    # 从service_registry获取document服务的handlers实例
    service_registry = getattr(http_request.app.state, 'service_registry', None)
    document_service = service_registry.get_service('document') if service_registry else None
    handlers = document_service.handlers if document_service else None
    
    if not handlers:
        raise BaseBusinessException(
            code=DOCUMENT_SERVICE_INIT_ERROR,
            message=get_service_error_message(DOCUMENT_SERVICE_INIT_ERROR)
        )
    
    # 调用业务逻辑，传入临时文件路径和文件信息
    response = await handlers.document_convert(request, temp_file_path, file_info, trace_id)
    
    logger.info(f"Document convert request completed - TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.model_dump(),
        trace_id=trace_id
    )


@document_router.get("/query-convert-task/{convert_task_id}", response_model=BaseResponse, summary="查询格式转换任务状态")
async def query_convert_task(convert_task_id: str, http_request: Request):
    """查询格式转换任务状态接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Query convert task started - TraceID: {trace_id}")
    
    # 从service_registry获取document服务的handlers实例
    service_registry = getattr(http_request.app.state, 'service_registry', None)
    document_service = service_registry.get_service('document') if service_registry else None
    handlers = document_service.handlers if document_service else None
    
    if not handlers:
        raise BaseBusinessException(
            code=DOCUMENT_SERVICE_INIT_ERROR,
            message=get_service_error_message(DOCUMENT_SERVICE_INIT_ERROR)
        )
    
    if not convert_task_id.startswith(DocumentTaskTypePrefix.DOCUMENT_CONVERT_TASK.value):
        raise ValidationException(get_service_error_message(DOCUMENT_SERVICE_INVALID_TASK_TYPE_ERROR))
    
    # 调用业务逻辑
    response = await handlers.query_convert_task(convert_task_id, trace_id)
    
    logger.info(f"Query convert task completed - TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.model_dump(),
        trace_id=trace_id
    )


@document_router.post("/text-extract", response_model=BaseResponse, summary="文本提取")
async def text_extract(http_request: Request):
    """文本提取接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Text extract started - TraceID: {trace_id}")
    
    # 从中间件获取处理后的数据
    temp_file_path = getattr(http_request.state, 'temp_file_path', None)
    file_info = getattr(http_request.state, 'file_info', None)
    processed_body = getattr(http_request.state, 'processed_request_body', None)
    
    if not temp_file_path or not file_info or not processed_body:
        raise BaseBusinessException(
            code=FILE_ERROR_PREPROCESS_FAILED,
            message=get_error_message(FILE_ERROR_PREPROCESS_FAILED)
        )
    
    # 构建请求对象
    request = TextExtractRequest(**processed_body)
    
    # 从service_registry获取document服务的handlers实例
    service_registry = getattr(http_request.app.state, 'service_registry', None)
    document_service = service_registry.get_service('document') if service_registry else None
    handlers = document_service.handlers if document_service else None
    
    if not handlers:
        raise BaseBusinessException(
            code=DOCUMENT_SERVICE_INIT_ERROR,
            message=get_service_error_message(DOCUMENT_SERVICE_INIT_ERROR)
        )
    
    # 调用业务逻辑，传入临时文件路径和文件信息
    response = await handlers.text_extract(request, temp_file_path, file_info, trace_id)
    
    logger.info(f"Text extract completed - TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.model_dump(),
        trace_id=trace_id
    )


@document_router.post("/text-extract-batch", response_model=BaseResponse, summary="文本提取批处理(异步接口)")
async def text_extract_batch(http_request: Request):
    """文本提取批处理接口（异步响应）"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Text extract batch started - TraceID: {trace_id}")
    
    # 从中间件获取处理后的数据
    processed_body = getattr(http_request.state, 'processed_request_body', None)
    
    if not processed_body:
        raise BaseBusinessException(
            code=FILE_ERROR_PREPROCESS_FAILED,
            message=get_error_message(FILE_ERROR_PREPROCESS_FAILED)
        )
    
    # 保存原始files数据（包含temp_file_path信息）
    original_files = processed_body.get('files', [])
    
    # 构建请求对象
    request = TextExtractBatchRequest(**processed_body)
    
    # 从service_registry获取document服务的handlers实例
    service_registry = getattr(http_request.app.state, 'service_registry', None)
    document_service = service_registry.get_service('document') if service_registry else None
    handlers = document_service.handlers if document_service else None
    
    if not handlers:
        raise BaseBusinessException(
            code=DOCUMENT_SERVICE_INIT_ERROR,
            message=get_service_error_message(DOCUMENT_SERVICE_INIT_ERROR)
        )
    
    # 调用业务逻辑，传递原始files数据
    response = await handlers.text_extract_batch(request, trace_id, original_files)
    
    logger.info(f"Text extract batch completed - TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.model_dump(),
        trace_id=trace_id
    )


@document_router.get("/query-extract-task/{batch_task_id}", response_model=BaseResponse, summary="查询文本提取批处理任务状态")
async def query_extract_task(batch_task_id: str, http_request: Request):
    """查询文本提取批处理任务状态接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Query extract task started - TraceID: {trace_id}")
    
    # 从service_registry获取document服务的handlers实例
    service_registry = getattr(http_request.app.state, 'service_registry', None)
    document_service = service_registry.get_service('document') if service_registry else None
    handlers = document_service.handlers if document_service else None
    
    if not handlers:
        raise BaseBusinessException(
            code=DOCUMENT_SERVICE_INIT_ERROR,
            message=get_service_error_message(DOCUMENT_SERVICE_INIT_ERROR)
        )
    
    if not batch_task_id.startswith(DocumentTaskTypePrefix.TEXT_EXTRACT_BATCH_TASK):
        raise ValidationException(get_service_error_message(DOCUMENT_SERVICE_INVALID_TASK_TYPE_ERROR))
    
    # 调用业务逻辑
    response = await handlers.query_extract_task(batch_task_id, trace_id)
    
    logger.info(f"Query extract task completed - TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.model_dump(),
        trace_id=trace_id
    )


@document_router.get("/query-pdf-parser-task/{pdf_parser_batch_task_id}", response_model=BaseResponse, summary="查询PDF批量解析任务状态")
async def query_pdf_parser_task(pdf_parser_batch_task_id: str, http_request: Request):
    """查询PDF批量解析任务状态接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Query PDF parser task started - TraceID: {trace_id}")
    
    # 从service_registry获取document服务的handlers实例
    service_registry = getattr(http_request.app.state, 'service_registry', None)
    document_service = service_registry.get_service('document') if service_registry else None
    handlers = document_service.handlers if document_service else None
    
    if not handlers:
        raise BaseBusinessException(
            code=DOCUMENT_SERVICE_INIT_ERROR,
            message=get_service_error_message(DOCUMENT_SERVICE_INIT_ERROR)
        )
    
    if not pdf_parser_batch_task_id.startswith(DocumentTaskTypePrefix.PDF_BATCH_PARSE_TASK.value):
        raise ValidationException(get_service_error_message(DOCUMENT_SERVICE_INVALID_TASK_TYPE_ERROR))
    
    # 调用业务逻辑
    response = await handlers.query_pdf_parser_task(pdf_parser_batch_task_id, trace_id)
    
    logger.info(f"Query PDF parser task completed - TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.model_dump(),
        trace_id=trace_id
    )


@document_router.post("/table-extract", response_model=BaseResponse, summary="表格提取")
async def table_extract(http_request: Request):
    """表格提取接口（同步接口）"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Table extract started - TraceID: {trace_id}")
    
    # 从中间件获取处理后的数据
    temp_file_path = getattr(http_request.state, 'temp_file_path', None)
    file_info = getattr(http_request.state, 'file_info', None)
    processed_body = getattr(http_request.state, 'processed_request_body', None)
    
    if not temp_file_path or not file_info or not processed_body:
        raise BaseBusinessException(
            code=FILE_ERROR_PREPROCESS_FAILED,
            message=get_error_message(FILE_ERROR_PREPROCESS_FAILED)
        )
    
    # 构建请求对象
    request = TableExtractRequest(**processed_body)
    
    # 从service_registry获取document服务的handlers实例
    service_registry = getattr(http_request.app.state, 'service_registry', None)
    document_service = service_registry.get_service('document') if service_registry else None
    handlers = document_service.handlers if document_service else None
    
    if not handlers:
        raise BaseBusinessException(
            code=DOCUMENT_SERVICE_INIT_ERROR,
            message=get_service_error_message(DOCUMENT_SERVICE_INIT_ERROR)
        )
    
    # 调用业务逻辑，传入临时文件路径和文件信息
    response = await handlers.table_extract(request, temp_file_path, file_info, trace_id)
    
    logger.info(f"Table extract completed - TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.model_dump(),
        trace_id=trace_id
    )


@document_router.get("/pdf-parser-download", summary="PDF解析结果文件下载")
async def pdf_parser_download(task_id: str, http_request: Request):
    """PDF解析结果文件下载接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"PDF parser download started - TraceID: {trace_id}")
    
    # 从service_registry获取document服务的handlers实例
    service_registry = getattr(http_request.app.state, 'service_registry', None)
    document_service = service_registry.get_service('document') if service_registry else None
    handlers = document_service.handlers if document_service else None
    
    if not handlers:
        raise BaseBusinessException(
            code=DOCUMENT_SERVICE_INIT_ERROR,
            message=get_service_error_message(DOCUMENT_SERVICE_INIT_ERROR)
        )
    
    if not task_id.startswith(DocumentTaskTypePrefix.PDF_PARSE_TASK):
        raise ValidationException(get_service_error_message(DOCUMENT_SERVICE_INVALID_TASK_TYPE_ERROR))
    
    # 获取文件管理器
    file_manager = handlers.pdf_processor.file_manager
    
    # 获取文件信息和路径
    file_info = file_manager.get_file_info(task_id)
    if not file_info:
        raise BaseBusinessException(
            code=FILE_ERROR_NOT_EXIST,
            message=get_service_error_message(FILE_ERROR_NOT_EXIST)
        )
    
    file_path = file_manager.get_file_path(task_id)
    if not file_path or not os.path.exists(file_path):
        raise BaseBusinessException(
            code=FILE_ERROR_NOT_EXIST,
            message=get_service_error_message(FILE_ERROR_NOT_EXIST)
        )
    
    logger.info(f"PDF parser download completed - TraceID: {trace_id}")
    # 返回文件响应
    return FileResponse(
        path=file_path,
        filename=file_info['filename'],
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )


@document_router.get("/convert-download", summary="文档转换结果文件下载")
async def convert_download(task_id: str, http_request: Request):
    """文档转换结果文件下载接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Convert download started - TraceID: {trace_id}")
    
    # 从service_registry获取document服务的handlers实例
    service_registry = getattr(http_request.app.state, 'service_registry', None)
    document_service = service_registry.get_service('document') if service_registry else None
    handlers = document_service.handlers if document_service else None
    
    if not handlers:
        raise BaseBusinessException(
            code=DOCUMENT_SERVICE_INIT_ERROR,
            message=get_service_error_message(DOCUMENT_SERVICE_INIT_ERROR)
        )
    
    if not task_id.startswith(DocumentTaskTypePrefix.CONVERT_TASK):
        raise ValidationException(get_service_error_message(DOCUMENT_SERVICE_INVALID_TASK_TYPE_ERROR))
    
    # 获取文件管理器（从convert_processor中获取）
    if not handlers.convert_task_manager:
        raise BaseBusinessException(
            code=DOCUMENT_SERVICE_CONVERT_TASK_MANAGER_INIT_ERROR,
            message=get_service_error_message(DOCUMENT_SERVICE_CONVERT_TASK_MANAGER_INIT_ERROR)
        )

    convert_processor = ConvertProcessor(handlers.config)
    file_manager = convert_processor.file_manager
    
    # 获取文件信息和路径
    file_info = file_manager.get_file_info(task_id)
    if not file_info:
        raise BaseBusinessException(
            code=FILE_ERROR_NOT_EXIST,
            message=get_service_error_message(FILE_ERROR_NOT_EXIST)
        )
    
    file_path = file_manager.get_file_path(task_id)
    if not file_path or not os.path.exists(file_path):
        raise BaseBusinessException(
            code=FILE_ERROR_NOT_EXIST,
            message=get_service_error_message(FILE_ERROR_NOT_EXIST)
        )
    
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
    
    logger.info(f"Convert download completed - TraceID: {trace_id}")
    # 返回文件响应
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=media_type
    )


@document_router.get("/extract-download", summary="表格提取结果文件下载")
async def extract_download(task_id: str, http_request: Request):
    """表格提取结果文件下载接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Extract download started - TraceID: {trace_id}")
    
    # 从service_registry获取document服务的handlers实例
    service_registry = getattr(http_request.app.state, 'service_registry', None)
    document_service = service_registry.get_service('document') if service_registry else None
    handlers = document_service.handlers if document_service else None
    
    if not handlers:
        raise BaseBusinessException(
            code=DOCUMENT_SERVICE_INIT_ERROR,
            message=get_service_error_message(DOCUMENT_SERVICE_INIT_ERROR)
        )
    
    if not task_id.startswith(DocumentTaskTypePrefix.TABLE_EXTRACT_TASK.value):
        raise ValidationException(get_service_error_message(DOCUMENT_SERVICE_INVALID_TASK_TYPE_ERROR))
    
    # 获取文件管理器（从table_processor中获取）
    file_manager = handlers.table_processor.file_manager
    
    # 获取文件信息和路径
    file_info = file_manager.get_file_info(task_id)
    if not file_info:
        raise BaseBusinessException(
            code=FILE_ERROR_NOT_EXIST,
            message=get_service_error_message(FILE_ERROR_NOT_EXIST)
        )
    
    file_path = file_manager.get_file_path(task_id)
    if not file_path or not os.path.exists(file_path):
        raise BaseBusinessException(
            code=FILE_ERROR_NOT_EXIST,
            message=get_service_error_message(FILE_ERROR_NOT_EXIST)
        )
    
    logger.info(f"Extract download completed - TraceID: {trace_id}")
    # 返回HTML文件响应
    return FileResponse(
        path=file_path,
        filename=file_info['filename'],
        media_type='text/html'
    )