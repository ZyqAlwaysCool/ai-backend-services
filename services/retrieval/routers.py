'''
Description: Retrieval服务HTTP路由
Author: zyq
Date: 2025-09-08
'''

import uuid
from typing import List, Optional
from fastapi import APIRouter, Request, UploadFile, File, Form
from loguru import logger

from core.schemas.base_resp_model_define import BaseResponse
from core.exceptions import ValidationException, BaseBusinessException
from .schemas import (RetrievalUploadRequest, RetrievalUploadResponse, 
                      KnowledgeBaseBuildRequest, KnowledgeBaseBuildResponse, BuildTaskStatusResponse,
                      RetrievalQueryRequest
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
    
    try:
        # 验证参数
        if not knowledge_base_name or not knowledge_base_name.strip():
            return BaseResponse.error(
                code=400,
                msg="知识库名称不能为空",
                trace_id=trace_id
            )
        
        if not files:
            return BaseResponse.error(
                code=400,
                msg="请选择要上传的文件",
                trace_id=trace_id
            )
        
        # 解析上传选项
        parsed_upload_options = None
        if upload_options:
            try:
                import json
                parsed_upload_options = json.loads(upload_options)
            except json.JSONDecodeError:
                return BaseResponse.error(
                    code=400,
                    msg="上传选项格式错误，请使用有效的JSON格式",
                    trace_id=trace_id
                )
        
        # 获取服务实例
        service_registry = getattr(request.app.state, 'service_registry', None)
        service = service_registry.get_service('retrieval') if service_registry else None
        handlers = service.handlers if service else None
        
        if not handlers:
            return BaseResponse.error(
                code=500,
                msg="Retrieval服务未初始化",
                trace_id=trace_id
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
        
    except ValidationException as e:
        logger.error(f"Validation error - TraceID: {trace_id}: {str(e)}")
        return BaseResponse.error(code=400, msg=str(e), trace_id=trace_id)
    except BaseBusinessException as e:
        logger.error(f"Business error - TraceID: {trace_id}: {str(e)}")
        return BaseResponse.error(code=e.code, msg=e.message, trace_id=trace_id)
    except Exception as e:
        logger.error(f"Unexpected error - TraceID: {trace_id}: {str(e)}")
        return BaseResponse.error(code=500, msg="服务内部错误", trace_id=trace_id)


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
    
    try:
        # 验证参数
        if not build_task_id or not build_task_id.strip():
            return BaseResponse.error(
                code=400,
                msg="构建任务ID不能为空",
                trace_id=trace_id
            )
        
        # 获取服务实例
        service_registry = getattr(request.app.state, 'service_registry', None)
        service = service_registry.get_service('retrieval') if service_registry else None
        handlers = service.handlers if service else None
        
        if not handlers:
            return BaseResponse.error(
                code=500,
                msg="Retrieval服务未初始化",
                trace_id=trace_id
            )
        
        # 调用业务逻辑处理（包含任务ID格式校验）
        result = await handlers.get_build_task_status(
            task_id=build_task_id.strip(),
            trace_id=trace_id
        )
        
        if result is None:
            return BaseResponse.error(
                code=404,
                msg="构建任务不存在或任务ID格式错误",
                trace_id=trace_id
            )
        
        return BaseResponse.success(
            data=result,
            trace_id=trace_id
        )
        
    except ValidationException as e:
        logger.error(f"Validation error - TraceID: {trace_id}: {str(e)}")
        return BaseResponse.error(code=400, msg=str(e), trace_id=trace_id)
    except BaseBusinessException as e:
        logger.error(f"Business error - TraceID: {trace_id}: {str(e)}")
        return BaseResponse.error(code=e.code, msg=e.message, trace_id=trace_id)
    except Exception as e:
        logger.error(f"Unexpected error - TraceID: {trace_id}: {str(e)}")
        return BaseResponse.error(code=500, msg="服务内部错误", trace_id=trace_id)


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
    
    try:
        # 验证参数
        if not build_request.knowledge_base_name or not build_request.knowledge_base_name.strip():
            return BaseResponse.error(
                code=400,
                msg="知识库名称不能为空",
                trace_id=trace_id
            )
        
        # 获取服务实例
        service_registry = getattr(request.app.state, 'service_registry', None)
        service = service_registry.get_service('retrieval') if service_registry else None
        handlers = service.handlers if service else None
        
        if not handlers:
            return BaseResponse.error(
                code=500,
                msg="Retrieval服务未初始化",
                trace_id=trace_id
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
        
    except ValidationException as e:
        logger.error(f"Validation error - TraceID: {trace_id}: {str(e)}")
        return BaseResponse.error(code=400, msg=str(e), trace_id=trace_id)
    except ValueError as e:
        logger.error(f"Value error - TraceID: {trace_id}: {str(e)}")
        return BaseResponse.error(code=400, msg=str(e), trace_id=trace_id)
    except BaseBusinessException as e:
        logger.error(f"Business error - TraceID: {trace_id}: {str(e)}")
        return BaseResponse.error(code=e.code, msg=e.message, trace_id=trace_id)
    except Exception as e:
        logger.error(f"Unexpected error - TraceID: {trace_id}: {str(e)}")
        return BaseResponse.error(code=500, msg="服务内部错误", trace_id=trace_id)

@retrieval_router.post("/query", response_model=BaseResponse, summary=["查询知识库"])
async def query_knowledge_base(
    request: Request,
    query_request: RetrievalQueryRequest
):
    """
    查询知识库：根据问题查询知识库
    """
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Received build knowledge base request - TraceID: {trace_id}")
    
    try:        
        # 获取服务实例
        service_registry = getattr(request.app.state, 'service_registry', None)
        service = service_registry.get_service('retrieval') if service_registry else None
        handlers = service.handlers if service else None
        
        if not handlers:
            return BaseResponse.error(
                code=500,
                msg="Retrieval服务未初始化",
                trace_id=trace_id
            )
        
        # 调用知识库构建业务逻辑处理
        result = await handlers.query_knowledge_base(
            kb_name_with_version = query_request.kb_name_with_version,
            query_text = query_request.query_text,
            trace_id=trace_id
        )
        
        return BaseResponse.success(
            data=result.dict(),
            trace_id=trace_id
        )
        
    except ValidationException as e:
        logger.error(f"Validation error - TraceID: {trace_id}: {str(e)}")
        return BaseResponse.error(code=400, msg=str(e), trace_id=trace_id)
    except ValueError as e:
        logger.error(f"Value error - TraceID: {trace_id}: {str(e)}")
        return BaseResponse.error(code=400, msg=str(e), trace_id=trace_id)
    except BaseBusinessException as e:
        logger.error(f"Business error - TraceID: {trace_id}: {str(e)}")
        return BaseResponse.error(code=e.code, msg=e.message, trace_id=trace_id)
    except Exception as e:
        logger.error(f"Unexpected error - TraceID: {trace_id}: {str(e)}")
        return BaseResponse.error(code=500, msg="服务内部错误", trace_id=trace_id)