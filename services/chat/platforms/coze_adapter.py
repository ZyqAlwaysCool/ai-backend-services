'''
Description: Coze 平台适配器，封装对话流相关业务逻辑
Author: zyq
Date: 2025-11-20 17:27:06
LastEditors: zyq
LastEditTime: 2025-11-20 18:02:32
'''
from __future__ import annotations

import os
import json
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger
from cozepy import CozeAPIError

from core.exceptions import ValidationException, BaseBusinessException, WorkflowException
from core.workflow_clients.base_workflow import WorkflowStatus
from core.workflow_clients.coze_client import CozeClient
from ..schemas import (
    ChatFlowPlatform,
    ChatFlowRequest,
    UploadFilesToChatFlowPlatformRequest,
    GetConversationListRequest,
    WorkflowRequest,
    WorkflowBlockResponse,
    UploadFilesToWorkflowPlatformRequest,
    UploadFilesToWorkflowPlatformResponse,
    GetWorkspaceListRequest,
    GetWorkspaceListResponse,
    WorkspaceInfo,
)
from .credential_service import CredentialService
from ...services_err_codes import (
    CHAT_SERVICE_COZE_CHAT_ERROR,
    CHAT_SERVICE_COZE_UPLOAD_FILE_ERROR,
    CHAT_SERVICE_GET_CONVERSATION_LIST_ERROR,
    CHAT_SERVICE_DIFY_WORKFLOW_ERROR,
)
from ...services_err_codes import get_service_error_message


class CozePlatformAdapter:
    """Coze 平台适配器"""

    def __init__(
        self,
        credential_service: CredentialService,
        get_files_info: Callable[[ChatFlowRequest], List[Dict[str, Any]]],
        chatflow_upload_limit: int,
        singlefile_maxsize: int,
    ):
        self._credential_service = credential_service
        self._get_files_info = get_files_info
        self._chatflow_upload_limit = chatflow_upload_limit
        self._singlefile_maxsize = singlefile_maxsize

    async def upload_files(
        self,
        request: UploadFilesToChatFlowPlatformRequest,
        login_user: str,
        files,
        trace_id: Optional[str] = None,
        is_workflow:bool = False,
    ):
        if len(files) > self._chatflow_upload_limit:
            raise ValidationException(f"单次上传文件数量不能超过{self._chatflow_upload_limit}个")
        if is_workflow:
            coze_client, bot_id, workflow_id= self._credential_service.create_coze_client(
                user_id=login_user,
                app_name=request.chatflow_name,
                platform_user=request.platform_user,
                is_workflow=is_workflow,
            )            
        else:
            coze_client, _ = self._credential_service.create_coze_client(
                user_id=login_user,
                app_name=request.chatflow_name,
                platform_user=request.platform_user,
                is_workflow=is_workflow,
            )
        uploaded_files_info = []
        temp_file_paths: List[str] = []

        try:
            for file in files:
                content = await file.read()
                file_size = len(content)

                if file_size > self._singlefile_maxsize:
                    raise ValidationException(
                        f"文件 {file.filename} 超过最大允许大小 {self._singlefile_maxsize / (1024 * 1024)} MB"
                    )

                with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as temp_file:
                    temp_file.write(content)
                    temp_file_path = temp_file.name
                    temp_file_paths.append(temp_file_path)

                logger.info(f"temp file created: {temp_file_path} for original file: {file.filename}")

                resp = await coze_client.upload_file(temp_file_path)
                if resp.status == WorkflowStatus.FAILED:
                    logger.error(f"failed to upload coze file {file.filename}: {resp.message}")
                    raise BaseBusinessException(
                        code=CHAT_SERVICE_COZE_UPLOAD_FILE_ERROR,
                        message=get_service_error_message(CHAT_SERVICE_COZE_UPLOAD_FILE_ERROR),
                        details=resp.message,
                    )

                file_info = resp.data or {}
                file_info["file_name"] = file.filename
                file_info["file_id"] = file_info.get("file_id") or file_info.get("id")
                uploaded_files_info.append(file_info)
                logger.info(f"file uploaded success: {file.filename} -> file_id={file_info.get('file_id')}")
        finally:
            for temp_path in temp_file_paths:
                try:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                        logger.info(f"temp file cleaned: {temp_path}")
                except Exception as exc:
                    logger.warning(f"failed to clean temp file {temp_path}: {str(exc)}")

        return uploaded_files_info

    async def chat_block(self, request: ChatFlowRequest, login_user: str):
        coze_client, bot_id = self._credential_service.create_coze_client(
            user_id=login_user,
            app_name=request.chatflow_name,
            platform_user=request.platform_user,
        )
        coze_files = self._get_files_info(request)
        try:
            resp = coze_client.chat_block(
                query=request.query,
                inputs=request.inputs,
                bot_id=bot_id,
                files=coze_files,
            )
        except CozeAPIError as exc:
            logger.error(f"coze chat_block failed user={login_user} chatflow={request.chatflow_name} error={exc}")
            raise WorkflowException(
                code=CHAT_SERVICE_COZE_CHAT_ERROR,
                message=f"Coze调用失败: {exc.msg}",
                details={"code": exc.code, "logid": exc.logid},
            )
        if resp.status == WorkflowStatus.FAILED:
            raise WorkflowException(
                code=CHAT_SERVICE_COZE_CHAT_ERROR,
                message=get_service_error_message(CHAT_SERVICE_COZE_CHAT_ERROR),
                details=resp.model_dump(),
            )

        return {
            "answer": resp.data.get("answer", ""),
            "conversation_id": resp.data.get("conversation_id", ""),
            "message_id": resp.data.get("message_id", ""),
            "metadata": resp.data.get("usages"),
        }

    async def chat_stream(self, request: ChatFlowRequest, login_user: str):
        coze_client, bot_id = self._credential_service.create_coze_client(
            user_id=login_user,
            app_name=request.chatflow_name,
            platform_user=request.platform_user,
        )
        coze_files = self._get_files_info(request)
        try:
            async for chunk in coze_client.chat_stream(
                query=request.query,
                inputs=request.inputs,
                bot_id=bot_id,
                files=coze_files,
            ):
                yield chunk
        except CozeAPIError as exc:
            logger.error(f"coze chat_stream failed user={login_user} chatflow={request.chatflow_name} error={exc}")
            raise WorkflowException(
                code=CHAT_SERVICE_COZE_CHAT_ERROR,
                message=f"Coze调用失败: {exc.msg}",
                details={"code": exc.code, "logid": exc.logid},
            )

    async def list_conversations(self, request: GetConversationListRequest, login_user: str):
        coze_client, bot_id = self._credential_service.create_coze_client(
            user_id=login_user,
            chatflow_name=request.chatflow_name,
            platform_user=request.platform_user,
        )
        page_num = 1
        if request.last_id:
            try:
                page_num = max(int(request.last_id), 1)
            except ValueError:
                logger.warning(
                    "coze conversation list fallback to page 1 due to invalid last_id. last_id=({})",
                    request.last_id,
                )

        try:
            resp = await coze_client.list_conversations(
                bot_id=bot_id,
                page_num=page_num,
                page_size=request.limit,
            )
        except CozeAPIError as exc:
            logger.error(
                "coze get conversation list failed user=({}) chatflow=({}) bot_id=({}) error=({})",
                login_user,
                request.chatflow_name,
                bot_id,
                exc,
            )
            raise WorkflowException(
                code=CHAT_SERVICE_GET_CONVERSATION_LIST_ERROR,
                message=f"Coze调用失败: {exc.msg}",
                details={"code": exc.code, "logid": exc.logid},
            )

        if resp.status == WorkflowStatus.FAILED:
            logger.error(
                "coze get conversation list failed user=({}) chatflow=({}) bot_id=({}) msg=({})",
                login_user,
                request.chatflow_name,
                bot_id,
                resp.message,
            )
            raise WorkflowException(
                code=CHAT_SERVICE_GET_CONVERSATION_LIST_ERROR,
                message=get_service_error_message(CHAT_SERVICE_GET_CONVERSATION_LIST_ERROR),
                details=resp.message,
            )

        return resp.data

    async def workflow_block_mode(self, request: WorkflowRequest, login_user: str) -> WorkflowBlockResponse:
        coze_client, bot_id, workflow_id = self._credential_service.create_coze_client(
            user_id=login_user,
            app_name=request.workflow_name,
            platform_user=request.platform_user,
            is_workflow=True,
        )
        coze_files = self._get_files_info(request)
        parameters = request.inputs if request.inputs else {}
        if coze_files:
            files_list=[]
            for file_info in coze_files:
                file_id = file_info.get("file_id") or file_info.get("id")
                if file_id:
                    files_list.append({"file_id":file_id})       
            parameters["files"] = files_list  

        resp = coze_client.workflow_block(
            workflow_id=workflow_id,
            bot_id=bot_id,
            parameters=parameters,
        )
        if resp.status == WorkflowStatus.FAILED:
            raise WorkflowException(
                code=CHAT_SERVICE_DIFY_WORKFLOW_ERROR,
                message=get_service_error_message(CHAT_SERVICE_DIFY_WORKFLOW_ERROR),
                details=resp.message,
            )
        data = resp.data if isinstance(resp.data, dict) else {}
        return WorkflowBlockResponse(
            workflow_run_id=data.get("execute_id", ""),
            task_id=data.get("execute_id", ""),
            outputs=json.loads(data.get("data", {})) or {},
        )

    async def workflow_stream_mode(self, request: WorkflowRequest, login_user: str):
        coze_client, bot_id, workflow_id = self._credential_service.create_coze_client(
            user_id=login_user,
            app_name=request.workflow_name,
            platform_user=request.platform_user,
            is_workflow=True,
        ) 
        coze_files = self._get_files_info(request)
        parameters = request.inputs 
        if coze_files:
            files_list=[]
            for file_info in coze_files:
                file_id = file_info.get("file_id") or file_info.get("id")
                if file_id:
                    files_list.append({"file_id":file_id})       
            parameters["files"] = files_list                      
        async for chunk in coze_client.workflow_stream(
            workflow_id=workflow_id,
            bot_id=bot_id,
            parameters=parameters,
        ):
            yield chunk

    async def upload_workflow_files(
        self,
        request: UploadFilesToWorkflowPlatformRequest,
        login_user: str,
        files,
        trace_id: Optional[str] = None,
    ) -> UploadFilesToWorkflowPlatformResponse:
        upload_req = UploadFilesToChatFlowPlatformRequest(
            platform=request.platform,
            platform_user=request.platform_user,
            chatflow_name=request.workflow_name,
        )
        infos = await self.upload_files(upload_req, login_user, files, trace_id=trace_id, is_workflow = True)
        return UploadFilesToWorkflowPlatformResponse(file_info_list=infos)

    async def list_workspaces(self, request: GetWorkspaceListRequest, login_user: str) -> GetWorkspaceListResponse:
        coze_client, _ = self._credential_service.create_coze_client(
            user_id=login_user,
            app_name=request.chatflow_name if hasattr(request, "chatflow_name") else "",
            platform_user=login_user,
            is_workflow=True,
        )
        page = request.page_num or 1
        page_size = request.page_size or 20
        try:
            paged = await coze_client.async_coze_client.workspaces.list(page_num=page, page_size=page_size)
        except Exception as exc:
            logger.error(f"coze list workspaces failed user={login_user} error={exc}")
            raise WorkflowException(
                code=CHAT_SERVICE_GET_CONVERSATION_LIST_ERROR,
                message=str(exc),
            )
        workspaces = []
        for ws in paged.items:
            workspaces.append(
                WorkspaceInfo(
                    id=getattr(ws, "id", ""),
                    name=getattr(ws, "name", ""),
                    owner_id=getattr(ws, "owner_id", None),
                    created_at=getattr(ws, "created_at", None),
                    extra=getattr(ws, "__dict__", {}),
                )
            )
        return GetWorkspaceListResponse(
            workspaces=workspaces,
            has_more=paged.has_more,
            page_num=page,
            page_size=page_size,
        )
