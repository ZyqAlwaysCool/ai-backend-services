'''
Description: 通用dify http client, 封装dify的后台api接口
Author: zyq
Date: 2025-07-29 17:51:12
LastEditors: zyq
LastEditTime: 2025-11-11 17:32:43
'''
import yaml
from pathlib import Path
from loguru import logger
from typing import Dict, List, Any, Optional, Union, AsyncGenerator
from pydantic import BaseModel, Field
import httpx
import json
import os
import asyncio
import mimetypes
from deprecated import deprecated

from .base_workflow import BaseWorkflowClient, WorkflowType, WorkflowResponse, WorkflowStatus
from ..exceptions import WorkflowException

# 保持向后兼容的响应模型
class DifyClientResp(BaseModel):
    status: str = Field(default="success")
    message: str = Field(default="")
    data: Union[str, Dict[str, Any], None] = Field(default="")
    conversation_id: str = Field(default="")
    
    @classmethod
    def success(cls, data: Union[str, Dict[str, Any]], conv_id: str=""):
        return cls(data=data, conversation_id=conv_id)
    
    @classmethod
    def error(cls, msg: str):
        return cls(status="error", message=msg)


class DifyClient(BaseWorkflowClient):
    def __init__(self, dify_url: str, access_api_key: str, workflow_name: str, user_id: str, timeout: int=120):
        # 调用父类初始化
        super().__init__(
            workflow_name=workflow_name,
            workflow_type=WorkflowType.DIFY,
            base_url=dify_url,
            user_id=user_id,
            timeout=timeout
        )
        
        self._base_url = dify_url
        self._dify_api_key = access_api_key
        self._dify_task_id = ""
        self._dify_conversation_id = ""
        self._dify_current_task_status = True
        self._dify_user_id = user_id
        
        # 请求参数设置
        self.sync_req_timeout = timeout
        self.async_req_timeout = httpx.Timeout(2 * timeout, read=timeout)
        
        logger.info(f"dify client init success. workflow_name=({self.workflow_name}) url=({self._base_url})")
    
    @staticmethod
    def _format_sse_error(message: str) -> str:
        """构造符合SSE规范的错误事件数据"""
        return f"event: error\ndata: {json.dumps({'error': message})}\n\n"
    
    @deprecated(version="1.0", reason="此方法已废弃, 请使用 chat_sse 或 chat_sse_raw 方法")
    async def __async_request_for_stream_chat(self, url: str, headers: dict, payload: dict, is_split_think: bool=True) -> DifyClientResp:
        """异步http请求封装. 目前与dify流式返回业务信息耦合"""
        logger.info(f"start async request for stream chat. workflow_name=({self.workflow_name}) url=({url}) headers=({headers}) payload=({payload})")
        try:
            async with httpx.AsyncClient(timeout=self.async_req_timeout, limits=httpx.Limits(max_connections=None)) as client:
                    async with client.stream("POST", url=url, headers=headers, json=payload) as resp:
                        resp.raise_for_status()
                        llm_resp_full_text = ""
                        async for line in resp.aiter_lines():
                            if self._dify_current_task_status == False:
                                # 触发终止任务动作
                                logger.info(f"stop current task. workflow_name=({self.workflow_name}) task_id=({self._dify_task_id})")
                                return DifyClientResp.error(msg="stop current task")
                            if line.startswith("data:"):
                                try:
                                    data = json.loads(line[5:].strip())
                                    if data.get("event") == "message":
                                        self.dify_conversation_id = data.get("conversation_id")
                                        self._dify_task_id = data.get("task_id")
                                        llm_resp_full_text += data.get("answer", "")
                                except json.JSONDecodeError as e:
                                    logger.error("decode json error: %s", e)
                                    return DifyClientResp.error(msg=str(e))
                        if is_split_think:
                            # 是否切掉回答中的think部分内容
                            _, sep, tail = llm_resp_full_text.partition("</think>")
                            llm_resp_no_think = tail.strip() if sep else llm_resp_full_text.strip()
                        else:
                            llm_resp_no_think = llm_resp_full_text
                        return DifyClientResp.success(data=llm_resp_no_think, conv_id=self.dify_conversation_id)
        except httpx.HTTPError as e:
            logger.error(f"async http failed. error: {str(e)}")
            return DifyClientResp.error(msg=str(e))
        except httpx.RequestError as e:
            logger.error(f"async request failed. error: {str(e)}")
            return DifyClientResp.error(msg=str(e))
    
    def __sync_request(self, 
                       url: str, 
                       method: str, 
                       headers: Optional[Dict[str, str]]=None, 
                       params: Optional[Dict[str, Any]]=None, 
                       json: Any=None, 
                       data: Any=None, 
                       files: Any=None) -> httpx.Response:
        """通用同步http请求封装"""
        logger.info(f"start sync request. url=({url}) headers=({headers}) method=({method}) params=({params}) data=({data}) json=({json})")
        with httpx.Client(timeout=self.sync_req_timeout) as client:
            response = client.request(method.upper(), url, headers=headers, params=params, json=json, data=data, files=files)
            response.raise_for_status()
            return response

    
    async def __async_request(
        self,
        url: str,
        method: str = "POST",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        stream: bool = False,
        **client_kwargs: Any,
    ) -> httpx.Response:
        """
        通用异步HTTP请求。
        返回原始 httpx.Response，由调用者自行处理（.json() / .text / .iter_bytes() …）。
        任何网络异常都会直接抛出，方便调用者捕获后决定重试或降级。
        """
        logger.info(f"start async request. workflow_name=({self.workflow_name}) url=({url}) method=({method}) params=({params})")
        async with httpx.AsyncClient(timeout=self.async_req_timeout, limits=httpx.Limits(max_connections=None)) as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                headers=headers,
                json=data if files is None else None,  # 传 json 时不能同时传 files
                data=data if files is not None else None,
                files=files,
                params=params,
            )
            response.raise_for_status()
            if not stream:
                await response.aread()  # 一次性读完整 body

            # 对于204 NO CONTENT状态码，避免JSON解析错误
            if response.status_code == 204:
                logger.info("end async request. response=HTTP 204 No Content")
            else:
                logger.info(f"end async request. response=({response.json()})")
            return response
    
    @deprecated(version="1.0", reason="此流式对话方法已废弃, 请使用 chat_sse 或 chat_sse_raw 方法")
    async def stream_chat(self, query: str, inputs: Optional[Dict[str, Any]]=None, is_split_think: bool=True) -> DifyClientResp:
        """流式对话"""
        logger.info(f"start stream chat. query=({query})")
        inputs = inputs or {}
        url = f"{self._base_url}/chat-messages"
        headers = {
            "Authorization": f"Bearer {self._dify_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "response_mode": "streaming",
            "user": self._dify_user_id,
            "inputs": inputs,
        }
        
        
        chat_result = await self.__async_request_for_stream_chat(url, headers, payload, is_split_think=is_split_think)
        
        return chat_result
    
    async def execute_chatflow_block(self, query: str, inputs: Optional[Dict[str, Any]]=None, files: Optional[List[Any]]=None, user_id: str=None) -> DifyClientResp:
        """阻塞模式执行对话流, 提取执行结果"""
        inputs = inputs or {}
        files = files or []
        logger.info(f"start execute chatflow. chatflow_name=({self.workflow_name}) inputs=({inputs})")
        url = f"{self._base_url}/chat-messages"
        headers = {
            'Authorization': f"Bearer {self._dify_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "response_mode": "blocking",
            "user": user_id if user_id else self._dify_user_id,
            "conversation_id": "" if inputs.get("conversation_id") is None else inputs.get("conversation_id"),
            "inputs": inputs,
            "files": files
        }
        try:
            response = await self.__async_request(url=url, method="POST", headers=headers, data=payload)
            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"execute chatflow failed. HTTP error: {str(e)} dify_response: {e.response.text if hasattr(e, 'response') else 'N/A'}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"execute chatflow failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务，请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"execute chatflow failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"execute chatflow failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"execute chatflow failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="执行对话流失败，请稍后重试")
        
        return DifyClientResp.success(data=body)
    
    async def execute_workflow(self, inputs: Optional[Dict[str, Any]]=None, is_stream=False) -> DifyClientResp:
        """执行工作流, 提取执行结果. 目前只支持接收blocking模式的结果. 实测在workflow下, 流式请求的结果也仅存在于【workflow_finished】节点中, 不是像chatflow一样的真流式."""
        inputs = inputs or {}
        logger.info(f"start execute workflow. workflow_name=({self.workflow_name}) inputs=({inputs})")

        if is_stream:
            #TODO: 未实现流式workflow请求, 现阶段改为blocking模式
            is_stream = False
        
        url = f"{self._base_url}/workflows/run"
        headers = {
            'Authorization': f"Bearer {self._dify_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "response_mode": "blocking" if not is_stream else "streaming",
            "user": self._dify_user_id,
            "inputs": inputs,
        }
        
        try:
            response = await self.__async_request(url=url, headers=headers, data=payload)
            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"execute workflow failed. HTTP error: {str(e)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"execute workflow failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务，请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"execute workflow failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"execute workflow failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"execute workflow failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="执行工作流失败，请稍后重试")
        
        data = body.get("data")
        if not isinstance(data, dict):
            logger.error(f"execute workflow failed. invalid resp body: {body}")
            return DifyClientResp.error(msg="workflow response malformed")

        if data.get("status") == "succeeded":
            return DifyClientResp.success(data=data.get("outputs", {}))

        error_msg = data.get("error") or body.get("message") or "workflow run failed"
        return DifyClientResp.error(msg=error_msg)
    
    async def get_conversation_history(self, conversation_id: str, user: str = None) -> DifyClientResp:
        """获取会话历史记录

        Args:
            conversation_id: 会话ID
            user: 用户标识，如不传则使用初始化时的user_id

        Returns:
            DifyClientResp: 包含历史消息列表的响应结果
        """
        logger.info(f"start get conversation history. conversation_id=({conversation_id})")
        url = f"{self._base_url}/messages"
        headers = {
            "Authorization": f"Bearer {self._dify_api_key}",
            "Content-Type": "application/json",
        }
        params = {
            "conversation_id": conversation_id,
            "user": user if user else self._dify_user_id,
        }

        try:
            response = await self.__async_request(url=url, method="GET", headers=headers, params=params)
            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"get conversation history failed. HTTP error: {str(e.response.text)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"get conversation history failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务，请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"get conversation history failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"get conversation history failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"get conversation history failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="获取会话历史失败，请稍后重试")

        return DifyClientResp.success(data=body, conv_id=conversation_id)

    async def get_conversations(self, user: Optional[str] = None, last_id: Optional[str] = None, limit: int = 20) -> DifyClientResp:
        """
        获取会话列表
        """
        logger.info(f"start get conversations. user=({user}) last_id=({last_id}) limit=({limit})")
        url = f"{self._base_url}/conversations"
        headers = {
            "Authorization": f"Bearer {self._dify_api_key}",
            "Content-Type": "application/json",
        }
        params = {
            "user": user if user else self._dify_user_id,
            "limit": limit,
        }
        if last_id:
            params["last_id"] = last_id

        try:
            response = await self.__async_request(url=url, method="GET", headers=headers, params=params)
            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"get conversations failed. HTTP error: {str(e)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"get conversations failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务，请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"get conversations failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"get conversations failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"get conversations failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="获取会话列表失败，请稍后重试")

        return DifyClientResp.success(data=body)
    
    def set_current_task_status(self, status: bool) -> None:
        logger.info(f"set task status. workflow_name=({self.workflow_name}) status=({status})")
        self._dify_current_task_status = status
    
    def get_current_task_status(self) -> bool:
        logger.info(f"get task status. workflow_name=({self.workflow_name})")
        return self._dify_current_task_status
    
    async def stop_task(self, task_id: str="") ->DifyClientResp:
        """终止当前运行的dify任务"""
        logger.info(f"start stop current task. workflow_name=({self.workflow_name}) task_id=({task_id})")
        if task_id == "":
            logger.warning(f"stop current task failed. workflow_name=({self.workflow_name}) no task_id")
            return DifyClientResp.success(data="")
        
        url = f"{self._base_url}/chat-messages/{task_id}/stop"

        headers = {
            "Authorization": f"Bearer {self._dify_api_key}",
            "Content-Type": "application/json",
        }

        data = {
            "user": self._dify_user_id,
        }
        try:
            resp = await self.__async_request(url=url, method="POST", headers=headers,data=data)
            logger.info(f"stop task resp: {resp.json()}")
        except httpx.HTTPStatusError as e:
            logger.error(f"stop current task failed. HTTP error: {str(e)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"stop current task failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务，请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"stop current task failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except Exception as e:
            logger.error(f"stop current task failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="停止任务失败，请稍后重试")
        logger.info(f"stop current task. workflow_name=({self.workflow_name}) task_id=({self._dify_task_id})")
        return DifyClientResp.success(data="")

    async def delete_conversation(self, conversation_id: str, user: Optional[str] = None) -> DifyClientResp:
        """
        删除会话
        """
        logger.info(f"start delete conversation. conversation_id=({conversation_id})")
        url = f"{self._base_url}/conversations/{conversation_id}"
        headers = {
            "Authorization": f"Bearer {self._dify_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "user": user if user else self._dify_user_id,
        }

        try:
            response = await self.__async_request(url=url, method="DELETE", headers=headers, data=payload)

            # 对于204 NO CONTENT响应，直接返回成功
            if response.status_code == 204:
                logger.info(f"delete conversation success. conversation_id=({conversation_id})")
                return DifyClientResp.success(data={"message": "会话删除成功"})

            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"delete conversation failed. HTTP error: {str(e)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"delete conversation failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务，请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"delete conversation failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"delete conversation failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"delete conversation failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="删除会话失败，请稍后重试")

        return DifyClientResp.success(data=body)

    async def rename_conversation(
        self,
        conversation_id: str,
        name: Optional[str] = None,
        auto_generate: bool = False,
        user: Optional[str] = None,
    ) -> DifyClientResp:
        """
        会话重命名
        """
        logger.info(f"start rename conversation. conversation_id=({conversation_id}) name=({name}) auto_generate=({auto_generate})")
        url = f"{self._base_url}/conversations/{conversation_id}/name"
        headers = {
            "Authorization": f"Bearer {self._dify_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "user": user if user else self._dify_user_id,
            "auto_generate": auto_generate,
        }
        if name is not None:
            payload["name"] = name

        try:
            response = await self.__async_request(url=url, method="POST", headers=headers, data=payload)
            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"rename conversation failed. HTTP error: {str(e)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"rename conversation failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务，请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"rename conversation failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"rename conversation failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"rename conversation failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="重命名会话失败，请稍后重试")

        return DifyClientResp.success(data=body)
   
    async def upload_file(self, file_path: str, user: Optional[str] = None) -> DifyClientResp:
        """
        通用文件上传接口,支持多种文件格式

        Args:
            file_path: 文件路径
            user: 用户标识,如不传则使用初始化时的user_id

        Returns:
            DifyClientResp: 上传结果，成功时data包含文件信息字典，包含:
            - id: 文件ID
            - name: 文件名
            - size: 文件大小(bytes)
            - extension: 文件扩展名
            - mime_type: 文件MIME类型
            - created_by: 上传者ID
            - created_at: 上传时间
        """
        logger.info(f"start upload file. file_path=({file_path})")

        # 检查文件是否存在
        if not os.path.exists(file_path):
            return DifyClientResp.error(msg=f"文件不存在: {file_path}")

        # 获取文件扩展名和MIME类型
        file_ext = os.path.splitext(file_path)[1].lower()

        # 常见文件类型的MIME映射
        mime_type_mapping = {
            # 图片格式
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.bmp': 'image/bmp',
            '.svg': 'image/svg+xml',
            # 文档格式
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.txt': 'text/plain',
            '.csv': 'text/csv',
            '.json': 'application/json',
            '.xml': 'application/xml',
            # 音视频格式
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.mp4': 'video/mp4',
            '.avi': 'video/x-msvideo',
            # 压缩格式
            '.zip': 'application/zip',
            '.rar': 'application/x-rar-compressed',
            '.7z': 'application/x-7z-compressed',
        }

        # 获取MIME类型
        mime_type = mime_type_mapping.get(file_ext)
        if not mime_type:
            # 尝试使用系统的mimetypes模块
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                # 如果仍然无法确定,使用默认的二进制类型
                mime_type = 'application/octet-stream'
                logger.warning(f"无法确定文件类型,使用默认MIME类型. file={file_path} mime_type={mime_type}")

        logger.info(f"file upload info. file={os.path.basename(file_path)} ext={file_ext} mime_type={mime_type}")

        # 准备上传
        url = f"{self._base_url}/files/upload"
        headers = {
            "Authorization": f"Bearer {self._dify_api_key}",
        }
        data = {
            "user": user if user else self._dify_user_id,
        }

        # 打开文件并上传
        with open(file_path, "rb") as f:
            files = {
                "file": (os.path.basename(file_path), f, mime_type)
            }

            try:
                response = await self.__async_request(
                    url=url,
                    method="POST",
                    headers=headers,
                    data=data,
                    files=files
                )

                result = response.json()
                logger.info(f"file upload success. file_id={result.get('id')} file_name={result.get('name')}")
                return DifyClientResp.success(data=result)

            except httpx.HTTPStatusError as e:
                logger.error(f"upload file failed. HTTP error: {str(e)} response: {e.response.text if hasattr(e, 'response') else 'N/A'}")
                return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
            except httpx.ConnectError as e:
                logger.error(f"upload file failed. Connection error: {str(e)}")
                return DifyClientResp.error(msg="无法连接到Dify服务，请检查网络连接或服务状态")
            except httpx.RequestError as e:
                logger.error(f"upload file failed. Request error: {str(e)}")
                return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
            except ValueError as e:
                logger.error(f"upload file failed. invalid json resp: {str(e)}")
                return DifyClientResp.error(msg="Dify响应格式错误")
            except Exception as e:
                logger.error(f"upload file failed. unexpected error: {str(e)}")
                return DifyClientResp.error(msg="文件上传失败，请稍后重试")


    async def chat_sse(self, query: str, inputs: dict, stop_flag: asyncio.Event) -> AsyncGenerator[str, None]:
        """流式透传事件消息"""
        logger.info(f"start event stream. query=({query})")
        url = f"{self._base_url}/chat-messages"
        headers = {
            "Authorization": f"Bearer {self._dify_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "response_mode": "streaming",
            "user": self._dify_user_id,
            "inputs": inputs,
        }
        
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url=url, headers=headers, json=payload) as resp:
                if resp.status_code != 200:
                    logger.error(f"error even stream. status_code=({resp.status_code})")
                    yield self._format_sse_error("Dify返回错误")
                    return 
                
                async for line in resp.aiter_lines():
                    if stop_flag.is_set():
                        logger.info(f"stop chat sse. workflow_name=({self.workflow_name})")
                        await resp.aclose()
                        return 
                    if line.startswith("data:"):
                        try:
                            data = json.loads(line[5:].strip())
                            if data.get("event") == "message":
                                ans = data.get("answer", "")
                                yield f"data: {ans}\n\n"
                        except json.JSONDecodeError as e:
                            logger.error(f"error even stream. decode json error: {str(e)}")
                            yield self._format_sse_error(str(e))
                            return 
    
    
    async def chat_sse_raw(self, stop_flag: asyncio.Event, query: str, inputs: Optional[Dict[str, Any]]=None, files: Optional[List[Any]]=None) -> AsyncGenerator[str, None]:
        """流式透传数据块, 不做任何额外处理"""
        inputs = inputs or {}
        files = files or []
        logger.info(f"start raw event stream. query=({query}) inputs=({inputs}) files=({files})")
        url = f"{self._base_url}/chat-messages"
        headers = {
            "Authorization": f"Bearer {self._dify_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "response_mode": "streaming",
            "user": self._dify_user_id,
            "conversation_id": "" if inputs.get("conversation_id") is None else inputs.get("conversation_id"),
            "inputs": inputs,
            "files": files
        }

        try:
            async with httpx.AsyncClient(timeout=self.async_req_timeout) as client:
                async with client.stream("POST", url=url, headers=headers, json=payload) as resp:
                    if resp.status_code != 200:
                        error_text = ""
                        try:
                            error_text = await resp.aread()
                            error_text = error_text.decode('utf-8')
                        except Exception:
                            error_text = f"HTTP {resp.status_code} error"
                        logger.error(f"error raw stream. status_code=({resp.status_code}) resp=({error_text})")
                        yield self._format_sse_error(f"Dify返回错误: {error_text}")
                        return

                    async for line in resp.aiter_lines():
                        if stop_flag.is_set():
                            logger.info(f"stop raw chat sse. workflow_name=({self.workflow_name})")
                            await resp.aclose()
                            return
                        # 直接返回原始行，不做任何处理
                        yield f"{line}\n"

        except httpx.HTTPError as e:
            logger.error(f"chat_sse_raw HTTP error: {str(e)}")
            yield self._format_sse_error(f"网络请求错误: {str(e)}")
        except Exception as e:
            logger.error(f"chat_sse_raw unexpected error: {str(e)}")
            yield self._format_sse_error(f"系统错误: {str(e)}")

    async def message_feedback(self, message_id: str, rating: str, user: str, content: str = "") -> DifyClientResp:
        """消息反馈（点赞）接口

        Args:
            message_id: 消息ID
            rating: 评分，如"like"或"dislike"
            user: 用户标识
            content: 反馈内容，可选

        Returns:
            DifyClientResp: 操作结果
        """
        logger.info(f"start message feedback. message_id=({message_id}) rating=({rating}) user=({user})")
        url = f"{self._base_url}/messages/{message_id}/feedbacks"
        headers = {
            "Authorization": f"Bearer {self._dify_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "rating": rating,
            "user": user,
        }

        # 只有当content不为空时才添加到payload中
        if content:
            payload["content"] = content

        try:
            response = await self.__async_request(url=url, method="POST", headers=headers, data=payload)
            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"message feedback failed. HTTP error: {str(e)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"message feedback failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务，请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"message feedback failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"message feedback failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"message feedback failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="消息反馈失败，请稍后重试")

        return DifyClientResp.success(data=body)

    async def get_app_feedbacks(self, page: int = 1, limit: int = 20) -> DifyClientResp:
        """获取APP的消息点赞和反馈

        Args:
            page: 页码，默认为1
            limit: 每页数量，默认为20

        Returns:
            DifyClientResp: 包含反馈列表的响应结果
        """
        logger.info(f"start get app feedbacks. page=({page}) limit=({limit})")
        url = f"{self._base_url}/app/feedbacks"
        headers = {
            "Authorization": f"Bearer {self._dify_api_key}",
            "Content-Type": "application/json",
        }
        params = {
            "page": page,
            "limit": limit,
        }

        try:
            response = await self.__async_request(url=url, method="GET", headers=headers, params=params)
            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"get app feedbacks failed. HTTP error: {str(e)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"get app feedbacks failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务，请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"get app feedbacks failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"get app feedbacks failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"get app feedbacks failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="获取反馈失败，请稍后重试")

        return DifyClientResp.success(data=body)

    async def get_suggested_questions(self, message_id: str, user: str) -> DifyClientResp:
        """获取下一轮建议问题列表

        Args:
            message_id: 消息ID
            user: 用户标识

        Returns:
            DifyClientResp: 包含建议问题列表的响应结果
        """
        logger.info(f"start get suggested questions. message_id=({message_id}) user=({user})")
        url = f"{self._base_url}/messages/{message_id}/suggested"
        headers = {
            "Authorization": f"Bearer {self._dify_api_key}",
            "Content-Type": "application/json",
        }
        params = {
            "user": user,
        }

        try:
            response = await self.__async_request(url=url, method="GET", headers=headers, params=params)
            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"get suggested questions failed. HTTP error: {str(e.response.text)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"get suggested questions failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务，请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"get suggested questions failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"get suggested questions failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"get suggested questions failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="获取建议问题失败，请稍后重试")

        return DifyClientResp.success(data=body)
