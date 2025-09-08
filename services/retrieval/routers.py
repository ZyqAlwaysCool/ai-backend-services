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
from .schemas import RetrievalUploadRequest, RetrievalUploadResponse

# 创建retrieval服务路由
retrieval_router = APIRouter()


@retrieval_router.post("/upload-files", response_model=BaseResponse)
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