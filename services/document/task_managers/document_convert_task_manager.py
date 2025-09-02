'''
Description: 文档格式转换任务管理器, 负责文档格式转换任务的管理和执行
Author: zyq
Date: 2025-09-01 10:33:38
LastEditors: zyq
LastEditTime: 2025-09-02 10:32:29
'''

import base64
import tempfile
import os
from typing import Dict, Any
from datetime import datetime
from loguru import logger

from core.tasks import (
    BaseTaskManager, TaskType, TaskStatus, BaseTask, 
    generate_task_id
)
from core.tasks.registry import task_registry, collection_registry
from core.schemas.file_models import FileInfo
from ..schemas import (
    DocumentConvertRequest, DocumentConvertResponse,
    ConvertTaskStatusResponse, DocumentTaskTypePrefix,
)


class DocumentConvertTaskManager(BaseTaskManager):
    """文档格式转换任务管理器"""
    
    def __init__(self, queue_backend, storage_backend, config: Dict[str, Any] = None):
        """
        初始化文档转换任务管理器
        
        Args:
            queue_backend: 队列后端
            storage_backend: 存储后端
            config: 配置参数
        """
        super().__init__(queue_backend, storage_backend, config)
        
        # 注册任务函数到全局注册表
        task_registry.register('_process_document_convert', self._process_document_convert)
        self.task_id_prefix = DocumentTaskTypePrefix.CONVERT_TASK.value
        
        # 注册collection映射和task_id前缀到全局注册表
        collection_registry.register(
            'document_convert_processing', 
            'document_convert_tasks',
            self.task_id_prefix  # 约束task_id前缀
        )
    
    def get_task_type(self) -> TaskType:
        """获取任务类型"""
        return TaskType.SINGLE_PROCESSING
    
    async def create_task_instance(self, **kwargs) -> BaseTask:
        """
        创建文档转换任务实例
        
        Args:
            **kwargs: 任务创建参数
                - request: DocumentConvertRequest
                - temp_file_path: 临时文件路径
                - file_info: 文件信息
                - trace_id: 链路追踪ID
                
        Returns:
            任务实例
        """
        request = kwargs.get('request')
        trace_id = kwargs.get('trace_id')
        
        task_id = generate_task_id(self.task_id_prefix)
        
        task = BaseTask(
            task_id=task_id,
            task_type=TaskType.SINGLE_PROCESSING,
            status=TaskStatus.PENDING,
            timeout=self.config.get('convert_timeout', 600),  # 10分钟超时
            max_retries=self.config.get('convert_max_retries', 2),
            trace_id=trace_id,
            metadata={'collection_type': 'document_convert_processing'}  # 指定collection类型
        )
        
        return task
    
    async def submit_convert_task(
        self, 
        request: DocumentConvertRequest,
        temp_file_path: str,
        file_info: FileInfo,
        trace_id: str = None
    ) -> DocumentConvertResponse:
        """
        提交文档转换任务
        
        Args:
            request: 文档转换请求
            temp_file_path: 临时文件路径
            file_info: 文件信息
            trace_id: 链路追踪ID
            
        Returns:
            文档转换响应
        """
        logger.info(f"Submitting document convert task - TraceID: {trace_id} | {request.source_format} → {request.target_format}")
        
        try:
            # 持久化输入文件到处理目录（避免中间件清理导致文件丢失）
            from ..utils.file_manager import FileManager
            file_manager = FileManager()
            persistent_file_path = await file_manager.persist_input_file(temp_file_path, file_info.filename)
            
            # 统一构建任务参数
            task_params = {
                'request': request.model_dump(),
                'temp_file_path': persistent_file_path,  # 使用持久化后的文件路径
                'file_info': file_info.model_dump(),
                'trace_id': trace_id
            }
            
            # 提交任务到队列（只传递一次参数）
            task_id = await self.submit_task(
                self._process_document_convert,
                task_params
            )
            
            return DocumentConvertResponse(
                convert_task_id=task_id,
                source_format=request.source_format,
                target_format=request.target_format,
                created_at=datetime.now().isoformat()
            )
            
        except Exception as e:
            logger.error(f"Failed to submit document convert task: {str(e)}")
            raise
    
    async def _process_document_convert(
        self,
        request: Dict[str, Any],
        temp_file_path: str,
        file_info: Dict[str, Any],
        trace_id: str = None,
        task_id: str = None
    ) -> Dict[str, Any]:
        """
        处理文档转换任务的核心函数（异步版本）
        
        Args:
            request: 转换请求字典
            temp_file_path: 临时文件路径
            file_info: 文件信息字典
            trace_id: 链路追踪ID
            task_id: 任务ID
            
        Returns:
            处理结果字典
        """
        # 如果没有传递task_id，尝试从ARQ context获取
        if not task_id:
            try:
                from arq.worker import current_ctx
                ctx = current_ctx.get()
                if ctx and hasattr(ctx, 'job_id'):
                    task_id = ctx.job_id
            except:
                pass
        
        logger.info(f"Processing document convert task: {task_id} | {request['source_format']} → {request['target_format']}")
        
        # 更新任务状态为处理中
        if task_id:
            await self.storage_backend.update_task_status(task_id, TaskStatus.PROCESSING)
        
        try:
            # 检查临时文件是否存在
            if not os.path.exists(temp_file_path):
                raise Exception(f"临时文件不存在: {temp_file_path}")
            
            # 重构请求和文件信息对象
            convert_request = DocumentConvertRequest(**request)
            file_info_obj = FileInfo(**file_info)
            
            # 调用转换处理器
            from ..processors.convert_processor import ConvertProcessor
            convert_processor = ConvertProcessor(self.config or {})
            
            # 执行转换（传入task_id确保输出文件路径一致）
            converted_file_path = await convert_processor.process(
                convert_request,
                temp_file_path,
                file_info_obj,
                trace_id,
                task_id
            )
            
            # 构建符合ConvertTaskStatusResponse格式的结果
            result = {
                'convert_task_id': task_id,
                'status': 'completed',
                'download_url': f"/document/convert-download?task_id={task_id}",
                'error_message': None,
                'created_at': datetime.now().isoformat(),
                'completed_at': datetime.now().isoformat(),
                'source_format': request['source_format'],
                'target_format': request['target_format']
            }
            
            # 更新任务状态为完成
            if task_id:
                await self.storage_backend.update_task_status(
                    task_id,
                    TaskStatus.COMPLETED,
                    completed_at=datetime.now(),
                    result=result
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to process document convert task {task_id}: {str(e)}")
            
            # 构建失败结果
            result = {
                'convert_task_id': task_id,
                'status': 'failed',
                'download_url': None,
                'error_message': str(e),
                'created_at': datetime.now().isoformat(),
                'completed_at': datetime.now().isoformat(),
                'source_format': request['source_format'],
                'target_format': request['target_format']
            }
            
            # 更新任务状态为失败
            if task_id:
                await self.storage_backend.update_task_status(
                    task_id,
                    TaskStatus.FAILED,
                    completed_at=datetime.now(),
                    error_message=str(e),
                    result=result
                )
            
            return result
            
        finally:
            # worker执行完成后清理输入的持久化文件
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    from ..utils.file_manager import FileManager
                    file_manager = FileManager()
                    file_manager.cleanup_input_file(temp_file_path)
                except Exception as e:
                    logger.warning(f"Failed to cleanup input file {temp_file_path}: {str(e)}")
    
    async def get_convert_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        获取文档转换任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            符合ConvertTaskStatusResponse格式的任务状态信息
        """
        try:
            # 获取完整任务信息
            task = await self.storage_backend.get_task(task_id)
            if not task:
                return None
            
            # 构建符合ConvertTaskStatusResponse的响应格式
            status_value = task.status.value.lower() if hasattr(task.status, 'value') else str(task.status).lower()
            result = {
                'convert_task_id': task_id,
                'status': status_value,  # pending | processing | completed | failed
                'created_at': task.created_at.isoformat() if task.created_at else datetime.now().isoformat(),
                'completed_at': task.completed_at.isoformat() if task.completed_at else None,
                'download_url': None,
                'error_message': task.error_message,
                'source_format': 'unknown',
                'target_format': 'unknown'
            }
            
            # 从任务结果中提取详细信息
            if hasattr(task, 'result') and task.result and isinstance(task.result, dict):
                result.update({
                    'source_format': task.result.get('source_format', 'unknown'),
                    'target_format': task.result.get('target_format', 'unknown'),
                    'download_url': task.result.get('download_url')
                })
            
            # 如果result中没有download_url但任务已完成，生成默认的download_url
            if result['status'] == 'completed' and not result.get('download_url'):
                result['download_url'] = f"/document/convert-download?task_id={task_id}"
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get document convert task status: {str(e)}")
            return None