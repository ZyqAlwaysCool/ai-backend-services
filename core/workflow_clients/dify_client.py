'''
Description: 通用dify http client, 封装dify的后台api接口
Author: zyq
Date: 2025-07-29 17:51:12
LastEditors: zyq
LastEditTime: 2025-11-06 10:49:57
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
                            llm_resp_no_think = llm_resp_full_text.split("</think>")[1].strip()
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
            return response
    
    @deprecated(version="1.0", reason="此流式对话方法已废弃, 请使用 chat_sse 或 chat_sse_raw 方法")
    async def stream_chat(self, query: str, inputs: dict={}, is_split_think: bool=True) -> DifyClientResp:
        """流式对话"""
        logger.info(f"start stream chat. query=({query})")
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
    
    def execute_chatflow_block(self, query: str, inputs: dict={}, files: list=[], user_id: str=None) -> DifyClientResp:
        """阻塞模式执行对话流, 提取执行结果"""
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
            response = self.__sync_request(url=url, method="POST", headers=headers, json=payload)
        except httpx.HTTPStatusError as e:
            logger.error(f"execute chatflow failed. error: {str(e)} dify_response: {e.response.text if hasattr(e, 'response') else 'N/A'}")
            return DifyClientResp.error(msg=str(e))
        
        return DifyClientResp.success(data=response.json())
    
    async def execute_workflow(self, inputs: dict={}, is_stream=False) -> DifyClientResp:
        """执行工作流, 提取执行结果. 目前只支持接收blocking模式的结果. 实测在workflow下, 流式请求的结果也仅存在于【workflow_finished】节点中, 不是像chatflow一样的真流式."""
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
        except httpx.HTTPStatusError as e:
            logger.error(f"execute workflow failed. error: {str(e)}")
            return DifyClientResp.error(msg=str(e))
        
        data = response.json()["data"]

        if data["status"] == "succeeded":
            return DifyClientResp.success(data=data["outputs"])
        else:
            return DifyClientResp.error(msg=data["error"])
    
    def get_history_messages_by_cid(self, conversation_id: str) -> DifyClientResp:
        """通过会话id获取历史消息"""
        logger.info(f"start get history messages by cid. conversation_id=({conversation_id})")
        url = f"{self._base_url}/messages?user={self._dify_user_id}&conversation_id={conversation_id}"
        headers = {
            "Authorization": f"Bearer {self._dify_api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = self.__sync_request(url=url, method="GET", headers=headers)
        except httpx.HTTPStatusError as e:
            logger.error(f"get history messages by cid failed. error: {str(e)}")
            return DifyClientResp.error(msg=str(e))
        
        return DifyClientResp.success(data=response.json(), conv_id=conversation_id)
    
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
            logger.info(f"stop task resp: {resp}")
        except httpx.HTTPStatusError as e:
            logger.error(f"stop current task failed. error: {str(e)}")
            return DifyClientResp.error(msg=str(e))
        logger.info(f"stop current task. workflow_name=({self.workflow_name}) task_id=({self._dify_task_id})")
        return DifyClientResp.success(data="")
   
    async def upload_file_to_dify(self, file_path: str) -> DifyClientResp:
        logger.info(f"start upload file to dify. file_path=({file_path})")
        if not file_path.endswith(".docx"):
            raise RuntimeError("file must be .docx format")

        url = f"{self._base_url}/files/upload"
        headers = {
            "Authorization": f"Bearer {self._dify_api_key}",
        }
        data = {
            "user": self._dify_user_id,
        }

        file = {
            # .docx格式必须指定MIME类型
            "file": (os.path.basename(file_path),
                     open(file_path, "rb"),
                     "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        }

        try:
            response = await self.__async_request(url=url, method="POST", headers=headers, data=data, files=file)
        except httpx.HTTPStatusError as e:
            logger.error(f"upload file to dify failed. error: {str(e)}")
            return DifyClientResp.error(msg=str(e))

        return DifyClientResp.success(data=response.json())


    async def upload_file(self, file_path: str, user: Optional[str] = None) -> Dict[str, Any]:
        """
        通用文件上传接口,支持多种文件格式

        Args:
            file_path: 文件路径
            user: 用户标识,如不传则使用初始化时的user_id

        Returns:
            上传成功后返回的文件信息字典,包含:
            - id: 文件ID
            - name: 文件名
            - size: 文件大小(bytes)
            - extension: 文件扩展名
            - mime_type: 文件MIME类型
            - created_by: 上传者ID
            - created_at: 上传时间

        Raises:
            httpx.HTTPStatusError: HTTP请求失败
            FileNotFoundError: 文件不存在
            ValueError: 不支持的文件类型
        """
        logger.info(f"start upload file. file_path=({file_path})")

        # 检查文件是否存在
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

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
                return result

            except httpx.HTTPStatusError as e:
                logger.error(f"upload file failed. error: {str(e)} response: {e.response.text if hasattr(e, 'response') else 'N/A'}")
                raise


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
                    yield f"err: {json.dumps({'error': 'Dify返回错误'})}\n\n"
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
                            yield f"err: {json.dumps({'error': str(e)})}\n\n"
                            return 
    
    
    async def chat_sse_raw(self, stop_flag: asyncio.Event, query: str, inputs: dict={}, files: list=[]) -> AsyncGenerator[str, None]:
        """流式透传数据块, 不做任何额外处理"""
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
        
        async with httpx.AsyncClient(timeout=self.async_req_timeout) as client:
            async with client.stream("POST", url=url, headers=headers, json=payload) as resp:
                if resp.status_code != 200:
                    logger.error(f"error raw stream. status_code=({resp.status_code})")
                    yield f"err: {json.dumps({'error': 'Dify返回错误, dify resp=({})'.format(resp)})}\n\n"
                    return 
                
                async for line in resp.aiter_lines():
                    if stop_flag.is_set():
                        logger.info(f"stop raw chat sse. workflow_name=({self.workflow_name})")
                        await resp.aclose()
                        return 
                    # 直接返回原始行，不做任何处理
                    yield f"{line}\n"