'''
Description: Chat服务数据模型
Author: zyq
Date: 2025-08-26 11:18:33
LastEditors: zyq
LastEditTime: 2025-12-02 17:46:21
'''
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class MessageRole(str, Enum):
    """消息角色枚举"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    """聊天消息模型"""
    role: MessageRole = Field(..., description="消息角色")
    content: str = Field(..., description="消息内容", min_length=1)
    
    class Config:
        use_enum_values = True


class ChatRequest(BaseModel):
    """对话请求模型（统一单轮/多轮）"""
    query: str = Field(..., description="当前用户问题", min_length=1)
    history: List[ChatMessage] = Field(default=[], description="历史对话记录（为空则为单轮对话）")
    model: str = Field("qwen3-32B", description="使用的模型名称")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    temperature: Optional[float] = Field(0.7, description="温度参数")
    max_tokens: Optional[int] = Field(2000, description="最大生成token数")


class ChatResponse(BaseModel):
    """对话响应模型"""
    answer: str = Field(..., description="AI回复内容")
    model: str = Field(..., description="使用的模型")
    usage: Dict[str, int] = Field(..., description="Token使用统计")
    finish_reason: str = Field(..., description="完成原因")


class StreamChatChunk(BaseModel):
    """流式对话数据块"""
    content: str = Field(..., description="增量内容")
    finish_reason: Optional[str] = Field(None, description="完成原因")
    model: str = Field(..., description="使用的模型")


class ChatServiceStatus(BaseModel):
    """Chat服务状态模型"""
    service_name: str = Field(..., description="服务名称")
    version: str = Field(..., description="服务版本")
    status: str = Field(..., description="服务状态")
    enabled_endpoints: List[str] = Field(..., description="启用的端点列表")
    available_models: List[str] = Field(..., description="可用模型列表")
    

# ========================工作流/对话流相关接口适配========================
class ChatFlowPlatform(str, Enum):
    """对话流平台"""
    DIFY = "dify"
    COZE = "coze"

class ApiKeyStatus(str, Enum):
    """API Key状态枚举"""
    ACTIVE = "active"
    DISABLED = "disabled"

class AddChatFlowApiKeyRequest(BaseModel):
    """添加对话流API key请求模型"""
    api_key: str = Field(..., description="对话流API key", min_length=1)
    chatflow_name: str = Field(..., description="对话流名称", min_length=1)
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="对话流平台")
    bot_id: Optional[str] = Field(None, description="机器人ID, 目前仅用于coze平台")
    description: Optional[str] = Field(None, description="备注说明")

class AddChatFlowApiKeyResponse(BaseModel):
    """添加对话流API key响应模型"""
    key_id: str = Field(..., description="API key记录ID")

class UpdateChatFlowApiKeyRequest(BaseModel):
    """更新对话流API key请求模型"""
    api_key: str = Field(..., description="对话流API key", min_length=1)
    chatflow_name: str = Field(..., description="对话流名称", min_length=1)
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="对话流平台")
    bot_id: Optional[str] = Field(None, description="机器人ID, 目前仅用于coze平台")
    description: Optional[str] = Field(None, description="备注说明")

class UpdateChatFlowApiKeyResponse(BaseModel):
    """更新对话流API key响应模型"""
    key_id: str = Field(..., description="API key记录ID")

class ChatFlowApiKeyInfo(BaseModel):
    """对话流API key信息模型"""
    key_id: str = Field(..., description="记录ID")
    user_id: str = Field(..., description="所属用户ID")
    bot_id: Optional[str] = Field(None, description="机器人ID, 目前仅用于coze平台")
    chatflow_name: str = Field(..., description="对话流名称")
    platform: ChatFlowPlatform = Field(default=ChatFlowPlatform.DIFY, description="对话流平台")
    api_key: str = Field(..., description="实际的API key")
    description: Optional[str] = Field(None, description="备注说明")
    status: ApiKeyStatus = Field(default=ApiKeyStatus.ACTIVE, description="状态")
    created_at: datetime = Field(default=datetime.utcnow, description="创建时间")

class AddOAuthInfoRequest(BaseModel):
    """
    Oauth_jwt鉴权方式, 目前仅用于coze平台
    参考: https://github.com/coze-dev/coze-py/blob/main/examples/auth_oauth_jwt.py
    """
    chatflow_name: str = Field(..., description="对话流名称")
    bot_id: str = Field(..., description="Coze机器人ID")
    oauth_client_id: str = Field(..., description="Oauth客户端ID")
    oauth_public_key: str = Field(..., description="Oauth公钥")
    oauth_private_key: str = Field(..., description="Oauth私钥")
    oauth_name: str = Field(..., description="Oauth名称")

class JWTOauthInfo(BaseModel):
    """
    Oauth_jwt鉴权方式, 目前仅用于coze平台
    """
    oauth_key_id: str = Field(..., description="Oauth记录id, 唯一标识")
    user_id: str = Field(..., description="所属用户ID")
    chatflow_name: str = Field(..., description="对话流名称")
    bot_id: str = Field(..., description="Coze机器人ID")
    oauth_name: str = Field(..., description="Oauth名称")
    oauth_client_id: str = Field(..., description="Oauth客户端ID")
    oauth_public_key: str = Field(..., description="Oauth公钥")
    oauth_private_key: str = Field(..., description="Oauth私钥")
    status: ApiKeyStatus = Field(default=ApiKeyStatus.ACTIVE, description="状态")
    created_at: datetime = Field(default=datetime.utcnow, description="创建时间")

class AddOauthInfoResponse(BaseModel):
    oauth_key_id: str = Field(..., description="Oauth记录id, 唯一标识")

class GetOauthInfoResponse(BaseModel):
    oauth_info: List[JWTOauthInfo] = Field(default_factory=list, description="Oauth列表")

class UpdateOAuthInfoRequest(BaseModel):
    """更新Coze OAuth配置请求"""
    chatflow_name: str = Field(..., description="对话流名称")
    bot_id: Optional[str] = Field(None, description="Coze机器人ID")
    oauth_client_id: Optional[str] = Field(None, description="Oauth客户端ID")
    oauth_public_key: Optional[str] = Field(None, description="Oauth公钥")
    oauth_private_key: Optional[str] = Field(None, description="Oauth私钥")
    oauth_name: Optional[str] = Field(None, description="Oauth名称")

class UpdateOauthInfoResponse(BaseModel):
    oauth_key_id: str = Field(..., description="Oauth记录id, 唯一标识")
    
    

class GetChatFlowApiKeyResponse(BaseModel):
    """查询对话流API key响应模型"""
    api_keys_info: List[ChatFlowApiKeyInfo] = Field(default=[], description="对话流API key信息列表")

class ResponseMode(str, Enum):
    """响应模式枚举"""
    BLOCK = "block" # 阻塞
    STREAM = "stream" # 流式

# ========================兼容dify的数据模型========================
class DifyFileTransferMethod(str, Enum):
    """Dify文件传输方式枚举"""
    LOCAL_FILE = "local_file"
    URL = "remote_url"

class DifyResponseMode(str, Enum):
    """Dify响应模式枚举"""
    BLOCK = "blocking"
    STREAM = "streaming"

class DifyFileInfo(BaseModel):
    """dify文件信息模型"""
    transfer_method: DifyFileTransferMethod = Field(DifyFileTransferMethod.LOCAL_FILE, description="文件传输方式")
    type: str = Field(..., description="文件类型")
    upload_file_id: Optional[str] = Field("", description="上传的文件id, 仅当传输方式为local_file时填入")
    url: Optional[str] = Field("", description="文件url, 仅当传输方式为remote_url时填入")

# ========================兼容dify数据模型========================

class UploadFileInfo(BaseModel):
    """上传文件信息模型"""
    file_name: str = Field(..., description="文件名称")
    file_id: str = Field(..., description="文件ID")

class ChatFlowRequest(BaseModel):
    """对话流请求模型(统一dify/coze)"""
    query: str = Field(..., description="用户的问题", min_length=1)
    chatflow_name: str = Field(..., description="对话流名称", min_length=1)
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="对话流平台")
    platform_user: str = Field(..., description="平台用户标识")
    inputs: dict = Field(default={}, description="输入参数")
    response_mode: ResponseMode = Field(ResponseMode.STREAM, description="响应模式, 默认流式")
    files: Optional[List[UploadFileInfo]] = Field(None, description="上传的文件列表")

class UploadFilesToChatFlowPlatformRequest(BaseModel):
    """上传文件到对话流平台请求模型"""
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="对话流平台")
    platform_user: str = Field(..., description="用户标识")
    chatflow_name: str = Field(..., description="对话流名称", min_length=1)

class UploadFilesToChatFlowPlatformResponse(BaseModel):
    """上传文件到对话流平台响应模型"""
    file_info_list: List[Dict] = Field(default_factory=list, description="文件ID列表")

class StopChatTaskRequest(BaseModel):
    """停止对话任务请求模型"""
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="对话流平台")
    task_id: str = Field(..., description="任务ID")
    chatflow_name: str = Field(..., description="对话流名称", min_length=1)
    platform_user: str = Field(..., description="用户标识")

class ChatFlowBlockResponse(BaseModel):
    """对话流阻塞模式响应模型"""
    answer: str = Field(..., description="AI回复内容")
    conversation_id: str = Field(..., description="会话ID")
    message_id: str = Field(..., description="消息ID")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据信息")

class FeedBackRating(str, Enum):
    """消息反馈评分"""
    LIKE = "like"
    DISLIKE = "dislike"
    DEFAULT = ""

class AddFeedBacksRequest(BaseModel):
    """消息反馈(点赞)"""
    message_id: str = Field(..., description="消息ID")
    rating: FeedBackRating = Field(FeedBackRating.DEFAULT, description="评分")
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="对话流平台")
    platform_user: str = Field(..., description="用户标识")
    chatflow_name: str = Field(..., description="对话流名称", min_length=1)
    content: Optional[str] = Field(default="", description="反馈内容")

class GetFeedBacksRequest(BaseModel):
    """获取APP的消息点赞和反馈"""
    platform_user: str = Field(..., description="用户标识")
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="对话流平台")
    chatflow_name: str = Field(..., description="对话流名称", min_length=1)
    page: Optional[int] = Field(default=1, description="分页", gt=0)
    limit: Optional[int] = Field(default=20, description="分页大小", gt=0)

class AddSuggestedQuestionsRequest(BaseModel):
    """添加建议问题"""
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="对话流平台")
    platform_user: str = Field(..., description="用户标识")
    chatflow_name: str = Field(..., description="对话流名称", min_length=1)
    message_id: str = Field(..., description="消息ID")

class GetHistoryMessageRequest(BaseModel):
    """获取单个会话的历史消息"""
    conversation_id: str = Field(..., description="会话ID")
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="对话流平台")
    platform_user: str = Field(..., description="用户标识")
    chatflow_name: str = Field(..., description="对话流名称", min_length=1)
    first_id: Optional[str] = Field(None, description="当前页第一条聊天记录的ID")
    limit: Optional[int] = Field(default=20, description="分页大小", gt=0)

class GetHistoryMessageResponse(BaseModel):
    """获取单个会话的历史消息响应模型"""
    message_list: List[Dict] = Field(default=[], description="消息列表")

class GetConversationListRequest(BaseModel):
    """获取会话列表"""
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="对话流平台")
    platform_user: str = Field(..., description="用户标识")
    chatflow_name: str = Field(..., description="对话流名称", min_length=1)
    last_id: Optional[str] = Field(default="", description="Dify: 当前页最后一条记录的ID; Coze: 作为页码(page_num)")
    limit: Optional[int] = Field(default=20, description="分页大小, Coze默认使用page_size", gt=0, lt=100)

class ConversationListCursor(BaseModel):
    """会话列表分页游标信息"""
    last_id: Optional[str] = Field(None, description="Dify使用的最后一条记录ID")
    first_id: Optional[str] = Field(None, description="Dify返回的第一页记录ID")
    page_num: Optional[int] = Field(None, description="Coze使用的页码")
    page_size: Optional[int] = Field(None, description="分页大小")

class ConversationListResponse(BaseModel):
    """统一的会话列表响应模型"""
    conversations: List[Dict[str, Any]] = Field(default_factory=list, description="会话列表")
    has_more: Optional[bool] = Field(None, description="是否还有更多数据")
    cursor: ConversationListCursor = Field(default_factory=ConversationListCursor, description="分页游标信息")

class DeleteConversationRequest(BaseModel):
    """删除会话"""
    conversation_id: str = Field(..., description="会话ID")
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="对话流平台")
    platform_user: str = Field(..., description="用户标识")
    chatflow_name: str = Field(..., description="对话流名称", min_length=1)

class RenameConversationRequest(BaseModel):
    """会话重命名"""
    conversation_id: str = Field(..., description="会话ID")
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="对话流平台")
    platform_user: str = Field(..., description="用户标识")
    chatflow_name: str = Field(..., description="对话流名称", min_length=1)
    name: str = Field(..., description="会话名称", min_length=1)

class WorkflowRunStatus(str, Enum):
    """工作流执行状态枚举"""
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"

class GetWorkflowRunRequest(BaseModel):
    """获取workflow执行情况请求模型"""
    workflow_run_id: str = Field(..., description="工作流执行ID", min_length=1)
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="平台")
    platform_user: str = Field(..., description="用户标识")
    workflow_name: str = Field(..., description="工作流名称", min_length=1)

class WorkflowRunInfo(BaseModel):
    """工作流执行信息模型"""
    id: str = Field(..., description="工作流执行ID")
    workflow_id: str = Field(..., description="关联的Workflow ID")
    status: WorkflowRunStatus = Field(..., description="执行状态")
    inputs: Dict[str, Any] = Field(..., description="任务输入内容")
    outputs: Dict[str, Any] = Field(None, description="任务输出内容")
    error: Optional[str] = Field(None, description="错误原因")
    total_steps: int = Field(..., description="任务执行总步数")
    total_tokens: int = Field(..., description="任务执行总tokens")
    created_at: int = Field(..., description="任务开始时间")
    finished_at: Optional[int] = Field(None, description="任务结束时间")
    elapsed_time: float = Field(..., description="耗时(s)")

class GetWorkflowRunResponse(BaseModel):
    """获取workflow执行情况响应模型"""
    workflow_run: WorkflowRunInfo = Field(..., description="工作流执行信息")

class StopWorkflowTaskRequest(BaseModel):
    """停止workflow任务请求模型"""
    task_id: str = Field(..., description="任务ID", min_length=1)
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="平台")
    platform_user: str = Field(..., description="用户标识")
    workflow_name: str = Field(..., description="工作流名称", min_length=1)

class StopWorkflowTaskResponse(BaseModel):
    """停止workflow任务响应模型"""
    result: str = Field(..., description="停止结果")

# ========================Workflow API Key管理========================
class AddWorkFlowOAuthInfoRequest(BaseModel):
    """
    Oauth_jwt鉴权方式, 目前仅用于coze平台
    参考: https://github.com/coze-dev/coze-py/blob/main/examples/auth_oauth_jwt.py
    """
    workflow_name: str = Field(..., description="工作流名称")
    workflow_id: str = Field(..., description="Coze工作流ID")    
    bot_id: Optional[str] = Field(None, description="Coze机器人ID")
    oauth_client_id: str = Field(..., description="Oauth客户端ID")
    oauth_public_key: str = Field(..., description="Oauth公钥")
    oauth_private_key: str = Field(..., description="Oauth私钥")
    oauth_name: str = Field(..., description="Oauth名称")
    
class WorkFlowJWTOauthInfo(BaseModel):
    """
    Oauth_jwt鉴权方式, 目前仅用于coze平台
    """
    oauth_key_id: str = Field(..., description="Oauth记录id, 唯一标识")
    user_id: str = Field(..., description="所属用户ID")
    workflow_name: str = Field(..., description="工作流名称")
    workflow_id: str = Field(..., description="Coze工作流ID")    
    bot_id: Optional[str] = Field(None, description="Coze机器人ID")
    oauth_name: str = Field(..., description="Oauth名称")
    oauth_client_id: str = Field(..., description="Oauth客户端ID")
    oauth_public_key: str = Field(..., description="Oauth公钥")
    oauth_private_key: str = Field(..., description="Oauth私钥")
    status: ApiKeyStatus = Field(default=ApiKeyStatus.ACTIVE, description="状态")
    created_at: datetime = Field(default=datetime.utcnow, description="创建时间")

class AddWorkflowApiKeyRequest(BaseModel):
    """添加工作流API key请求模型"""
    api_key: str = Field(..., description="工作流API key", min_length=1)
    workflow_name: str = Field(..., description="工作流名称", min_length=1)
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="平台")
    workflow_id: str = Field(..., description="Coze工作流ID")
    bot_id: Optional[str] = Field(None, description="Coze工作流关联的Bot ID")
    description: Optional[str] = Field(None, description="备注说明")

class AddWorkflowApiKeyResponse(BaseModel):
    """添加工作流API key响应模型"""
    key_id: str = Field(..., description="API key记录ID")

class WorkflowApiKeyInfo(BaseModel):
    """工作流API key信息模型"""
    key_id: str = Field(..., description="记录ID")
    user_id: str = Field(..., description="所属用户ID")
    workflow_name: str = Field(..., description="工作流名称")
    platform: ChatFlowPlatform = Field(default=ChatFlowPlatform.DIFY, description="平台")
    api_key: str = Field(..., description="实际的API key")
    workflow_id: str = Field(None, description="Coze工作流ID")
    bot_id: Optional[str] = Field(None, description="Coze工作流关联Bot ID")
    description: Optional[str] = Field(None, description="备注说明")
    status: ApiKeyStatus = Field(default=ApiKeyStatus.ACTIVE, description="状态")
    created_at: datetime = Field(default=datetime.utcnow, description="创建时间")

class GetWorkflowApiKeyResponse(BaseModel):
    """查询工作流API key响应模型"""
    api_keys_info: List[WorkflowApiKeyInfo] = Field(default=[], description="工作流API key信息列表")

# ========================Coze工作空间============================
class GetWorkspaceListRequest(BaseModel):
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.COZE, description="平台")
    page_num: Optional[int] = Field(1, description="页码", gt=0)
    page_size: Optional[int] = Field(20, description="每页数量", gt=0, le=100)


class WorkspaceInfo(BaseModel):
    id: str = Field(..., description="工作空间ID")
    name: str = Field(..., description="工作空间名称")
    owner_id: Optional[str] = Field(None, description="拥有者ID")
    created_at: Optional[int] = Field(None, description="创建时间")
    extra: Dict[str, Any] = Field(default_factory=dict, description="附加信息")


class GetWorkspaceListResponse(BaseModel):
    workspaces: List[WorkspaceInfo] = Field(default_factory=list, description="工作空间列表")
    has_more: Optional[bool] = Field(None, description="是否有更多")
    page_num: Optional[int] = Field(None, description="页码")
    page_size: Optional[int] = Field(None, description="分页大小")

# ========================Coze工作空间============================
class GetWorkspaceListRequest(BaseModel):
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.COZE, description="平台")
    page_num: Optional[int] = Field(1, description="页码", gt=0)
    page_size: Optional[int] = Field(20, description="每页数量", gt=0, le=100)

class WorkspaceInfo(BaseModel):
    id: str = Field(..., description="工作空间ID")
    name: str = Field(..., description="工作空间名称")
    owner_id: Optional[str] = Field(None, description="拥有者ID")
    created_at: Optional[int] = Field(None, description="创建时间")
    extra: Dict[str, Any] = Field(default_factory=dict, description="附加信息")

class GetWorkspaceListResponse(BaseModel):
    workspaces: List[WorkspaceInfo] = Field(default_factory=list, description="工作空间列表")
    has_more: Optional[bool] = Field(None, description="是否有更多")
    page_num: Optional[int] = Field(None, description="页码")
    page_size: Optional[int] = Field(None, description="分页大小")

class WorkflowRequest(BaseModel):
    """工作流请求模型(统一dify/coze)"""
    workflow_name: str = Field(..., description="工作流名称", min_length=1)
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="工作流平台")
    platform_user: str = Field(..., description="平台用户标识")
    response_mode: ResponseMode = Field(ResponseMode.STREAM, description="响应模式, 默认流式")
    inputs: dict = Field(default={}, description="输入参数")
    files: Optional[List[UploadFileInfo]] = Field(None, description="上传的文件列表")

class WorkflowBlockResponse(BaseModel):
    """工作流阻塞模式响应模型"""
    workflow_run_id: str = Field(..., description="工作流执行ID")
    task_id: str = Field(..., description="任务ID")
    outputs: Dict[str, Any] = Field(..., description="工作流执行结果")

class UploadFilesToWorkflowPlatformRequest(BaseModel):
    """上传文件到workflow平台请求模型"""
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="平台")
    platform_user: str = Field(..., description="用户标识")
    workflow_name: str = Field(..., description="工作流名称", min_length=1)

class UploadFilesToWorkflowPlatformResponse(BaseModel):
    """上传文件到workflow平台响应模型"""
    file_info_list: List[Dict] = Field(default_factory=list, description="文件ID列表")

class GetWorkflowLogsRequest(BaseModel):
    """获取workflow日志请求模型"""
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="平台")
    platform_user: str = Field(..., description="用户标识")
    workflow_name: str = Field(..., description="工作流名称", min_length=1)
    keyword: Optional[str] = Field(None, description="关键字")
    status: Optional[str] = Field(None, description="执行状态 succeeded/failed/stopped")
    page: Optional[int] = Field(1, description="当前页码，默认1", gt=0)
    limit: Optional[int] = Field(20, description="每页条数，默认20", gt=0, le=100)
    created_by_end_user_session_id: Optional[str] = Field(None, description="由哪个endUser创建")
    created_by_account: Optional[str] = Field(None, description="由哪个邮箱账户创建")

class WorkflowRunLog(BaseModel):
    """工作流执行日志信息"""
    id: str = Field(..., description="标识")
    workflow_run: Dict[str, Any] = Field(..., description="Workflow执行日志")
    created_from: str = Field(..., description="来源")
    created_by_role: str = Field(..., description="角色")
    created_by_account: Optional[str] = Field(None, description="账号")
    created_by_end_user: Optional[Dict[str, Any]] = Field(None, description="用户信息")
    created_at: int = Field(..., description="创建时间")

class GetWorkflowLogsResponse(BaseModel):
    """获取workflow日志响应模型"""
    page: int = Field(..., description="当前页码")
    limit: int = Field(..., description="每页条数")
    total: int = Field(..., description="总条数")
    has_more: bool = Field(..., description="是否还有更多数据")
    data: List[WorkflowRunLog] = Field(..., description="当前页码的数据")

# ========================应用相关信息获取接口============================
class AppType(str, Enum):
    WORKFLOW = "workflow"
    CHATFLOW = "chatflow"

class GetAppBaseInfoRequest(BaseModel):
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="平台")
    app_type: AppType = Field(..., description="应用类型: chatflow/workflow")
    apikey_name: str = Field(..., description="apikey映射的名称, chatflow_name/workflow_name", min_length=1)

class AppBaseInfo(BaseModel):
    name: str = Field(..., description="应用名称")
    description: str = Field(..., description="应用描述")
    tags: List[str] = Field(..., description="应用标签")
    mode: str = Field(..., description="应用模式")
    author_name: str = Field(..., description="作者名称")
    
class GetAppBaseInfoResponse(BaseModel):
    app_info: AppBaseInfo = Field(..., description="应用信息")

class GetWebAppInfoRequest(BaseModel):
    platform: ChatFlowPlatform = Field(ChatFlowPlatform.DIFY, description="平台")
    app_type: AppType = Field(..., description="应用类型: chatflow/workflow")
    apikey_name: str = Field(..., description="apikey映射的名称, chatflow_name/workflow_name", min_length=1)

class WebAppIconType(str, Enum):
    EMO = "emoji"
    IMG = "image"

class WebAppinfo(BaseModel):
    title: str = Field(..., description="WebApp名称")
    icon_type: WebAppIconType = Field(..., description="WebApp图标类型")
    icon: str = Field(..., description="WebApp图标")
    icon_background: Optional[str] = Field(None, description="WebApp图标背景色")
    icon_url: Optional[str] = Field(None, description="WebApp图标URL")
    description: Optional[str] = Field(None, description="WebApp描述")
    copyright: Optional[str] = Field(None, description="WebApp版权信息")
    privacy_policy: Optional[str] = Field(None, description="WebApp隐私政策")
    custom_disclaimer: Optional[str] = Field(None, description="WebApp自定义声明")
    default_language: Optional[str] = Field(None, description="WebApp默认语言")
    show_workflow_steps: bool = Field(default=False, description="WebApp是否显示工作流步骤")

class GetWebAppInfoResponse(BaseModel):
    app_info: WebAppinfo = Field(..., description="WebApp应用信息")    
# ========================工作流/对话流相关接口适配========================
