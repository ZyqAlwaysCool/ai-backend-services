'''
Description: Dify 平台适配器，封装对话流相关业务逻辑
Author: zyq
Date: 2025-11-20 17:26:31
LastEditors: zyq
LastEditTime: 2025-12-02 18:13:57
'''
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from core.config import get_app_config
from core.exceptions import ValidationException, BaseBusinessException, WorkflowException
from core.workflow_clients.base_workflow import WorkflowStatus
from ..schemas import (
    AppBaseInfo,
    AppType,
    ChatFlowPlatform,
    ChatFlowRequest,
    DeleteConversationRequest,
    GetAppBaseInfoRequest,
    GetAppBaseInfoResponse,
    GetConversationListRequest,
    GetFeedBacksRequest,
    GetHistoryMessageRequest,
    GetHistoryMessageResponse,
    GetWebAppInfoRequest,
    GetWebAppInfoResponse,
    GetWorkflowLogsRequest,
    GetWorkflowLogsResponse,
    GetWorkflowRunRequest,
    GetWorkflowRunResponse,
    UploadFilesToChatFlowPlatformRequest,
    UploadFilesToWorkflowPlatformRequest,
    UploadFilesToWorkflowPlatformResponse,
    WorkflowBlockResponse,
    WorkflowRequest,
    WorkflowRunInfo,
    WorkflowRunLog,
    WorkflowRunStatus,
    WebAppIconType,
    WebAppinfo,
    AddFeedBacksRequest,
    AddSuggestedQuestionsRequest,
    RenameConversationRequest,
    StopChatTaskRequest,
    StopWorkflowTaskRequest,
    StopWorkflowTaskResponse,
)
from ...services_err_codes import (
    CHAT_SERVICE_ADD_FEEDBACK_ERROR,
    CHAT_SERVICE_ADD_SUGGESTED_QUESTION_ERROR,
    CHAT_SERVICE_DELETE_CONVERSATION_ERROR,
    CHAT_SERVICE_DIFY_CHAT_ERROR,
    CHAT_SERVICE_DIFY_UPLOAD_FILE_ERROR,
    CHAT_SERVICE_DIFY_WORKFLOW_ERROR,
    CHAT_SERVICE_GET_APP_INFO_ERROR,
    CHAT_SERVICE_GET_APP_SITE_ERROR,
    CHAT_SERVICE_GET_CONVERSATION_LIST_ERROR,
    CHAT_SERVICE_GET_FEEDBACK_ERROR,
    CHAT_SERVICE_GET_HISTORY_MESSAGE_ERROR,
    CHAT_SERVICE_GET_WORKFLOW_LOGS_ERROR,
    CHAT_SERVICE_GET_WORKFLOW_RUN_STATUS_ERROR,
    CHAT_SERVICE_RENAME_CONVERSATION_ERROR,
    CHAT_SERVICE_STOP_CHAT_TASK_ERROR,
    CHAT_SERVICE_STOP_WORKFLOW_TASK_ERROR,
    CHAT_SERVICE_UPLOAD_WORKFLOW_FILE_ERROR,
)
from ...services_err_codes import get_service_error_message
from .credential_service import CredentialService


class DifyPlatformAdapter:
    """Dify 平台适配器"""

    def __init__(
        self,
        credential_service: CredentialService,
        get_files_info: Callable[[ChatFlowRequest], List[Dict[str, Any]]],
        chatflow_upload_limit: int,
        chatflow_singlefile_maxsize: int,
        workflow_upload_limit: int,
        workflow_singlefile_maxsize: int,
        safe_json_loads: Callable[[Any, Optional[Dict[str, Any]]], Dict[str, Any]],
        normalize_workflow_status: Callable[[Any], WorkflowRunStatus],
    ):
        self._credential_service = credential_service
        self._get_files_info = get_files_info
        self._chatflow_upload_limit = chatflow_upload_limit
        self._chatflow_singlefile_maxsize = chatflow_singlefile_maxsize
        self._workflow_upload_limit = workflow_upload_limit
        self._workflow_singlefile_maxsize = workflow_singlefile_maxsize
        self._safe_json_loads = safe_json_loads
        self._normalize_workflow_status = normalize_workflow_status
        self._app_config = get_app_config()

    async def upload_files(
        self,
        request: UploadFilesToChatFlowPlatformRequest,
        login_user: str,
        files,
        trace_id: Optional[str] = None,
    ):
        if len(files) > self._workflow_upload_limit:
            raise ValidationException(f"单次上传文件数量不能超过{self._workflow_upload_limit}个")

        dify_client = self._credential_service.create_dify_chatflow_client(
            user_id=login_user,
            chatflow_name=request.chatflow_name,
            platform_user=request.platform_user,
            dify_url=self._app_config.dify_url,
        )

        uploaded_files_info = []
        temp_file_paths: List[str] = []

        try:
            for file in files:
                content = await file.read()
                file_size = len(content)

                if file_size > self._chatflow_singlefile_maxsize:
                    raise ValidationException(
                        f"文件 {file.filename} 超过最大允许大小 {self._chatflow_singlefile_maxsize / (1024 * 1024)} MB"
                    )

                with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as temp_file:
                    temp_file.write(content)
                    temp_file_path = temp_file.name
                    temp_file_paths.append(temp_file_path)

                logger.info(f"temp file created: {temp_file_path} for original file: {file.filename}")

                resp = await dify_client.upload_chatflow_file(file_path=temp_file_path)
                if resp.status == WorkflowStatus.FAILED:
                    logger.error(f"failed to upload file {file.filename}: {resp.message}")
                    raise BaseBusinessException(
                        code=CHAT_SERVICE_DIFY_UPLOAD_FILE_ERROR,
                        message=get_service_error_message(CHAT_SERVICE_DIFY_UPLOAD_FILE_ERROR),
                        details=resp.message,
                    )
                file_info = resp.data
                file_info["file_name"] = file.filename
                file_info["file_id"] = file_info.get("id")
                uploaded_files_info.append(file_info)
                logger.info(f"file uploaded success: {file.filename} -> file_id={file_info.get('id')}")
        finally:
            for temp_path in temp_file_paths:
                try:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                        logger.info(f"temp file cleaned: {temp_path}")
                except Exception as exc:
                    logger.warning(f"failed to clean temp file {temp_path}: {str(exc)}")

        return uploaded_files_info

    async def chat_block(
        self,
        request: ChatFlowRequest,
        login_user: str,
    ):
        dify_files = self._get_files_info(request)
        dify_client = self._credential_service.create_dify_chatflow_client(
            user_id=login_user,
            chatflow_name=request.chatflow_name,
            platform_user=request.platform_user,
            dify_url=self._app_config.dify_url,
        )

        resp = await dify_client.execute_chatflow_block(request.query, inputs=request.inputs, files=dify_files)
        if resp.status == WorkflowStatus.FAILED:
            raise WorkflowException(
                code=CHAT_SERVICE_DIFY_CHAT_ERROR,
                message=get_service_error_message(CHAT_SERVICE_DIFY_CHAT_ERROR),
                details=resp.model_dump(),
            )

        dify_data = resp.data if isinstance(resp.data, dict) else {}
        return {
            "answer": dify_data.get("answer", ""),
            "conversation_id": dify_data.get("conversation_id", ""),
            "metadata": dify_data.get("metadata"),
            "message_id": dify_data.get("message_id", ""),
        }

    async def chat_stream(self, request: ChatFlowRequest, login_user: str):
        dify_files = self._get_files_info(request)
        dify_client = self._credential_service.create_dify_chatflow_client(
            user_id=login_user,
            chatflow_name=request.chatflow_name,
            platform_user=request.platform_user,
            dify_url=self._app_config.dify_url,
        )

        stop_event = asyncio.Event()
        try:
            async for chunk in dify_client.chatflow_sse_raw(
                stop_flag=stop_event,
                query=request.query,
                inputs=request.inputs,
                files=dify_files,
            ):
                yield chunk
        except asyncio.CancelledError:
            stop_event.set()
            raise
        except Exception as exc:
            raise WorkflowException(
                code=CHAT_SERVICE_DIFY_CHAT_ERROR,
                message=get_service_error_message(CHAT_SERVICE_DIFY_CHAT_ERROR),
                details=str(exc),
            )

    async def list_conversations(self, request: GetConversationListRequest, login_user: str):
        dify_client = self._credential_service.create_dify_chatflow_client(
            user_id=login_user,
            chatflow_name=request.chatflow_name,
            platform_user=request.platform_user,
            dify_url=self._app_config.dify_url,
        )

        resp = await dify_client.get_chatflow_conversation_list(
            user=request.platform_user,
            last_id=request.last_id,
            limit=request.limit,
        )

        if resp.status == WorkflowStatus.FAILED:
            logger.error(f"get conversation list failed error={resp.message}")
            raise WorkflowException(
                code=CHAT_SERVICE_GET_CONVERSATION_LIST_ERROR,
                message=get_service_error_message(CHAT_SERVICE_GET_CONVERSATION_LIST_ERROR),
                details=resp.message,
        )

        return resp.data

    async def get_history_message(self, request: GetHistoryMessageRequest, login_user: str) -> GetHistoryMessageResponse:
        dify_client = self._credential_service.create_dify_chatflow_client(
            user_id=login_user,
            chatflow_name=request.chatflow_name,
            platform_user=request.platform_user,
            dify_url=self._app_config.dify_url,
        )

        resp = await dify_client.get_chatflow_conversation_history(
            conversation_id=request.conversation_id,
            user=request.platform_user,
        )

        if resp.status == WorkflowStatus.FAILED:
            logger.error(f"get history message failed error={resp.message}")
            raise WorkflowException(
                code=CHAT_SERVICE_GET_HISTORY_MESSAGE_ERROR,
                message=get_service_error_message(CHAT_SERVICE_GET_HISTORY_MESSAGE_ERROR),
                details=resp.message,
            )

        dify_data = resp.data if isinstance(resp.data, dict) else {}
        return GetHistoryMessageResponse(message_list=dify_data.get("data", []))

    async def delete_conversation(self, request: DeleteConversationRequest, login_user: str):
        dify_client = self._credential_service.create_dify_chatflow_client(
            user_id=login_user,
            chatflow_name=request.chatflow_name,
            platform_user=request.platform_user,
            dify_url=self._app_config.dify_url,
        )

        resp = await dify_client.delete_chatflow_conversation(
            conversation_id=request.conversation_id,
            user=request.platform_user,
        )
        if resp.status == WorkflowStatus.FAILED:
            logger.error(f"delete conversation failed error={resp.message}")
            raise WorkflowException(
                code=CHAT_SERVICE_DELETE_CONVERSATION_ERROR,
                message=get_service_error_message(CHAT_SERVICE_DELETE_CONVERSATION_ERROR),
                details=resp.message,
            )
        return resp.data

    async def rename_conversation(self, request: RenameConversationRequest, login_user: str):
        dify_client = self._credential_service.create_dify_chatflow_client(
            user_id=login_user,
            chatflow_name=request.chatflow_name,
            platform_user=request.platform_user,
            dify_url=self._app_config.dify_url,
        )

        resp = await dify_client.rename_chatflow_conversation(
            conversation_id=request.conversation_id,
            name=request.name,
            auto_generate=False,
            user=request.platform_user,
        )
        if resp.status == WorkflowStatus.FAILED:
            logger.error(f"rename conversation failed error={resp.message}")
            raise WorkflowException(
                code=CHAT_SERVICE_RENAME_CONVERSATION_ERROR,
                message=get_service_error_message(CHAT_SERVICE_RENAME_CONVERSATION_ERROR),
                details=resp.message,
            )
        return resp.data

    async def add_feedbacks(self, request: AddFeedBacksRequest, login_user: str):
        dify_client = self._credential_service.create_dify_chatflow_client(
            user_id=login_user,
            chatflow_name=request.chatflow_name,
            platform_user=request.platform_user,
            dify_url=self._app_config.dify_url,
        )
        resp = await dify_client.chatflow_message_feedback(
            message_id=request.message_id,
            rating=request.rating.value if request.rating != "" else None,
            user=request.platform_user,
            content=request.content,
        )
        if resp.status == WorkflowStatus.FAILED:
            logger.error(f"add feedbacks failed error={resp.message}")
            raise WorkflowException(
                code=CHAT_SERVICE_ADD_FEEDBACK_ERROR,
                message=get_service_error_message(CHAT_SERVICE_ADD_FEEDBACK_ERROR),
                details=resp.message,
            )
        return resp.data

    async def get_feedbacks(self, request: GetFeedBacksRequest, login_user: str):
        dify_client = self._credential_service.create_dify_chatflow_client(
            user_id=login_user,
            chatflow_name=request.chatflow_name,
            platform_user=request.platform_user,
            dify_url=self._app_config.dify_url,
        )
        resp = await dify_client.get_chatflow_app_feedbacks(
            page=request.page,
            limit=request.limit,
        )
        if resp.status == WorkflowStatus.FAILED:
            logger.error(f"get feedbacks failed error={resp.message}")
            raise WorkflowException(
                code=CHAT_SERVICE_GET_FEEDBACK_ERROR,
                message=get_service_error_message(CHAT_SERVICE_GET_FEEDBACK_ERROR),
                details=resp.message,
            )
        return resp.data

    async def add_suggested_questions(self, request: AddSuggestedQuestionsRequest, login_user: str):
        dify_client = self._credential_service.create_dify_chatflow_client(
            user_id=login_user,
            chatflow_name=request.chatflow_name,
            platform_user=request.platform_user,
            dify_url=self._app_config.dify_url,
        )
        resp = await dify_client.get_chatflow_suggested_questions(
            message_id=request.message_id,
            user=request.platform_user,
        )
        if resp.status == WorkflowStatus.FAILED:
            logger.error(f"add suggested questions failed error={resp.message}")
            raise WorkflowException(
                code=CHAT_SERVICE_ADD_SUGGESTED_QUESTION_ERROR,
                message=get_service_error_message(CHAT_SERVICE_ADD_SUGGESTED_QUESTION_ERROR),
                details=resp.message,
            )
        return resp.data

    async def stop_chatflow_task(self, request: StopChatTaskRequest, login_user: str):
        dify_client = self._credential_service.create_dify_chatflow_client(
            user_id=login_user,
            chatflow_name=request.chatflow_name,
            platform_user=request.platform_user,
            dify_url=self._app_config.dify_url,
        )
        resp = await dify_client.stop_chatflow_task(task_id=request.task_id)
        if resp.status == WorkflowStatus.FAILED:
            logger.error(f"stop chatflow task failed error={resp.message}")
            raise WorkflowException(
                code=CHAT_SERVICE_STOP_CHAT_TASK_ERROR,
                message=get_service_error_message(CHAT_SERVICE_STOP_CHAT_TASK_ERROR),
                details=resp.message,
            )
        return resp.data

    async def upload_workflow_files(
        self,
        request: UploadFilesToWorkflowPlatformRequest,
        login_user: str,
        files,
        trace_id: Optional[str] = None,
    ) -> UploadFilesToWorkflowPlatformResponse:
        if len(files) > self._workflow_upload_limit:
            raise ValidationException(f"单次上传文件数量不能超过{self._workflow_upload_limit}个")

        dify_client = self._credential_service.create_dify_workflow_client(
            user_id=login_user,
            workflow_name=request.workflow_name,
            platform_user=request.platform_user,
            dify_url=self._app_config.dify_url,
        )

        uploaded_files_info = []
        temp_file_paths: List[str] = []

        try:
            for file in files:
                content = await file.read()
                file_size = len(content)

                if file_size > self._workflow_singlefile_maxsize:
                    raise ValidationException(
                        f"文件 {file.filename} 超过最大允许大小 {self._workflow_singlefile_maxsize / (1024 * 1024)} MB"
                    )

                with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as temp_file:
                    temp_file.write(content)
                    temp_file_path = temp_file.name
                    temp_file_paths.append(temp_file_path)

                logger.info(f"temp file created: {temp_file_path} for original file: {file.filename}")

                resp = await dify_client.upload_workflow_file(file_path=temp_file_path)
                if resp.status == WorkflowStatus.FAILED:
                    logger.error(f"failed to upload workflow file {file.filename}: {resp.message}")
                    raise BaseBusinessException(
                        code=CHAT_SERVICE_UPLOAD_WORKFLOW_FILE_ERROR,
                        message=get_service_error_message(CHAT_SERVICE_UPLOAD_WORKFLOW_FILE_ERROR),
                        details=resp.message,
                    )
                file_info = resp.data
                file_info["file_name"] = file.filename
                uploaded_files_info.append(file_info)
                logger.info(f"file uploaded success: {file.filename} -> file_id={file_info.get('id')}")
        finally:
            for temp_path in temp_file_paths:
                try:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                        logger.info(f"temp file cleaned: {temp_path}")
                except Exception as exc:
                    logger.warning(f"failed to clean temp file {temp_path}: {str(exc)}")

        return UploadFilesToWorkflowPlatformResponse(file_info_list=uploaded_files_info)

    async def workflow_block_mode(self, request: WorkflowRequest, login_user: str) -> WorkflowBlockResponse:
        dify_files = self._get_files_info(request)
        dify_client = self._credential_service.create_dify_workflow_client(
            user_id=login_user,
            workflow_name=request.workflow_name,
            platform_user=request.platform_user,
            dify_url=self._app_config.dify_url,
        )

        resp = await dify_client.execute_workflow_block(inputs=request.inputs, files=dify_files)
        if resp.status == WorkflowStatus.FAILED:
            raise WorkflowException(
                code=CHAT_SERVICE_DIFY_CHAT_ERROR,
                message=get_service_error_message(CHAT_SERVICE_DIFY_CHAT_ERROR),
                details=resp.model_dump(),
            )

        dify_data = resp.data if isinstance(resp.data, dict) else {}
        workflow_run_id = dify_data.get("workflow_run_id", "")
        task_id = dify_data.get("task_id", "")
        outputs = dify_data.get("data", {}).get("outputs", {})
        return WorkflowBlockResponse(
            workflow_run_id=workflow_run_id,
            task_id=task_id,
            outputs=outputs,
        )

    async def workflow_stream_mode(self, request: WorkflowRequest, login_user: str):
        dify_files = self._get_files_info(request)
        dify_client = self._credential_service.create_dify_workflow_client(
            user_id=login_user,
            workflow_name=request.workflow_name,
            platform_user=request.platform_user,
            dify_url=self._app_config.dify_url,
        )

        stop_event = asyncio.Event()
        try:
            async for chunk in dify_client.workflow_sse_raw(
                stop_flag=stop_event,
                inputs=request.inputs,
                files=dify_files,
            ):
                yield chunk
        except asyncio.CancelledError:
            stop_event.set()
            raise
        except Exception as exc:
            raise WorkflowException(
                code=CHAT_SERVICE_DIFY_WORKFLOW_ERROR,
                message=get_service_error_message(CHAT_SERVICE_DIFY_WORKFLOW_ERROR),
                details=str(exc),
            )

    async def get_workflow_run_status(self, request: GetWorkflowRunRequest, login_user: str) -> GetWorkflowRunResponse:
        dify_client = self._credential_service.create_dify_workflow_client(
            user_id=login_user,
            workflow_name=request.workflow_name,
            platform_user=request.platform_user,
            dify_url=self._app_config.dify_url,
        )
        resp = await dify_client.get_workflow_run_status(workflow_run_id=request.workflow_run_id)
        if resp.status == WorkflowStatus.FAILED:
            logger.error(f"get workflow run status failed error={resp.message}")
            raise WorkflowException(
                code=CHAT_SERVICE_GET_WORKFLOW_RUN_STATUS_ERROR,
                message=get_service_error_message(CHAT_SERVICE_GET_WORKFLOW_RUN_STATUS_ERROR),
                details=resp.message,
            )
        dify_data = resp.data if isinstance(resp.data, dict) else {}
        workflow_run_info = WorkflowRunInfo(
            id=dify_data.get("id", ""),
            workflow_id=dify_data.get("workflow_id", ""),
            status=self._normalize_workflow_status(dify_data.get("status", WorkflowRunStatus.FAILED.value)),
            inputs=self._safe_json_loads(dify_data.get("inputs"), {}),
            outputs=self._safe_json_loads(dify_data.get("outputs"), {}),
            error=dify_data.get("error"),
            total_steps=dify_data.get("total_steps", 0),
            total_tokens=dify_data.get("total_tokens", 0),
            created_at=dify_data.get("created_at", 0),
            finished_at=dify_data.get("finished_at"),
            elapsed_time=dify_data.get("elapsed_time", 0.0),
        )
        return GetWorkflowRunResponse(workflow_run=workflow_run_info)

    async def stop_workflow_task(self, request: StopWorkflowTaskRequest, login_user: str) -> StopWorkflowTaskResponse:
        dify_client = self._credential_service.create_dify_workflow_client(
            user_id=login_user,
            workflow_name=request.workflow_name,
            platform_user=request.platform_user,
            dify_url=self._app_config.dify_url,
        )
        resp = await dify_client.stop_workflow_task(task_id=request.task_id)
        if resp.status == WorkflowStatus.FAILED:
            logger.error(f"stop workflow task failed error={resp.message}")
            raise WorkflowException(
                code=CHAT_SERVICE_STOP_WORKFLOW_TASK_ERROR,
                message=get_service_error_message(CHAT_SERVICE_STOP_WORKFLOW_TASK_ERROR),
                details=resp.message,
            )
        dify_data = resp.data if isinstance(resp.data, dict) else {}
        result = dify_data.get("result", "success")
        return StopWorkflowTaskResponse(result=result)

    async def get_workflow_logs(self, request: GetWorkflowLogsRequest, login_user: str) -> GetWorkflowLogsResponse:
        dify_client = self._credential_service.create_dify_workflow_client(
            user_id=login_user,
            workflow_name=request.workflow_name,
            platform_user=request.platform_user,
            dify_url=self._app_config.dify_url,
        )
        resp = await dify_client.get_workflow_logs(
            keyword=request.keyword,
            status=request.status,
            page=request.page,
            limit=request.limit,
            created_by_end_user_session_id=request.created_by_end_user_session_id,
            created_by_account=request.created_by_account,
        )
        if resp.status == WorkflowStatus.FAILED:
            logger.error(f"get workflow logs failed error={resp.message}")
            raise WorkflowException(
                code=CHAT_SERVICE_GET_WORKFLOW_LOGS_ERROR,
                message=get_service_error_message(CHAT_SERVICE_GET_WORKFLOW_LOGS_ERROR),
                details=resp.message,
            )
        dify_data = resp.data if isinstance(resp.data, dict) else {}
        workflow_logs = []
        for log_data in dify_data.get("data", []):
            workflow_log = WorkflowRunLog(
                id=log_data.get("id", ""),
                workflow_run=log_data.get("workflow_run", {}),
                created_from=log_data.get("created_from", ""),
                created_by_role=log_data.get("created_by_role", ""),
                created_by_account=log_data.get("created_by_account"),
                created_by_end_user=log_data.get("created_by_end_user"),
                created_at=log_data.get("created_at", 0),
            )
            workflow_logs.append(workflow_log)

        return GetWorkflowLogsResponse(
            page=dify_data.get("page", request.page),
            limit=dify_data.get("limit", request.limit),
            total=dify_data.get("total", 0),
            has_more=dify_data.get("has_more", False),
            data=workflow_logs,
        )

    async def get_app_base_info(self, request: GetAppBaseInfoRequest, login_user: str) -> GetAppBaseInfoResponse:
        if request.app_type == AppType.CHATFLOW:
            dify_client = self._credential_service.create_dify_chatflow_client(
                user_id=login_user,
                chatflow_name=request.apikey_name,
                platform_user=login_user,
                dify_url=self._app_config.dify_url,
            )
        elif request.app_type == AppType.WORKFLOW:
            dify_client = self._credential_service.create_dify_workflow_client(
                user_id=login_user,
                workflow_name=request.apikey_name,
                platform_user=login_user,
                dify_url=self._app_config.dify_url,
            )
        else:
            raise ValidationException(f"不支持的应用类型: {request.app_type}")
        resp = await dify_client.get_app_info()
        if resp.status == WorkflowStatus.FAILED:
            logger.error(f"get app base info failed error={resp.message}")
            raise WorkflowException(
                code=CHAT_SERVICE_GET_APP_INFO_ERROR,
                message=get_service_error_message(CHAT_SERVICE_GET_APP_INFO_ERROR),
                details=resp.message,
            )
        dify_data = resp.data if isinstance(resp.data, dict) else {}
        app_info = AppBaseInfo(
            name=dify_data.get("name", ""),
            description=dify_data.get("description", ""),
            tags=dify_data.get("tags", []),
            mode=dify_data.get("mode", ""),
            author_name=dify_data.get("author_name", ""),
        )
        return GetAppBaseInfoResponse(app_info=app_info)

    async def get_webapp_info(self, request: GetWebAppInfoRequest, login_user: str) -> GetWebAppInfoResponse:
        if request.app_type == AppType.CHATFLOW:
            dify_client = self._credential_service.create_dify_chatflow_client(
                user_id=login_user,
                chatflow_name=request.apikey_name,
                platform_user=login_user,
                dify_url=self._app_config.dify_url,
            )
        elif request.app_type == AppType.WORKFLOW:
            dify_client = self._credential_service.create_dify_workflow_client(
                user_id=login_user,
                workflow_name=request.apikey_name,
                platform_user=login_user,
                dify_url=self._app_config.dify_url,
            )
        else:
            raise ValidationException(f"不支持的应用类型: {request.app_type}")
        resp = await dify_client.get_app_site()
        if resp.status == WorkflowStatus.FAILED:
            logger.error(f"get webapp info failed error={resp.message}")
            raise WorkflowException(
                code=CHAT_SERVICE_GET_APP_SITE_ERROR,
                message=get_service_error_message(CHAT_SERVICE_GET_APP_SITE_ERROR),
                details=resp.message,
            )
        dify_data = resp.data if isinstance(resp.data, dict) else {}
        icon_type_str = dify_data.get("icon_type", "emoji")
        icon_type = WebAppIconType.EMO if icon_type_str == "emoji" else WebAppIconType.IMG
        webapp_info = WebAppinfo(
            title=dify_data.get("title", ""),
            icon_type=icon_type,
            icon=dify_data.get("icon", ""),
            icon_background=dify_data.get("icon_background", ""),
            icon_url=dify_data.get("icon_url", ""),
            description=dify_data.get("description", ""),
            copyright=dify_data.get("copyright", ""),
            privacy_policy=dify_data.get("privacy_policy", ""),
            custom_disclaimer=dify_data.get("custom_disclaimer", ""),
            default_language=dify_data.get("default_language", ""),
            show_workflow_steps=dify_data.get("show_workflow_steps", False),
        )
        return GetWebAppInfoResponse(app_info=webapp_info)
