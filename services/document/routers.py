import uuid
from typing import Union
from fastapi import APIRouter, Request, File, UploadFile, Form, Body
from loguru import logger

from core.schemas.base_resp_model_define import BaseResponse
from core.config.error_codes import COMMON_ERROR_REQUEST_PARSE_ERROR
from .schemas import PDFParserRequest, PDFParserBatchRequest, DocumentConvertRequest, TextExtractRequest, TextExtractBatchRequest, TableExtractRequest

document_router = APIRouter(tags=["文档服务"])


@document_router.post("/pdf-parser", response_model=BaseResponse)
async def pdf_parser(http_request: Request):
    """PDF解析接口（非流式响应）"""
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
            data=response.dict(),
            trace_id=trace_id
        )
        
    except Exception as e:
        logger.error(f"PDF parser error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="PDF解析服务异常",
            trace_id=trace_id
        )


@document_router.post("/pdf-parser-batch", response_model=BaseResponse)
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
            data=response.dict(),
            trace_id=trace_id
        )
        
    except Exception as e:
        logger.error(f"PDF parser batch error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="PDF批量解析服务异常",
            trace_id=trace_id
        )


@document_router.post("/convert", response_model=BaseResponse)
async def document_convert(http_request: Request):
    """文档格式转换接口（非流式响应）"""
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
            data=response.dict(),
            trace_id=trace_id
        )
        
    except Exception as e:
        logger.error(f"Document convert error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="文档格式转换服务异常",
            trace_id=trace_id
        )


@document_router.get("/query-convert-task/{convert_task_id}", response_model=BaseResponse)
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
            data=response.dict(),
            trace_id=trace_id
        )
        
    except Exception as e:
        logger.error(f"Query convert task error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="查询格式转换任务状态服务异常",
            trace_id=trace_id
        )


@document_router.post("/text-extract", response_model=BaseResponse)
async def text_extract(http_request: Request):
    """文本提取接口（非流式响应）"""
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
            data=response.dict(),
            trace_id=trace_id
        )
        
    except Exception as e:
        logger.error(f"Text extract error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="文本提取服务异常",
            trace_id=trace_id
        )


@document_router.post("/text-extract-batch", response_model=BaseResponse)
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
            data=response.dict(),
            trace_id=trace_id
        )
        
    except Exception as e:
        logger.error(f"Text extract batch error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="文本提取批处理服务异常",
            trace_id=trace_id
        )


@document_router.get("/query-extract-task/{batch_task_id}", response_model=BaseResponse)
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
            data=response.dict(),
            trace_id=trace_id
        )
        
    except Exception as e:
        logger.error(f"Query extract task error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="查询文本提取批处理任务状态服务异常",
            trace_id=trace_id
        )


@document_router.get("/query-pdf-parser-task/{pdf_parser_batch_task_id}", response_model=BaseResponse)
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
        
        # 调用业务逻辑
        response = await handlers.query_pdf_parser_task(pdf_parser_batch_task_id, trace_id)
        
        return BaseResponse.success(
            data=response.dict(),
            trace_id=trace_id
        )
        
    except Exception as e:
        logger.error(f"Query PDF parser task error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="查询PDF批量解析任务状态服务异常",
            trace_id=trace_id
        )


@document_router.post("/table-extract", response_model=BaseResponse)
async def table_extract(http_request: Request):
    """表格提取接口（非流式响应）"""
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
            data=response.dict(),
            trace_id=trace_id
        )
        
    except Exception as e:
        logger.error(f"Table extract error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=500,
            msg="表格提取服务异常",
            trace_id=trace_id
        )