'''
Description: Retrieval服务HTTP路由
Author: zyq
Date: 2025-09-18 15:50:47
LastEditors: zyq
LastEditTime: 2025-09-19 17:17:32
'''

import uuid
from typing import List, Optional
from fastapi import APIRouter, Request, UploadFile, File, Form
from loguru import logger

from core.schemas.base_resp_model_define import BaseResponse
from core.exceptions import ValidationException, BaseBusinessException
from ..services_err_codes import (
    RETRIEVAL_SERVICE_INIT_ERROR, 
    RETRIEVAL_SERVICE_TASK_NOT_FOUND_ERROR,
    get_service_error_message
)
from .schemas import (RetrievalUploadRequest, RetrievalUploadResponse, 
                      KnowledgeBaseBuildRequest, KnowledgeBaseBuildResponse, BuildTaskStatusResponse,
                      RetrievalQueryRequest, KnowledgeBaseQueryResponse
)

# 创建retrieval服务路由
retrieval_router = APIRouter(tags=["向量检索服务"])


@retrieval_router.post("/upload-files", response_model=BaseResponse, summary=["上传docx格式文档至知识库"])
async def upload_documents(
    request: Request,
    knowledge_base_name: str = Form(..., description="知识库名称"),
    files: List[UploadFile] = File(..., description="DOCX文档文件列表"),
    upload_options: Optional[str] = Form(None, description="上传选项配置(JSON字符串)")
):
    """
    上传DOCX文档到指定知识库
    
    - **knowledge_base_name**: 知识库名称
    - **files**: DOCX格式文档列表
    - **upload_options**: 可选配置项(JSON格式)
    """
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Received upload documents request - TraceID: {trace_id}")
    
    # 验证参数
    if not knowledge_base_name or not knowledge_base_name.strip():
        raise ValidationException("知识库名称不能为空")
    
    if not files:
        raise ValidationException("请选择要上传的文件")
    
    # 解析上传选项
    parsed_upload_options = None
    if upload_options:
        try:
            import json
            parsed_upload_options = json.loads(upload_options)
        except json.JSONDecodeError:
            raise ValidationException("上传选项格式错误，请使用有效的JSON格式")
    
    # 获取服务实例
    service_registry = getattr(request.app.state, 'service_registry', None)
    service = service_registry.get_service('retrieval') if service_registry else None
    handlers = service.handlers if service else None
    
    if not handlers:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_INIT_ERROR,
            message=get_service_error_message(RETRIEVAL_SERVICE_INIT_ERROR)
        )
    
    # 调用业务逻辑处理
    result = await handlers.upload_documents(
        files=files,
        knowledge_base_name=knowledge_base_name.strip(),
        upload_options=parsed_upload_options,
        trace_id=trace_id
    )
    
    return BaseResponse.success(
        data=result.dict(),
        trace_id=trace_id
    )


@retrieval_router.get("/build-task-status/{build_task_id}", response_model=BaseResponse, summary=["获取知识库构建任务状态"])
async def get_build_task_status(
    request: Request,
    build_task_id: str
):
    """
    查询知识库构建任务状态
    
    - **build_task_id**: 构建任务ID
    """
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Received build task status query - TraceID: {trace_id}, TaskID: {build_task_id}")
    
    # 验证参数
    if not build_task_id or not build_task_id.strip():
        raise ValidationException("构建任务ID不能为空")
    
    # 获取服务实例
    service_registry = getattr(request.app.state, 'service_registry', None)
    service = service_registry.get_service('retrieval') if service_registry else None
    handlers = service.handlers if service else None
    
    if not handlers:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_INIT_ERROR,
            message=get_service_error_message(RETRIEVAL_SERVICE_INIT_ERROR)
        )
    
    # 调用业务逻辑处理（包含任务ID格式校验）
    result = await handlers.get_build_task_status(
        task_id=build_task_id.strip(),
        trace_id=trace_id
    )
    
    if result is None:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_TASK_NOT_FOUND_ERROR,
            message=get_service_error_message(RETRIEVAL_SERVICE_TASK_NOT_FOUND_ERROR)
        )
    
    return BaseResponse.success(
        data=result,
        trace_id=trace_id
    )


@retrieval_router.post("/build-knowledge-base", response_model=BaseResponse, summary=["构建知识库"])
async def build_knowledge_base(
    request: Request,
    build_request: KnowledgeBaseBuildRequest
):
    """
    构建知识库：清洗文档并进行向量化，生成可检索的知识库
    """
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Received build knowledge base request - TraceID: {trace_id}")
    
    # 验证参数
    if not build_request.knowledge_base_name or not build_request.knowledge_base_name.strip():
        raise ValidationException("知识库名称不能为空")
    
    # 获取服务实例
    service_registry = getattr(request.app.state, 'service_registry', None)
    service = service_registry.get_service('retrieval') if service_registry else None
    handlers = service.handlers if service else None
    
    if not handlers:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_INIT_ERROR,
            message=get_service_error_message(RETRIEVAL_SERVICE_INIT_ERROR)
        )
    
    # 调用知识库构建业务逻辑处理
    result = await handlers.build_knowledge_base(
        knowledge_base_name=build_request.knowledge_base_name.strip(),
        clean_settings=build_request.clean_settings,
        trace_id=trace_id
    )
    
    return BaseResponse.success(
        data=result.dict(),
        trace_id=trace_id
    )

@retrieval_router.post("/query", response_model=BaseResponse, summary=["查询知识库"])
async def query_knowledge_base(
    request: Request,
    query_request: RetrievalQueryRequest
):
    """
    查询知识库：根据问题查询知识库
    """
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Received query knowledge base request - TraceID: {trace_id}")
    
    # 获取服务实例
    service_registry = getattr(request.app.state, 'service_registry', None)
    service = service_registry.get_service('retrieval') if service_registry else None
    handlers = service.handlers if service else None
    
    if not handlers:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_INIT_ERROR,
            message=get_service_error_message(RETRIEVAL_SERVICE_INIT_ERROR)
        )
    
    # 调用知识库查询业务逻辑处理
    result = await handlers.query_knowledge_base(
        knowledge_base_name=query_request.knowledge_base_name,
        kb_version=query_request.kb_version,
        query_text=query_request.query_text,
        trace_id=trace_id
    )
    
    return BaseResponse.success(
        data=result.dict(),
        trace_id=trace_id
    )


@retrieval_router.get("/knowledge-base/{knowledge_base_name}", 
                     response_model=BaseResponse, 
                     summary=["查询知识库版本信息"])
async def get_knowledge_base_info(
    request: Request,
    knowledge_base_name: str
):
    """
    查询知识库各版本详细信息
    
    - **knowledge_base_name**: 知识库名称
    """
    trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
    logger.info(f"Received get knowledge base info request - TraceID: {trace_id}, KB: {knowledge_base_name}")
    
    # 验证参数
    if not knowledge_base_name or not knowledge_base_name.strip():
        raise ValidationException("知识库名称不能为空")
    
    # 获取服务实例
    service_registry = getattr(request.app.state, "service_registry", None)
    service = service_registry.get_service("retrieval") if service_registry else None
    handlers = service.handlers if service else None
    
    if not handlers:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_INIT_ERROR,
            message=get_service_error_message(RETRIEVAL_SERVICE_INIT_ERROR)
        )
    
    # 调用业务逻辑处理
    result = await handlers.get_knowledge_base_info(
        knowledge_base_name=knowledge_base_name.strip(),
        trace_id=trace_id
    )
    
    return BaseResponse.success(
        data=result.dict(),
        trace_id=trace_id
    )

