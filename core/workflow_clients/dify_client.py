'''
Description: 通用dify http client, 封装dify的后台api接口
Author: zyq
Date: 2025-07-29 17:51:12
LastEditors: zyq
LastEditTime: 2025-11-19 10:14:48
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

from .base_workflow import BaseWorkflowClient, WorkflowType, WorkflowResponse
from ..exceptions import WorkflowException

# 保持向后兼容的响应模型
class DifyClientResp(WorkflowResponse):
    pass

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
        
        logger.info(f"dify client init success. workflow_name=({self.workflow_name}) url=({self._base_url})")
    
    @staticmethod
    def _format_sse_error(message: str) -> str:
        """构造符合SSE规范的错误事件数据"""
        return f"event: error\ndata: {json.dumps({'error': message})}\n\n"

# ====================chatflow相关接口能力====================
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
            response = await self._async_request(url=url, method="POST", headers=headers, data=payload)
            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"execute chatflow failed. HTTP error: {str(e)} dify_response: {e.response.text if hasattr(e, 'response') else 'N/A'}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"execute chatflow failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务, 请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"execute chatflow failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"execute chatflow failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"execute chatflow failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="执行对话流失败, 请稍后重试")
        
        return DifyClientResp.success(data=body)
    
    async def get_chatflow_conversation_history(self, conversation_id: str, user: str = None) -> DifyClientResp:
        """获取会话历史记录

        Args:
            conversation_id: 会话ID
            user: 用户标识, 如不传则使用初始化时的user_id

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
            response = await self._async_request(url=url, method="GET", headers=headers, params=params)
            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"get conversation history failed. HTTP error: {str(e.response.text)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"get conversation history failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务, 请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"get conversation history failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"get conversation history failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"get conversation history failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="获取会话历史失败, 请稍后重试")

        return DifyClientResp.success(data=body, conv_id=conversation_id)

    async def get_chatflow_conversation_list(self, user: Optional[str] = None, last_id: Optional[str] = None, limit: int = 20) -> DifyClientResp:
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
            response = await self._async_request(url=url, method="GET", headers=headers, params=params)
            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"get conversations failed. HTTP error: {str(e)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"get conversations failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务, 请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"get conversations failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"get conversations failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"get conversations failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="获取会话列表失败, 请稍后重试")

        return DifyClientResp.success(data=body)
    
    async def stop_chatflow_task(self, task_id: str="") ->DifyClientResp:
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
            resp = await self._async_request(url=url, method="POST", headers=headers,data=data)
            logger.info(f"stop task resp: {resp.json()}")
        except httpx.HTTPStatusError as e:
            logger.error(f"stop current task failed. HTTP error: {str(e)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"stop current task failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务, 请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"stop current task failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except Exception as e:
            logger.error(f"stop current task failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="停止任务失败, 请稍后重试")
        logger.info(f"stop current task. workflow_name=({self.workflow_name}) task_id=({self._dify_task_id})")
        return DifyClientResp.success(data="")

    async def delete_chatflow_conversation(self, conversation_id: str, user: Optional[str] = None) -> DifyClientResp:
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
            response = await self._async_request(url=url, method="DELETE", headers=headers, data=payload)

            # 对于204 NO CONTENT响应, 直接返回成功
            if response.status_code == 204:
                logger.info(f"delete conversation success. conversation_id=({conversation_id})")
                return DifyClientResp.success(data={"message": "会话删除成功"})

            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"delete conversation failed. HTTP error: {str(e)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"delete conversation failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务, 请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"delete conversation failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"delete conversation failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"delete conversation failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="删除会话失败, 请稍后重试")

        return DifyClientResp.success(data=body)

    async def rename_chatflow_conversation(
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
            response = await self._async_request(url=url, method="POST", headers=headers, data=payload)
            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"rename conversation failed. HTTP error: {str(e)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"rename conversation failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务, 请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"rename conversation failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"rename conversation failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"rename conversation failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="重命名会话失败, 请稍后重试")

        return DifyClientResp.success(data=body)
   
    async def _upload_dify_file(self, file_path: str, user: Optional[str] = None) -> DifyClientResp:
        """
        上传文件到Dify平台（通用接口，支持chatflow和workflow）

        Args:
            file_path: 文件路径
            user: 用户标识,如不传则使用初始化时的user_id

        Returns:
            DifyClientResp: 上传结果, 成功时data包含文件信息字典, 包含:
            - id: 文件ID
            - name: 文件名
            - size: 文件大小(bytes)
            - extension: 文件扩展名
            - mime_type: 文件MIME类型
            - created_by: 上传者ID
            - created_at: 上传时间
        """
        logger.info(f"start upload dify file. file_path=({file_path})")

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
                response = await self._async_request(
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
                return DifyClientResp.error(msg="无法连接到Dify服务, 请检查网络连接或服务状态")
            except httpx.RequestError as e:
                logger.error(f"upload file failed. Request error: {str(e)}")
                return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
            except ValueError as e:
                logger.error(f"upload file failed. invalid json resp: {str(e)}")
                return DifyClientResp.error(msg="Dify响应格式错误")
            except Exception as e:
                logger.error(f"upload dify file failed. unexpected error: {str(e)}")
                return DifyClientResp.error(msg="文件上传失败, 请稍后重试")

    # 为了保持向后兼容性，提供便捷的wrapper方法
    async def upload_chatflow_file(self, file_path: str, user: Optional[str] = None) -> DifyClientResp:
        """上传chatflow文件 - 调用通用上传接口"""
        return await self._upload_dify_file(file_path=file_path, user=user)

    async def upload_workflow_file(self, file_path: str, user: Optional[str] = None) -> DifyClientResp:
        """上传workflow文件 - 调用通用上传接口"""
        return await self._upload_dify_file(file_path=file_path, user=user)
    
    async def __request_sse_raw(self, stop_flag: asyncio.Event, url: str, headers: Dict[str, Any]=None, payload: Dict[str, Any]=None) -> AsyncGenerator[str, None]:
        logger.info(f"start sse. workflow_name=({self.workflow_name}) url=({url}) payload=({payload})")
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
                        # 直接返回原始行, 不做任何处理
                        yield f"{line}\n"

        except httpx.HTTPError as e:
            logger.error(f"chat_sse_raw HTTP error: {str(e)}")
            yield self._format_sse_error(f"网络请求错误: {str(e)}")
        except Exception as e:
            logger.error(f"chat_sse_raw unexpected error: {str(e)}")
            yield self._format_sse_error(f"系统错误: {str(e)}")

    async def chatflow_sse_raw(self, stop_flag: asyncio.Event, query: str, inputs: Optional[Dict[str, Any]]=None, files: Optional[List[Any]]=None) -> AsyncGenerator[str, None]:
        """chatflow流式透传数据块, 不做任何额外处理"""
        inputs = inputs or {}
        files = files or []
        logger.info(f"start chatflow sse stream. query=({query}) inputs=({inputs}) files=({files})")
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
        
        async for line in self.__request_sse_raw(stop_flag=stop_flag, url=url, headers=headers, payload=payload):
            yield line

    async def workflow_sse_raw(self, stop_flag: asyncio.Event, inputs: Optional[Dict[str, Any]]=None, files: Optional[List[Any]]=None) -> AsyncGenerator[str, None]:
        """workflow流式透传数据块, 不做任何额外处理"""
        inputs = inputs or {}
        logger.info(f"start workflow sse stream. inputs=({inputs})")

        url = f"{self._base_url}/workflows/run"
            
        headers = {
            "Authorization": f"Bearer {self._dify_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "response_mode": "streaming",
            "user": self._dify_user_id,
            "inputs": inputs,
            "files": files,
        }

        async for line in self.__request_sse_raw(stop_flag=stop_flag, url=url, headers=headers, payload=payload):
            yield line


    async def chatflow_message_feedback(self, message_id: str, rating: str, user: str, content: str = "") -> DifyClientResp:
        """消息反馈（点赞）接口

        Args:
            message_id: 消息ID
            rating: 评分, 如"like"或"dislike"
            user: 用户标识
            content: 反馈内容, 可选

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
            response = await self._async_request(url=url, method="POST", headers=headers, data=payload)
            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"message feedback failed. HTTP error: {str(e)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"message feedback failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务, 请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"message feedback failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"message feedback failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"message feedback failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="消息反馈失败, 请稍后重试")

        return DifyClientResp.success(data=body)

    async def get_chatflow_app_feedbacks(self, page: int = 1, limit: int = 20) -> DifyClientResp:
        """获取chatflow APP的消息点赞和反馈

        Args:
            page: 页码, 默认为1
            limit: 每页数量, 默认为20

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
            response = await self._async_request(url=url, method="GET", headers=headers, params=params)
            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"get app feedbacks failed. HTTP error: {str(e)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"get app feedbacks failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务, 请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"get app feedbacks failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"get app feedbacks failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"get app feedbacks failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="获取反馈失败, 请稍后重试")

        return DifyClientResp.success(data=body)

    async def get_chatflow_suggested_questions(self, message_id: str, user: str) -> DifyClientResp:
        """chatflow获取下一轮建议问题列表

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
            response = await self._async_request(url=url, method="GET", headers=headers, params=params)
            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"get suggested questions failed. HTTP error: {str(e.response.text)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"get suggested questions failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务, 请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"get suggested questions failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"get suggested questions failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"get suggested questions failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="获取建议问题失败, 请稍后重试")

        return DifyClientResp.success(data=body)

# ====================chatflow相关接口能力====================




# ====================workflow相关接口能力====================
    async def execute_workflow_block(self, inputs: Optional[Dict[str, Any]]=None, files: Optional[List[Any]]=None) -> DifyClientResp:
        """
        阻塞模式执行工作流, 提取执行结果.
        """
        inputs = inputs or {}
        files = files or []
        logger.info(f"start execute workflow. workflow_name=({self.workflow_name}) inputs=({inputs})")
        
        url = f"{self._base_url}/workflows/run"
        headers = {
            'Authorization': f"Bearer {self._dify_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "response_mode": "blocking",
            "user": self._dify_user_id,
            "inputs": inputs,
            "files": files,
        }
        
        try:
            response = await self._async_request(url=url, headers=headers, data=payload)
            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"execute workflow failed. HTTP error: {str(e)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"execute workflow failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务, 请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"execute workflow failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"execute workflow failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"execute workflow failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="执行工作流失败, 请稍后重试")
        
        data = body.get("data")
        if not isinstance(data, dict):
            logger.error(f"execute workflow failed. invalid resp body: {body}")
            return DifyClientResp.error(msg="workflow response malformed")

        if data.get("status") == "succeeded":
            return DifyClientResp.success(data=body)

        error_msg = data.get("error") or body.get("message") or "workflow run failed"
        return DifyClientResp.error(msg=error_msg)

    async def get_workflow_run_status(self, workflow_run_id: str) -> DifyClientResp:
        """
        获取workflow执行情况

        Args:
            workflow_run_id: 工作流执行ID

        Returns:
            DifyClientResp: 包含工作流执行信息的响应结果
        """
        logger.info(f"start get workflow run status. workflow_run_id=({workflow_run_id})")
        url = f"{self._base_url}/workflows/run/{workflow_run_id}"
        headers = {
            "Authorization": f"Bearer {self._dify_api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = await self._async_request(url=url, method="GET", headers=headers)
            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"get workflow run status failed. HTTP error: {str(e)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"get workflow run status failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务, 请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"get workflow run status failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"get workflow run status failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"get workflow run status failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="获取workflow执行情况失败, 请稍后重试")

        return DifyClientResp.success(data=body)

    async def stop_workflow_task(self, task_id: str) -> DifyClientResp:
        """
        停止workflow任务

        Args:
            task_id: 任务ID

        Returns:
            DifyClientResp: 包含停止结果的响应
        """
        logger.info(f"start stop workflow task. task_id=({task_id})")
        url = f"{self._base_url}/workflows/tasks/{task_id}/stop"
        headers = {
            "Authorization": f"Bearer {self._dify_api_key}",
            "Content-Type": "application/json",
        }

        data = {
            "user": self._dify_user_id,
        }

        try:
            response = await self._async_request(url=url, method="POST", headers=headers, data=data)
            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"stop workflow task failed. HTTP error: {str(e)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"stop workflow task failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务, 请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"stop workflow task failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"stop workflow task failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"stop workflow task failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="停止workflow任务失败, 请稍后重试")

        return DifyClientResp.success(data=body)

    async def get_workflow_logs(self, keyword: Optional[str] = None, status: Optional[str] = None,
                               page: int = 1, limit: int = 20,
                               created_by_end_user_session_id: Optional[str] = None,
                               created_by_account: Optional[str] = None) -> DifyClientResp:
        """
        获取workflow日志

        Args:
            keyword: 关键字
            status: 执行状态 succeeded/failed/stopped
            page: 当前页码, 默认1
            limit: 每页条数, 默认20
            created_by_end_user_session_id: 由哪个endUser创建
            created_by_account: 由哪个邮箱账户创建

        Returns:
            DifyClientResp: 包含workflow日志列表的响应结果
        """
        logger.info(f"start get workflow logs. keyword=({keyword}) status=({status}) page=({page}) limit=({limit})")
        url = f"{self._base_url}/workflows/logs"
        headers = {
            "Authorization": f"Bearer {self._dify_api_key}",
            "Content-Type": "application/json",
        }

        params = {
            "page": page,
            "limit": limit,
        }

        # 添加可选参数
        if keyword:
            params["keyword"] = keyword
        if status:
            params["status"] = status
        if created_by_end_user_session_id:
            params["created_by_end_user_session_id"] = created_by_end_user_session_id
        if created_by_account:
            params["created_by_account"] = created_by_account

        try:
            response = await self._async_request(url=url, method="GET", headers=headers, params=params)
            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"get workflow logs failed. HTTP error: {str(e)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"get workflow logs failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务, 请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"get workflow logs failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"get workflow logs failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"get workflow logs failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="获取workflow日志失败, 请稍后重试")

        return DifyClientResp.success(data=body)

    async def get_app_info(self) -> DifyClientResp:
        """
        获取应用基本信息

        Returns:
            DifyClientResp: 包含应用基本信息的响应结果
        """
        logger.info(f"start get app info. workflow_name=({self.workflow_name})")
        url = f"{self._base_url}/info"
        headers = {
            "Authorization": f"Bearer {self._dify_api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = await self._async_request(url=url, method="GET", headers=headers)
            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"get app info failed. HTTP error: {str(e)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"get app info failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务, 请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"get app info failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"get app info failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"get app info failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="获取应用基本信息失败, 请稍后重试")

        return DifyClientResp.success(data=body)

    async def get_app_site(self) -> DifyClientResp:
        """
        获取应用WebApp设置

        Returns:
            DifyClientResp: 包含应用WebApp设置的响应结果
        """
        logger.info(f"start get app site. workflow_name=({self.workflow_name})")
        url = f"{self._base_url}/site"
        headers = {
            "Authorization": f"Bearer {self._dify_api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = await self._async_request(url=url, method="GET", headers=headers)
            body = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"get app site failed. HTTP error: {str(e)}")
            return DifyClientResp.error(msg=f"Dify服务HTTP错误: status_code=({e.response.status_code}) content=({e.response.text})")
        except httpx.ConnectError as e:
            logger.error(f"get app site failed. Connection error: {str(e)}")
            return DifyClientResp.error(msg="无法连接到Dify服务, 请检查网络连接或服务状态")
        except httpx.RequestError as e:
            logger.error(f"get app site failed. Request error: {str(e)}")
            return DifyClientResp.error(msg=f"网络请求错误: {str(e)}")
        except ValueError as e:
            logger.error(f"get app site failed. invalid json resp: {str(e)}")
            return DifyClientResp.error(msg="Dify响应格式错误")
        except Exception as e:
            logger.error(f"get app site failed. unexpected error: {str(e)}")
            return DifyClientResp.error(msg="获取应用WebApp设置失败, 请稍后重试")

        return DifyClientResp.success(data=body)
# ====================workflow相关接口能力====================