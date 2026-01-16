'''
Description: Chat服务API路由定义
Author: zyq
Date: 2025-09-03 18:29:16
LastEditors: zyq
LastEditTime: 2025-12-03 09:34:03
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
    ResponseMode,
    AddFeedBacksRequest,
    GetFeedBacksRequest,
    AddSuggestedQuestionsRequest,
    GetHistoryMessageRequest,
    GetConversationListRequest,
    DeleteConversationRequest,
    RenameConversationRequest,
    WorkflowRequest,
    WorkflowBlockResponse,
    GetWorkflowRunRequest,
    GetWorkflowRunResponse,
    StopWorkflowTaskRequest,
    StopWorkflowTaskResponse,
    UploadFilesToWorkflowPlatformRequest,
    UploadFilesToWorkflowPlatformResponse,
    GetWorkflowLogsRequest,
    GetWorkflowLogsResponse,
    GetAppBaseInfoRequest,
    GetAppBaseInfoResponse,
    GetWebAppInfoRequest,
    GetWebAppInfoResponse,
    AddWorkflowApiKeyRequest,
    AddWorkflowApiKeyResponse,
    GetWorkflowApiKeyResponse,
    UpdateChatFlowApiKeyRequest,
    AddOAuthInfoRequest,
    AddWorkFlowOAuthInfoRequest,
    UpdateOAuthInfoRequest,
    GetWorkspaceListRequest,
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

@chat_router.post("/update-chatflow-apikey", response_model=BaseResponse, summary="更新对话流平台apikey信息")
async def update_chatflow_apikey_info(request: UpdateChatFlowApiKeyRequest, http_request: Request):
    """更新对话流平台apikey信息"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Update ChatFlow API key info request started | TraceID: {trace_id}")
    
    handlers = check_service_initialized(http_request)
    
    response = handlers.update_chatflow_apikey_info(request, http_request.state.user_id, trace_id)
    
    logger.info(f"Update ChatFlow API key info request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.dict(),
        trace_id=trace_id
    )

@chat_router.post("/add-chatflow-oauth", response_model=BaseResponse, summary="增加Coze OAuth配置(支持pem文件上传)")
async def add_chatflow_oauth_info(
    http_request: Request,
    chatflow_name: str = Form(...),
    bot_id: str = Form(...),
    oauth_client_id: str = Form(...),
    oauth_public_key: str = Form(...),
    oauth_name: str = Form(...),
    oauth_private_key_file: UploadFile = File(...),
):
    """增加Coze OAuth配置, 需要上传pem私钥文件"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Add ChatFlow OAuth info request started | TraceID: {trace_id}")
    handlers = check_service_initialized(http_request)

    if not oauth_private_key_file.filename or not oauth_private_key_file.filename.lower().endswith(".pem"):
        raise ValidationException("请上传.pem格式的私钥文件")

    private_key_bytes = await oauth_private_key_file.read()
    await oauth_private_key_file.close()
    if not private_key_bytes:
        raise ValidationException("上传的私钥文件内容为空")

    if len(private_key_bytes) > 200 * 1024:
        raise ValidationException("私钥文件过大, 请检查后重新上传")

    request = AddOAuthInfoRequest(
        chatflow_name=chatflow_name,
        bot_id=bot_id,
        oauth_client_id=oauth_client_id.strip(),
        oauth_public_key=oauth_public_key.strip(),
        oauth_private_key=private_key_bytes.decode("utf-8"),
        oauth_name=oauth_name.strip(),
    )
    response = handlers.add_chatflow_oauth_info(request, http_request.state.user_id, trace_id)

    logger.info(f"Add ChatFlow OAuth info request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.dict(),
        trace_id=trace_id
    )

@chat_router.post("/update-chatflow-oauth", response_model=BaseResponse, summary="更新Coze OAuth配置(支持pem文件上传)")
async def update_chatflow_oauth_info(
    http_request: Request,
    chatflow_name: str = Form(...),
    bot_id: str = Form(None),
    oauth_client_id: str = Form(None),
    oauth_public_key: str = Form(None),
    oauth_name: str = Form(None),
    oauth_private_key_file: UploadFile = File(None),
):
    """更新Coze OAuth配置"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Update ChatFlow OAuth info request started | TraceID: {trace_id}")
    handlers = check_service_initialized(http_request)

    private_key_str = None
    if oauth_private_key_file:
        if not oauth_private_key_file.filename.lower().endswith(".pem"):
            raise ValidationException("请上传.pem格式的私钥文件")
        private_key_bytes = await oauth_private_key_file.read()
        await oauth_private_key_file.close()
        if not private_key_bytes:
            raise ValidationException("上传的私钥文件内容为空")
        if len(private_key_bytes) > 200 * 1024:
            raise ValidationException("私钥文件过大, 请检查后重新上传")
        private_key_str = private_key_bytes.decode("utf-8")

    request = UpdateOAuthInfoRequest(
        chatflow_name=chatflow_name,
        bot_id=bot_id,
        oauth_client_id=oauth_client_id.strip() if oauth_client_id else None,
        oauth_public_key=oauth_public_key.strip() if oauth_public_key else None,
        oauth_private_key=private_key_str,
        oauth_name=oauth_name.strip() if oauth_name else None,
    )
    response = handlers.update_chatflow_oauth_info(request, http_request.state.user_id, trace_id)

    logger.info(f"Update ChatFlow OAuth info request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.dict(),
        trace_id=trace_id
    )


@chat_router.post("/get-workspace-list", response_model=BaseResponse, summary="获取Coze工作空间列表")
async def get_workspace_list(request: GetWorkspaceListRequest, http_request: Request):
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Get workspace list request started | TraceID: {trace_id}")

    handlers = check_service_initialized(http_request)

    response = await handlers.get_workspace_list(request, http_request.state.user_id, trace_id)

    logger.info(f"Get workspace list request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.model_dump(),
        trace_id=trace_id
    )

@chat_router.get("/get-chatflow-oauth", response_model=BaseResponse, summary="获取Coze OAuth配置列表")
async def get_chatflow_oauth_info(http_request: Request):
    """获取Coze OAuth配置列表"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Get ChatFlow OAuth info request started | TraceID: {trace_id}")

    handlers = check_service_initialized(http_request)

    response = handlers.get_chatflow_oauth_info(http_request.state.user_id, trace_id)

    logger.info(f"Get ChatFlow OAuth info request completed | TraceID: {trace_id}")
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

    if request.response_mode == ResponseMode.STREAM:
        # 流式响应处理
        stream_generator = handlers.chatflow_stream_mode(request, http_request.state.user_id, trace_id)
        
        return StreamingResponse(
            stream_generator,
            media_type="text/event-stream",
            headers={"X-Trace-ID": trace_id}
        )
    
    else:
        # 非流式响应处理
        response = await handlers.chatflow_block_mode(request, http_request.state.user_id, trace_id)
    
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
        platform_user=platform_user,
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

    response = await handlers.stop_chatflow_task(request, http_request.state.user_id, trace_id)

    logger.info(f"Stop ChatFlow task request completed | TraceID: {trace_id}")

    return BaseResponse.success(
        data=response,
        trace_id=trace_id
    )

@chat_router.post("/add-chatflow-feedbacks", response_model=BaseResponse, summary="添加消息反馈")
async def add_feedbacks(request: AddFeedBacksRequest, http_request: Request):
    """添加消息反馈接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Add feedbacks request started | TraceID: {trace_id}")

    handlers = check_service_initialized(http_request)

    response = await handlers.add_feedbacks(request, http_request.state.user_id, trace_id)

    logger.info(f"Add feedbacks request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response,
        trace_id=trace_id
    )

@chat_router.post("/get-chaflow-feedbacks", response_model=BaseResponse, summary="获取消息反馈")
async def get_feedbacks(request: GetFeedBacksRequest, http_request: Request):
    """获取APP的消息点赞和反馈接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Get feedbacks request started | TraceID: {trace_id}")

    handlers = check_service_initialized(http_request)

    response = await handlers.get_feedbacks(request, http_request.state.user_id, trace_id)

    logger.info(f"Get feedbacks request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response,
        trace_id=trace_id
    )

@chat_router.post("/add-chatflow-suggested-questions", response_model=BaseResponse, summary="添加建议问题")
async def add_suggested_questions(request: AddSuggestedQuestionsRequest, http_request: Request):
    """添加建议问题接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Add suggested questions request started | TraceID: {trace_id}")

    handlers = check_service_initialized(http_request)

    response = await handlers.add_suggested_questions(request, http_request.state.user_id, trace_id)

    logger.info(f"Add suggested questions request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response,
        trace_id=trace_id
    )

@chat_router.post("/get-chatflow-history-message", response_model=BaseResponse, summary="获取历史消息")
async def get_history_message(request: GetHistoryMessageRequest, http_request: Request):
    """获取单个会话的历史消息接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Get history message request started | TraceID: {trace_id}")

    handlers = check_service_initialized(http_request)

    response = await handlers.get_history_message(request, http_request.state.user_id, trace_id)

    logger.info(f"Get history message request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.model_dump(),
        trace_id=trace_id
    )

@chat_router.post("/get-chatflow-conversation-list", response_model=BaseResponse, summary="获取会话列表")
async def get_conversation_list(request: GetConversationListRequest, http_request: Request):
    """获取会话列表接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Get conversation list request started | TraceID: {trace_id}")

    handlers = check_service_initialized(http_request)

    response = await handlers.get_conversation_list(request, http_request.state.user_id, trace_id)

    logger.info(f"Get conversation list request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response,
        trace_id=trace_id
    )

@chat_router.post("/add-workflow-oauth", response_model=BaseResponse, summary="增加工作流Coze OAuth配置(支持pem文件上传)")
async def add_workflow_oauth_info(
    http_request: Request,
    workflow_name: str = Form(...),
    workflow_id: str = Form(...),
    bot_id: str = Form(""),
    oauth_client_id: str = Form(...),
    oauth_public_key: str = Form(...),
    oauth_name: str = Form(...),
    oauth_private_key_file: UploadFile = File(...),
):
    """增加工作流Coze OAuth配置, 需要上传pem私钥文件"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Add WorkFlow OAuth info request started | TraceID: {trace_id}")
    handlers = check_service_initialized(http_request)

    if not oauth_private_key_file.filename or not oauth_private_key_file.filename.lower().endswith(".pem"):
        raise ValidationException("请上传.pem格式的私钥文件")

    private_key_bytes = await oauth_private_key_file.read()
    await oauth_private_key_file.close()
    if not private_key_bytes:
        raise ValidationException("上传的私钥文件内容为空")

    if len(private_key_bytes) > 200 * 1024:
        raise ValidationException("私钥文件过大, 请检查后重新上传")

    request = AddWorkFlowOAuthInfoRequest(
        workflow_name=workflow_name,
        workflow_id=workflow_id,
        bot_id=bot_id,
        oauth_client_id=oauth_client_id.strip(),
        oauth_public_key=oauth_public_key.strip(),
        oauth_private_key=private_key_bytes.decode("utf-8"),
        oauth_name=oauth_name.strip(),
    )
    response = handlers.add_workflow_oauth_info(request, http_request.state.user_id, trace_id)

    logger.info(f"Add WorkFlow OAuth info request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.dict(),
        trace_id=trace_id
    )
@chat_router.post("/workflow", response_model=BaseResponse, summary="工作流平台请求")
async def workflow(request: WorkflowRequest, http_request: Request):
    """工作流平台请求接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Workflow request started | TraceID: {trace_id}")

    handlers = check_service_initialized(http_request)

    logger.info(f"Workflow request completed | TraceID: {trace_id}")
    
    if request.response_mode == ResponseMode.BLOCK:
        # 非流式响应处理
        response = await handlers.workflow_block_mode(request, http_request.state.user_id, trace_id)
    
        return BaseResponse.success(
            data=response.dict(),
            trace_id=trace_id
        )
    
    else:
        # 流式响应处理
        stream_generator = handlers.workflow_stream_mode(request, http_request.state.user_id, trace_id)
        
        return StreamingResponse(
            stream_generator,
            media_type="text/event-stream",
            headers={"X-Trace-ID": trace_id}
        )

@chat_router.post("/get-workflow-run-status", response_model=BaseResponse, summary="获取workflow执行情况")
async def get_workflow_run_status(request: GetWorkflowRunRequest, http_request: Request):
    """获取workflow执行情况接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Get workflow run status request started | TraceID: {trace_id}")

    handlers = check_service_initialized(http_request)

    response = await handlers.get_workflow_run_status(request, http_request.state.user_id, trace_id)

    logger.info(f"Get workflow run status request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.model_dump(),
        trace_id=trace_id
    )

@chat_router.post("/stop-workflow-task", response_model=BaseResponse, summary="停止workflow任务")
async def stop_workflow_task(request: StopWorkflowTaskRequest, http_request: Request):
    """停止workflow任务接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Stop workflow task request started | TraceID: {trace_id}")

    handlers = check_service_initialized(http_request)

    response = await handlers.stop_workflow_task(request, http_request.state.user_id, trace_id)

    logger.info(f"Stop workflow task request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.model_dump(),
        trace_id=trace_id
    )

@chat_router.post("/upload-files-workflow-platform", response_model=BaseResponse, summary="上传文件到workflow平台")
async def upload_files_to_workflow_platform(
    http_request: Request,
    platform: str = Form(default=ChatFlowPlatform.DIFY, description="平台"),
    platform_user: str = Form(..., description="平台用户标识"),
    workflow_name: str = Form(..., description="工作流名称"),
    files: List[UploadFile] = File(..., description="文件列表")):
    """上传文件到workflow平台接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Upload files to workflow platform request started | TraceID: {trace_id}")

    handlers = check_service_initialized(http_request)

    # 构建请求对象
    request = UploadFilesToWorkflowPlatformRequest(
        platform=platform,
        platform_user=platform_user,
        workflow_name=workflow_name
    )

    # 调用handler处理文件上传
    response = await handlers.upload_files_to_workflow_platform(request, http_request.state.user_id, files, trace_id)

    logger.info(f"Upload files to workflow platform request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.model_dump(),
        trace_id=trace_id
    )

@chat_router.post("/get-workflow-logs", response_model=BaseResponse, summary="获取workflow日志")
async def get_workflow_logs(request: GetWorkflowLogsRequest, http_request: Request):
    """获取workflow日志接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Get workflow logs request started | TraceID: {trace_id}")

    handlers = check_service_initialized(http_request)

    response = await handlers.get_workflow_logs(request, http_request.state.user_id, trace_id)

    logger.info(f"Get workflow logs request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.model_dump(),
        trace_id=trace_id
    )

@chat_router.post("/get-app-base-info", response_model=BaseResponse, summary="获取应用基本信息")
async def get_app_base_info(request: GetAppBaseInfoRequest, http_request: Request):
    """获取应用基本信息接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Get app base info request started | TraceID: {trace_id}")

    handlers = check_service_initialized(http_request)

    response = await handlers.get_app_base_info(request, http_request.state.user_id, trace_id)

    logger.info(f"Get app base info request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.model_dump(),
        trace_id=trace_id
    )

@chat_router.post("/get-webapp-info", response_model=BaseResponse, summary="获取应用WebApp设置")
async def get_webapp_info(request: GetWebAppInfoRequest, http_request: Request):
    """获取应用WebApp设置接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Get webapp info request started | TraceID: {trace_id}")

    handlers = check_service_initialized(http_request)

    response = await handlers.get_webapp_info(request, http_request.state.user_id, trace_id)

    logger.info(f"Get webapp info request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.model_dump(),
        trace_id=trace_id
    )

@chat_router.post("/add-workflow-apikey", response_model=BaseResponse, summary="增加工作流平台apikey信息")
async def add_workflow_apikey_info(request: AddWorkflowApiKeyRequest, http_request: Request):
    """增加工作流平台apikey信息"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Add Workflow API key info request started | TraceID: {trace_id}")

    handlers = check_service_initialized(http_request)

    response = handlers.add_workflow_apikey_info(request, http_request.state.user_id, trace_id)

    logger.info(f"Add Workflow API key info request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response.dict(),
        trace_id=trace_id
    )

@chat_router.get("/get-workflow-apikey", response_model=BaseResponse, summary="获取工作流平台apikey信息列表")
async def get_workflow_apikey_info(http_request: Request):
    """获取工作流平台apikey信息列表"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Get Workflow API key info request started | TraceID: {trace_id}")

    handlers = check_service_initialized(http_request)

    response = handlers.get_workflow_apikey_info(http_request.state.user_id, trace_id)

    logger.info(f"Get Workflow API key info request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response,
        trace_id=trace_id
    )

@chat_router.post("/delete-chatflow-conversation", response_model=BaseResponse, summary="删除会话")
async def delete_conversation(request: DeleteConversationRequest, http_request: Request):
    """删除会话接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Delete conversation request started | TraceID: {trace_id}")

    handlers = check_service_initialized(http_request)

    response = await handlers.delete_conversation(request, http_request.state.user_id, trace_id)

    logger.info(f"Delete conversation request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response,
        trace_id=trace_id
    )

@chat_router.post("/rename-chatflow-conversation", response_model=BaseResponse, summary="会话重命名")
async def rename_conversation(request: RenameConversationRequest, http_request: Request):
    """会话重命名接口"""
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Rename conversation request started | TraceID: {trace_id}")

    handlers = check_service_initialized(http_request)

    response = await handlers.rename_conversation(request, http_request.state.user_id, trace_id)

    logger.info(f"Rename conversation request completed | TraceID: {trace_id}")
    return BaseResponse.success(
        data=response,
        trace_id=trace_id
    )
