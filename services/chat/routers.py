'''
Description: Chat服务API路由定义
Author: zyq
Date: 2025-09-03 18:29:16
LastEditors: zyq
LastEditTime: 2025-11-05 17:51:06
'''

import uuid
from fastapi import APIRouter, HTTPException, Request, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from loguru import logger
from typing import List

from core.schemas.base_resp_model_define import BaseResponse
from core.config.error_codes import *
from core.exceptions import ValidationException, BaseBusinessException
from .schemas import (
    ChatRequest, 
    AddChatFlowApiKeyRequest,
    ChatFlowRequest,
    UploadFilesToChatFlowPlatformRequest,
    UploadFilesToChatFlowPlatformResponse,
    StopChatTaskRequest,
    ChatFlowPlatform,
    ChatFlowResponseMode,
)
from .handlers import ChatHandlers


chat_router = APIRouter(tags=["对话服务"])

def check_service_initialized(http_request: Request):
    # 从service_registry获取chat服务的handlers实例
    service_registry = getattr(http_request.app.state, 'service_registry', None)
    chat_service = service_registry.get_service('chat') if service_registry else None
    handlers = chat_service.handlers if chat_service else None
    if not handlers:
        raise BaseBusinessException(
            code=COMMON_ERROR_REQUEST_PARSE_ERROR,
            message="Chat服务未初始化"
        )
    return handlers

async def _stream_wrapper(generator, trace_id: str):
    """流式响应包装器 - 返回原始chunk块"""
    try:
        async for chunk in generator:
            # 直接返回原始StreamChatChunk对象的字典形式
            yield f"data: {chunk.json()}\n\n"
    except Exception as e:
        logger.error(f"Stream processing error error={str(e)} | TraceID: {trace_id}")
        # 流式错误也返回原始格式
        error_chunk = {
            "content": "",
            "finish_reason": "error",
            "model": "",
            "error": str(e)
        }
        yield f"data: {error_chunk}\n\n"


@chat_router.post("/chat", response_model=BaseResponse, summary="非流式对话")
async def chat(request: ChatRequest, http_request: Request):
    """对话接口(非流式响应,根据history字段判断单轮/多轮)"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Chat request started | TraceID: {trace_id}")
    
    handlers = check_service_initialized(http_request)
    
    response = await handlers.chat(request, trace_id)
    
    logger.info(f"Chat request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.dict(),
        trace_id=trace_id
    )


@chat_router.post("/chat-stream", summary="流式对话")
async def chat_stream(request: ChatRequest, http_request: Request):
    """对话接口(流式响应,根据history字段判断单轮/多轮)"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Chat stream request started | TraceID: {trace_id}")
    
    handlers = check_service_initialized(http_request)
    
    # 获取流式生成器
    stream_generator = handlers.chat_stream(request, trace_id)
    
    logger.info(f"Chat stream request completed | TraceID: {trace_id}")
    # 返回流式响应 - 原始chunk块
    return StreamingResponse(
        _stream_wrapper(stream_generator, trace_id),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Trace-ID": trace_id
        }
    )


@chat_router.get("/models", response_model=BaseResponse, summary="获取可用模型")
async def get_enabled_models(http_request: Request):
    """获取启用的模型列表"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Get enabled models request started | TraceID: {trace_id}")
    
    handlers = check_service_initialized(http_request)
    
    enabled_models = handlers.get_enabled_models()
    
    logger.info(f"Get enabled models request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data={"models": enabled_models},
        trace_id=trace_id
    )

@chat_router.post("/add-chatflow-apikey", response_model=BaseResponse, summary="增加对话流平台apikey信息")
async def add_chatflow_apikey_info(request: AddChatFlowApiKeyRequest, http_request: Request):
    """增加对话流平台apikey信息"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Add ChatFlow API key info request started | TraceID: {trace_id}")
    
    handlers = check_service_initialized(http_request)
    
    response = handlers.add_chatflow_apikey_info(request, http_request.state.user_id, trace_id)
    
    logger.info(f"Add ChatFlow API key info request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.dict(),
        trace_id=trace_id
    )

@chat_router.get("/get-chatflow-apikey", response_model=BaseResponse, summary="获取对话流平台apikey信息列表")
async def get_chatflow_apikey_info(http_request: Request):
    """获取对话流平台apikey信息列表"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Get ChatFlow API key info request started | TraceID: {trace_id}")
    
    handlers = check_service_initialized(http_request)
    
    response = handlers.get_chatflow_apikey_info(http_request.state.user_id, trace_id)
    
    logger.info(f"Get ChatFlow API key info request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.dict(),
        trace_id=trace_id
    )

@chat_router.post("/chatflow", summary="对话流平台请求")
async def chatflow(request: ChatFlowRequest, http_request: Request):
    """对话流平台请求接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"ChatFlow request started | TraceID: {trace_id}")
    
    handlers = check_service_initialized(http_request)
    
    logger.info(f"ChatFlow request completed | TraceID: {trace_id}")

    if request.response_mode == ChatFlowResponseMode.STREAM:
        # 流式响应处理
        return BaseResponse.success(
            data="streaming response initiated",
            trace_id=trace_id
        )
    
    else:
        # 非流式响应处理
        response = handlers.chatflow_block_mode(request, http_request.state.user_id, trace_id)
    
        return BaseResponse.success(
            data=response.dict(),
            trace_id=trace_id
        )

@chat_router.post("/upload-files-chatflow-platform", response_model=BaseResponse, summary="上传文件到对话流平台")
async def upload_files_to_chatflow_platform(
    http_request: Request,
    platform: str = Form(default=ChatFlowPlatform.DIFY, description="对话流平台"),
    platform_user: str = Form(..., description="平台用户标识"),
    chatflow_name: str = Form(..., description="对话流名称"),
    files: List[UploadFile] = File(..., description="文件列表")):
    """上传文件到对话流平台接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Upload files to ChatFlow platform request started | TraceID: {trace_id}")

    handlers = check_service_initialized(http_request)

    # 构建请求对象
    request = UploadFilesToChatFlowPlatformRequest(
        platform=platform,
        user=platform_user,
        chatflow_name=chatflow_name
    )

    # 调用handler处理文件上传
    response = await handlers.upload_files_to_chatflow_platform(request, http_request.state.user_id, files, trace_id)

    logger.info(f"Upload files to ChatFlow platform request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.dict(),
        trace_id=trace_id
    )

@chat_router.post("/stop-chatflow-task", response_model=BaseResponse, summary="停止对话流任务")
async def stop_chatflow_task(request: StopChatTaskRequest, http_request: Request):
    """停止对话流任务接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Stop ChatFlow task request started | TraceID: {trace_id}")
    
    handlers = check_service_initialized(http_request)
    
    logger.info(f"Stop ChatFlow task request completed | TraceID: {trace_id}")
    
    return BaseResponse.success(
        data="test22",
        trace_id=trace_id
    )