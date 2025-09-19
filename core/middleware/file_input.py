'''
Description: 文件输入处理中间件
Author: zyq
Date: 2025-09-02 17:17:17
LastEditors: zyq
LastEditTime: 2025-09-18 11:03:45
'''
import base64
import tempfile
import json
from typing import Dict, Any, Optional
from fastapi import Request, Response, HTTPException, UploadFile
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from loguru import logger

from core.schemas.file_models import FileInfo
from core.schemas.base_resp_model_define import BaseResponse


class FileInputMiddleware(BaseHTTPMiddleware):
    """文件输入处理中间件"""
    
    def __init__(self, app, max_file_size: int = 10 * 1024 * 1024):  # 默认10MB
        super().__init__(app)
        self.max_file_size = max_file_size
        # 需要处理文件的具体路径
        self.file_endpoints = {
            "/document/pdf-parser",
            "/document/convert", 
            "/document/text-extract",
            "/document/table-extract"
        }
    
    async def dispatch(self, request: Request, call_next):
        # 检查是否是需要处理文件的具体接口
        needs_file_processing = request.url.path in self.file_endpoints
        
        if not needs_file_processing:
            return await call_next(request)
        
        trace_id = getattr(request.state, 'trace_id', 'unknown')
        temp_file_path = None
        
        try:
            # 处理文件输入
            temp_file_path, file_info, processed_body = await self._process_file_input(request, trace_id)
            
            # 将处理结果存储到request state中供后续使用
            request.state.temp_file_path = temp_file_path
            request.state.file_info = file_info
            request.state.processed_request_body = processed_body
            
            # 继续处理请求
            response = await call_next(request)
            
            return response
            
        except HTTPException as e:
            # 抛出HTTPException，由全局异常处理器统一处理
            raise e
        except Exception as e:
            logger.error(f"File processing middleware error - TraceID: {trace_id} | Error: {str(e)}")
            # 抛出业务异常，由全局异常处理器统一处理
            from core.exceptions import FileProcessException
            raise FileProcessException("文件处理失败", {"original_error": str(e)})
        finally:
            # 清理临时文件
            if temp_file_path:
                self._cleanup_temp_file(temp_file_path)
    
    async def _process_file_input(self, request: Request, trace_id: str) -> tuple:
        """处理文件输入，返回临时文件路径、文件信息和处理后的请求体"""
        content_type = request.headers.get("content-type", "")
        
        if content_type.startswith("multipart/form-data"):
            return await self._process_multipart_file(request, trace_id)
        elif content_type.startswith("application/json"):
            return await self._process_json_base64(request, trace_id)
        else:
            raise HTTPException(
                status_code=400,
                detail="不支持的Content-Type，请使用multipart/form-data或application/json"
            )
    
    async def _process_multipart_file(self, request: Request, trace_id: str) -> tuple:
        """处理multipart文件上传"""
        try:
            form = await request.form()
            
            # 获取input_type
            input_type = form.get("input_type")
            if input_type != "file":
                raise HTTPException(status_code=400, detail="multipart上传时input_type必须为file")
            
            # 获取上传的文件
            file_field = None
            logger.info(f"Processing multipart form fields - TraceID: {trace_id}")
            for key, value in form.items():
                logger.info(f"Form field: {key} = {type(value)} | TraceID: {trace_id}")
                # 检查是否是UploadFile类型的更详细判断
                if hasattr(value, 'filename') and hasattr(value, 'file'):
                    file_field = value
                    logger.info(f"Found file field: {key} | TraceID: {trace_id}")
                    break
                elif isinstance(value, UploadFile):
                    file_field = value
                    logger.info(f"Found file field (UploadFile): {key} | TraceID: {trace_id}")
                    break
            
            if not file_field:
                logger.error(f"No file field found in form data - TraceID: {trace_id}")
                raise HTTPException(status_code=400, detail="未找到上传的文件")
            
            # 获取文件名
            filename = form.get("filename") or file_field.filename
            if not filename:
                raise HTTPException(status_code=400, detail="文件名不能为空")
            
            # 检查文件大小
            file_content = await file_field.read()
            file_size = len(file_content)
            
            if file_size > self.max_file_size:
                raise HTTPException(
                    status_code=413,
                    detail=f"文件大小超过限制({self.max_file_size / 1024 / 1024}MB)"
                )
            
            # 创建临时文件
            temp_file_path = await self._save_to_temp_file(file_content, filename)
            
            file_info = FileInfo(
                filename=filename,
                file_size=file_size,
                content_type=file_field.content_type,
                input_type="file",
                temp_file_path=temp_file_path
            )
            
            # 构建处理后的请求体
            processed_body = {
                "input_type": "file",
                "filename": filename,
                "file_size": file_size
            }
            
            # 根据不同的接口路径添加特定参数
            if "/pdf-parser" in request.url.path:
                processed_body.update({
                    "output_format": form.get("output_format", "text"),
                    "parser_options": json.loads(form.get("parser_options", "{}"))
                })
            elif "/convert" in request.url.path:
                processed_body.update({
                    "source_format": form.get("source_format", ""),
                    "target_format": form.get("target_format", ""),
                    "convert_options": json.loads(form.get("convert_options", "{}"))
                })
            elif "/text-extract" in request.url.path:
                processed_body.update({
                    "extract_options": json.loads(form.get("extract_options", "{}"))
                })
            elif "/table-extract" in request.url.path:
                processed_body.update({
                    "output_format": body.get("output_format", "html_text")
                })
            
            logger.info(f"Processed multipart file - TraceID: {trace_id} | Filename: {filename} | Size: {file_size}")
            return temp_file_path, file_info, processed_body
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Multipart file processing failed - TraceID: {trace_id} | Error: {str(e)}")
            raise HTTPException(status_code=500, detail="文件处理失败")
    
    async def _process_json_base64(self, request: Request, trace_id: str) -> tuple:
        """处理JSON中的base64文件"""
        try:
            body = await request.json()
            
            # 获取input_type
            input_type = body.get("input_type")
            if input_type != "base64":
                raise HTTPException(status_code=400, detail="JSON请求时input_type必须为base64")
            
            # 获取base64数据
            file_data = body.get("file_data")
            if not file_data:
                raise HTTPException(status_code=400, detail="file_data不能为空")
            
            # 获取文件名
            filename = body.get("filename")
            if not filename:
                raise HTTPException(status_code=400, detail="filename不能为空")
            
            # 解码base64
            try:
                file_content = base64.b64decode(file_data)
            except Exception:
                raise HTTPException(status_code=400, detail="base64解码失败")
            
            # 检查文件大小
            file_size = len(file_content)
            if file_size > self.max_file_size:
                raise HTTPException(
                    status_code=413,
                    detail=f"文件大小超过限制({self.max_file_size / 1024 / 1024}MB)"
                )
            
            # 创建临时文件
            temp_file_path = await self._save_to_temp_file(file_content, filename)
            
            file_info = FileInfo(
                filename=filename,
                file_size=file_size,
                input_type="base64",
                temp_file_path=temp_file_path
            )
            
            # 处理后的请求体（移除file_data字段，避免传输大量数据）
            processed_body = {
                "input_type": "base64",
                "filename": filename,
                "file_size": file_size
            }
            
            # 根据不同的接口路径添加特定参数
            if "/pdf-parser" in request.url.path:
                processed_body.update({
                    "output_format": body.get("output_format", "text"),
                    "parser_options": body.get("parser_options", {})
                })
            elif "/convert" in request.url.path:
                processed_body.update({
                    "source_format": body.get("source_format", ""),
                    "target_format": body.get("target_format", ""),
                    "convert_options": body.get("convert_options", {})
                })
            elif "/text-extract" in request.url.path:
                processed_body.update({
                    "extract_options": body.get("extract_options", {})
                })
            elif "/table-extract" in request.url.path:
                processed_body.update({
                    "output_format": body.get("output_format", "html_text")
                })
            
            logger.info(f"Processed base64 file - TraceID: {trace_id} | Filename: {filename} | Size: {file_size}")
            return temp_file_path, file_info, processed_body
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Base64 file processing failed - TraceID: {trace_id} | Error: {str(e)}")
            raise HTTPException(status_code=500, detail="文件处理失败")
    
    async def _save_to_temp_file(self, file_content: bytes, filename: str) -> str:
        """保存文件内容到临时文件"""
        try:
            # 获取文件扩展名
            file_ext = ""
            if "." in filename:
                file_ext = "." + filename.split(".")[-1]
            
            # 创建临时文件
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_ext)
            temp_file.write(file_content)
            temp_file.close()
            
            return temp_file.name
            
        except Exception as e:
            logger.error(f"Failed to save temp file: {str(e)}")
            raise HTTPException(status_code=500, detail="临时文件创建失败")
    
    def _cleanup_temp_file(self, temp_file_path: str):
        """清理临时文件"""
        try:
            import os
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
                logger.info(f"Cleaned up temp file: {temp_file_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup temp file {temp_file_path}: {str(e)}")