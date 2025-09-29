'''
Description: 文本提取批处理任务管理器
Author: zyq
Date: 2025-09-02
'''

import base64
import tempfile
import os
from typing import Dict, Any, List
from datetime import datetime
from loguru import logger

from core.tasks.base import QueueBackend, StorageBackend, BaseTaskManager
from core.tasks.models.task_models import TaskStatus, TaskType, BatchTask
from core.tasks.registry import task_registry, collection_registry
from core.tasks import generate_task_id
from core.schemas.file_models import FileInfo
from ..schemas import (
    TextExtractBatchRequest, TextExtractBatchResponse,
    ExtractTaskStatusResponse, FileExtractTask, FileExtractStatus,
    DocumentTaskTypePrefix
)
from ..processors.text_processor import TextProcessor


class TextExtractBatchTaskManager(BaseTaskManager):
    """文本提取批处理任务管理器"""
    
    def __init__(self, queue_backend: QueueBackend, storage_backend: StorageBackend, config: Dict[str, Any]):
        super().__init__(queue_backend, storage_backend, config)
        self.text_processor = TextProcessor(config)
        self.task_id_prefix = DocumentTaskTypePrefix.TEXT_EXTRACT_BATCH_TASK.value
        
        # 注册任务函数到全局注册表
        task_registry.register('_process_text_extract_batch', self._process_text_extract_batch)
        
        # 注册collection映射
        collection_registry.register(
            'text_extract_batch_processing',
            'text_extract_batch_tasks',
            DocumentTaskTypePrefix.TEXT_EXTRACT_BATCH_TASK.value
        )
        
    def get_task_type(self) -> TaskType:
        """获取任务类型"""
        return TaskType.BATCH_PROCESSING
    
    async def create_task_instance(self, **kwargs) -> BatchTask:
        """创建文本提取批处理任务实例"""
        files = kwargs.get('files', [])
        trace_id = kwargs.get('trace_id')
        
        task_id = generate_task_id(self.task_id_prefix)
        
        task = BatchTask(
            task_id=task_id,
            task_type=TaskType.BATCH_PROCESSING,
            status=TaskStatus.PENDING,
            total_items=len(files),
            processed_items=0,
            successful_items=0,
            failed_items=0,
            timeout=self.config.get('text_extract_batch_timeout', 3600),
            max_retries=self.config.get('text_extract_batch_max_retries', 3),
            trace_id=trace_id,
            metadata={'collection_type': 'text_extract_batch_processing'}
        )
        
        return task
    
    async def submit_text_extract_batch_task(self, request: TextExtractBatchRequest, trace_id: str = None) -> TextExtractBatchResponse:
        """提交文本提取批处理任务"""
        logger.info(f"Submitting text extract batch task - TraceID: {trace_id} | Files: {len(request.files)}")
        
        try:
            # 验证文件数量
            if len(request.files) > 10:
                raise ValueError("文件数量不能超过10个")
            
            # 验证文件格式
            for file_item in request.files:
                if not file_item.filename.lower().endswith('.docx'):
                    raise ValueError(f"仅支持DOCX格式文件,不支持: {file_item.filename}")
            
            # 统一构建任务参数
            task_params = {
                'files': request.files,
                'extract_options': request.extract_options,
                'trace_id': trace_id
            }
            
            # 提交任务到队列
            task_id = await self.submit_task(
                self._process_text_extract_batch,
                task_params
            )
            
            return TextExtractBatchResponse(
                text_extract_batch_task_id=task_id,
                total_files=len(request.files),
                created_at=datetime.now().isoformat()
            )
            
        except Exception as e:
            logger.error(f"Failed to submit text extract batch task: {str(e)}")
            raise
    
    async def get_extract_batch_task_status(self, batch_task_id: str) -> Dict[str, Any]:
        """获取文本提取批处理任务状态"""
        try:
            task = await self.storage_backend.get_task(batch_task_id)
            
            if not task:
                logger.warning(f"文本提取批处理任务不存在 - TaskID: {batch_task_id}")
                return None
            
            # 构建符合响应格式的状态信息
            status_value = task.status.value.lower() if hasattr(task.status, 'value') else str(task.status).lower()
            
            # 将子任务结果转换为 FileExtractTask 格式
            results = None
            if hasattr(task, 'sub_results') and task.sub_results:
                results = []
                for sub_result in task.sub_results:
                    # sub_result.result 包含 FileExtractTask 的 model_dump() 数据
                    if sub_result.result:
                        file_extract_task = FileExtractTask(**sub_result.result)
                        results.append(file_extract_task)
            
            task_status = {
                'text_extract_batch_task_id': batch_task_id,
                'status': status_value,
                'results': results,
                'total_files': getattr(task, 'total_items', 0),
                'completed_files': getattr(task, 'processed_items', 0),
                'successful_files': getattr(task, 'successful_items', 0),
                'failed_files': getattr(task, 'failed_items', 0),
                'created_at': task.created_at.isoformat() if task.created_at else None,
                'completed_at': task.completed_at.isoformat() if task.completed_at else None,
                'error_message': getattr(task, 'error_message', None)
            }
            
            logger.info(f"获取文本提取批处理任务状态 - TaskID: {batch_task_id} | Status: {status_value}")
            return task_status
            
        except Exception as e:
            logger.error(f"获取文本提取批处理任务状态失败 - TaskID: {batch_task_id} | Error: {str(e)}")
            raise RuntimeError(f"查询任务状态失败: {str(e)}")
    
    async def _process_text_extract_batch(
        self,
        files: List[Any],
        extract_options: Dict[str, Any],
        trace_id: str = None,
        task_id: str = None
    ):
        """处理文本提取批处理任务（Worker调用）"""
        # 如果没有传递task_id，尝试从ARQ context获取
        if not task_id:
            try:
                from arq.worker import current_ctx
                ctx = current_ctx.get()
                if ctx and hasattr(ctx, 'job_id'):
                    task_id = ctx.job_id
            except:
                pass
        
        logger.info(f"Processing text extract batch task: {task_id} | Files: {len(files)}")
        
        try:
            # 更新任务状态为处理中
            if task_id:
                await self.storage_backend.update_task_status(task_id, TaskStatus.PROCESSING)
            
            results = []
            completed_count = 0
            
            # 逐个处理文件
            for file_item in files:
                try:
                    # 处理单个文件
                    result = await self._process_single_file(file_item, extract_options, trace_id)
                    results.append(result)
                    completed_count += 1
                    
                    # 将结果存储为子任务结果
                    if task_id:
                        sub_task_status = TaskStatus.COMPLETED if result.status == FileExtractStatus.SUCCESS else TaskStatus.FAILED
                        await self.storage_backend.add_sub_task_result(
                            task_id=task_id,
                            sub_task_id=result.extract_task_id,
                            status=sub_task_status,
                            result=result.model_dump(),
                            error_message=None if result.status == FileExtractStatus.SUCCESS else "文件处理失败"
                        )
                    
                    # 更新进度
                    if task_id:
                        await self.storage_backend.update_task_progress(
                            task_id,
                            processed_items=completed_count,
                            successful_items=sum(1 for r in results if r.status == FileExtractStatus.SUCCESS),
                            failed_items=sum(1 for r in results if r.status == FileExtractStatus.FAILED)
                        )
                    
                except Exception as e:
                    logger.error(f"文件处理失败 - File: {file_item.filename} | Error: {str(e)}")
                    # 添加失败结果
                    error_result = FileExtractTask(
                        extract_task_id=f"{task_id}_{file_item.filename}",
                        filename=file_item.filename,
                        status=FileExtractStatus.FAILED,
                        text_content="",
                        word_count=0
                    )
                    results.append(error_result)
                    completed_count += 1
                    
                    # 将失败结果存储为子任务结果
                    if task_id:
                        await self.storage_backend.add_sub_task_result(
                            task_id=task_id,
                            sub_task_id=error_result.extract_task_id,
                            status=TaskStatus.FAILED,
                            result=error_result.model_dump(),
                            error_message=str(e)
                        )
                    
                    # 更新进度
                    if task_id:
                        await self.storage_backend.update_task_progress(
                            task_id,
                            processed_items=completed_count,
                            successful_items=sum(1 for r in results if r.status == FileExtractStatus.SUCCESS),
                            failed_items=sum(1 for r in results if r.status == FileExtractStatus.FAILED)
                        )
            
            # 更新最终状态
            successful_count = sum(1 for r in results if r.status == FileExtractStatus.SUCCESS)
            failed_count = sum(1 for r in results if r.status == FileExtractStatus.FAILED)
            
            final_status = TaskStatus.COMPLETED if failed_count == 0 else TaskStatus.FAILED
            
            # 如果有失败的文件，添加错误信息
            error_message = None
            if failed_count > 0:
                failed_files = [r.filename for r in results if r.status == FileExtractStatus.FAILED]
                error_message = f"批处理失败: {failed_count}/{len(files)} 个文件处理失败，失败文件: {', '.join(failed_files[:5])}"
                if len(failed_files) > 5:
                    error_message += f" 等{len(failed_files)}个文件"
            
            if task_id:
                await self.storage_backend.update_task_status(
                    task_id,
                    final_status,
                    completed_at=datetime.now(),
                    error_message=error_message
                )
                
                await self.storage_backend.update_task_progress(
                    task_id,
                    processed_items=len(files),
                    successful_items=successful_count,
                    failed_items=failed_count
                )
            
            logger.info(f"Text extract batch task completed: {task_id} | Success: {successful_count} | Failed: {failed_count}")
            
        except Exception as e:
            logger.error(f"Failed to process text extract batch task: {task_id} | Error: {str(e)}")
            if task_id:
                await self.storage_backend.update_task_status(
                    task_id,
                    TaskStatus.FAILED,
                    completed_at=datetime.now(),
                    error_message=str(e)
                )
            raise e
    
    async def _process_single_file(self, file_item: Any, extract_options: Dict[str, Any], trace_id: str) -> FileExtractTask:
        """处理单个文件的文本提取"""
        filename = file_item.filename
        input_type = getattr(file_item, 'input_type', 'base64')
        
        temp_file_path = None
        should_cleanup_temp_file = False
        
        try:
            # 根据input_type选择处理方式
            if input_type == "file" and hasattr(file_item, 'temp_file_path'):
                # multipart上传，直接使用已有的临时文件
                temp_file_path = file_item.temp_file_path
                if not os.path.exists(temp_file_path):
                    raise Exception(f"临时文件不存在: {temp_file_path}")
                with open(temp_file_path, 'rb') as f:
                    file_bytes = f.read()
            else:
                # base64方式，需要解码并创建临时文件
                file_data = file_item.file_data
                file_bytes = base64.b64decode(file_data)
                
                # 创建临时文件
                with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as temp_file:
                    temp_file.write(file_bytes)
                    temp_file_path = temp_file.name
                should_cleanup_temp_file = True
            
            # 验证临时文件是否正确创建
            if not os.path.exists(temp_file_path):
                raise Exception(f"临时文件创建失败: {temp_file_path}")
            
            logger.debug(f"临时文件创建成功: {temp_file_path} | Size: {os.path.getsize(temp_file_path)}")
            
            try:
                # 创建文件信息对象
                file_info = FileInfo(
                    filename=filename,
                    content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    file_size=len(file_bytes),
                    input_type=input_type,
                    temp_file_path=temp_file_path
                )
                
                # 创建文本提取请求
                from ..schemas import TextExtractRequest
                text_request = TextExtractRequest(
                    input_type=input_type,
                    file_data=file_item.file_data if input_type == 'base64' else "",
                    filename=filename,
                    extract_options=extract_options
                )
                
                # 调用文本处理器
                response = await self.text_processor.process(text_request, temp_file_path, file_info, trace_id)
                
                # 构建成功结果
                return FileExtractTask(
                    extract_task_id=f"{filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    filename=filename,
                    status=FileExtractStatus.SUCCESS,
                    text_content=response.text_content,
                    word_count=response.word_count
                )
                
            finally:
                # 清理临时文件（只清理我们自己创建的临时文件）
                if should_cleanup_temp_file and temp_file_path and os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                    
        except Exception as e:
            logger.error(f"单文件文本提取失败 - File: {filename} | Error: {str(e)}")
            return FileExtractTask(
                extract_task_id=f"{filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                filename=filename,
                status=FileExtractStatus.FAILED,
                text_content="",
                word_count=0
            )
    
    
