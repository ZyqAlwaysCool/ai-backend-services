'''
Description: PDF批处理任务管理器, 负责PDF批量解析任务的管理和执行
Author: zyq
Date: 2025-08-28 11:14:11
LastEditors: zyq
LastEditTime: 2025-08-29 17:08:19
'''
import base64
import tempfile
import os
from typing import Dict, Any, List
from datetime import datetime
from loguru import logger

from core.tasks import (
    BaseTaskManager, TaskType, TaskStatus, BatchTask, 
    generate_task_id, SubTaskResult
)
from core.tasks.registry import task_registry, collection_registry
from core.schemas.file_models import FileInfo
from ..schemas import (
    PDFParserBatchRequest, PDFParserBatchResponse, 
    PDFFileItem, PDFParserRequest, PDFParserResponse,
    PDFParserTask, PDFParserTaskStatus
)
from ..processors.pdf_processor import PDFProcessor


class PDFBatchTaskManager(BaseTaskManager):
    """PDF批处理任务管理器"""
    
    def __init__(self, queue_backend, storage_backend, config: Dict[str, Any] = None):
        """
        初始化PDF批处理任务管理器
        
        Args:
            queue_backend: 队列后端
            storage_backend: 存储后端
            config: 配置参数
        """
        super().__init__(queue_backend, storage_backend, config)
        self.pdf_processor = PDFProcessor(config or {})
        
        # 注册任务函数到全局注册表
        task_registry.register('_process_pdf_batch', self._process_pdf_batch)
        self.task_id_prefix = "pdf-batch"
        
        # 注册collection映射和task_id前缀到全局注册表
        collection_registry.register(
            'pdf_batch_processing', 
            'pdf_batch_tasks',
            self.task_id_prefix  # 约束task_id必须以pdf-batch开头
        )
    
    def get_task_type(self) -> TaskType:
        """获取任务类型"""
        return TaskType.BATCH_PROCESSING
    
    async def create_task_instance(self, **kwargs) -> BatchTask:
        """
        创建PDF批处理任务实例
        
        Args:
            **kwargs: 任务创建参数
                - files: PDF文件列表
                - output_format: 输出格式
                - parser_options: 解析选项
                - trace_id: 链路追踪ID
                
        Returns:
            批处理任务实例
        """
        files = kwargs.get('files', [])
        output_format = kwargs.get('output_format', 'docx')
        parser_options = kwargs.get('parser_options', {})
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
            timeout=self.config.get('pdf_batch_timeout', 3600),
            max_retries=self.config.get('pdf_batch_max_retries', 3),
            trace_id=trace_id,
            metadata={'collection_type': 'pdf_batch_processing'}  # 指定collection类型
        )
        
        return task
    
    async def submit_pdf_batch_task(
        self, 
        request: PDFParserBatchRequest, 
        trace_id: str = None
    ) -> PDFParserBatchResponse:
        """
        提交PDF批处理任务
        
        Args:
            request: PDF批处理请求
            trace_id: 链路追踪ID
            
        Returns:
            PDF批处理响应
        """
        logger.info(f"Submitting PDF batch task - TraceID: {trace_id} | Files: {len(request.files)}")
        
        try:
            # 统一构建任务参数
            task_params = {
                'files': request.files,
                'output_format': request.output_format,
                'parser_options': request.parser_options,
                'trace_id': trace_id
            }
            
            # 提交任务到队列（只传递一次参数）
            task_id = await self.submit_task(
                self._process_pdf_batch,
                task_params
            )
            
            return PDFParserBatchResponse(
                pdf_parser_batch_task_id=task_id,
                total_files=len(request.files),
                created_at=datetime.now().isoformat()
            )
            
        except Exception as e:
            logger.error(f"Failed to submit PDF batch task: {str(e)}")
            raise
    
    async def _process_pdf_batch(
        self,
        files: List[PDFFileItem],
        output_format: str,
        parser_options: Dict[str, Any],
        trace_id: str = None,
        task_id: str = None
    ) -> Dict[str, Any]:
        """
        处理PDF批处理任务的核心函数（异步版本）
        
        Args:
            files: PDF文件列表
            output_format: 输出格式
            parser_options: 解析选项
            trace_id: 链路追踪ID
            
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
        
        logger.info(f"Processing PDF batch task: {task_id} | Files: {len(files)}")
        
        # 更新任务状态为处理中
        if task_id:
            await self.storage_backend.update_task_status(task_id, TaskStatus.PROCESSING)
        
        results = []
        successful_count = 0
        failed_count = 0
        
        for idx, file_item in enumerate(files):
            sub_task_id = f"{task_id}_file_{idx}" if task_id else f"file_{idx}"
            
            try:
                # 更新处理进度
                if task_id:
                    await self.storage_backend.update_task_progress(
                        task_id, 
                        processed_items=idx,
                        successful_items=successful_count,
                        failed_items=failed_count
                    )
                
                # 处理单个PDF文件
                result = await self._process_single_pdf(
                    file_item, 
                    output_format, 
                    parser_options,
                    sub_task_id,
                    trace_id
                )
                
                if result['status'] == 'success':
                    successful_count += 1
                    status = TaskStatus.COMPLETED
                else:
                    failed_count += 1
                    status = TaskStatus.FAILED
                
                results.append(result)
                
                # 添加子任务结果
                if task_id:
                    await self.storage_backend.add_sub_task_result(
                        task_id,
                        sub_task_id,
                        status,
                        result.get('data'),
                        result.get('error_message'),
                        result.get('processing_time')
                    )
                
            except Exception as e:
                failed_count += 1
                error_result = {
                    'filename': file_item.filename,
                    'status': 'failed',
                    'error_message': str(e),
                    'data': None
                }
                results.append(error_result)
                
                # 添加失败的子任务结果
                if task_id:
                    await self.storage_backend.add_sub_task_result(
                        task_id,
                        sub_task_id,
                        TaskStatus.FAILED,
                        None,
                        str(e),
                        None
                    )
                
                logger.error(f"Failed to process file {file_item.filename}: {str(e)}")
        
        # 更新最终进度
        if task_id:
            final_status = TaskStatus.COMPLETED if failed_count == 0 else TaskStatus.FAILED
            
            # 如果有失败的文件，添加错误信息
            error_message = None
            if failed_count > 0:
                failed_files = [r['filename'] for r in results if r['status'] == 'failed']
                error_message = f"批处理失败: {failed_count}/{len(files)} 个文件处理失败，失败文件: {', '.join(failed_files[:5])}"
                if len(failed_files) > 5:
                    error_message += f" 等{len(failed_files)}个文件"
            
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
        
        batch_result = {
            'total_files': len(files),
            'successful_files': successful_count,
            'failed_files': failed_count,
            'results': results
        }
        
        logger.info(f"PDF batch task completed: {task_id} | Success: {successful_count} | Failed: {failed_count}")
        return batch_result
    
    async def _process_single_pdf(
        self,
        file_item: PDFFileItem,
        output_format: str,
        parser_options: Dict[str, Any],
        sub_task_id: str,
        trace_id: str = None
    ) -> Dict[str, Any]:
        """
        处理单个PDF文件
        
        Args:
            file_item: PDF文件项
            output_format: 输出格式
            parser_options: 解析选项
            sub_task_id: 子任务ID
            trace_id: 链路追踪ID
            
        Returns:
            处理结果字典
        """
        import time
        start_time = time.time()
        
        temp_file_path = None
        try:
            # 解码base64数据并保存到临时文件
            try:
                file_data = base64.b64decode(file_item.file_data)
            except Exception as decode_error:
                raise Exception(f"base64解码失败: {str(decode_error)}")
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                temp_file.write(file_data)
                temp_file_path = temp_file.name
            
            # 创建文件信息
            file_info = FileInfo(
                filename=file_item.filename,
                content_type='application/pdf',
                file_size=len(file_data),
                input_type='base64'
            )
            
            # 创建PDF解析请求
            pdf_request = PDFParserRequest(
                input_type="base64",
                file_data=file_item.file_data,
                filename=file_item.filename,
                output_format=output_format,
                parser_options=parser_options
            )
            
            # 调用PDF处理器
            response = await self.pdf_processor.process(
                pdf_request, 
                temp_file_path, 
                file_info, 
                trace_id
            )
            
            processing_time = time.time() - start_time
            
            # 根据输出格式构建结果
            if output_format == "text":
                result_data = response.text_content
            else:  # docx
                result_data = response.download_url
            
            return {
                'filename': file_item.filename,
                'status': 'success',
                'output_format': output_format,
                'data': result_data,
                'error_message': None,
                'processing_time': processing_time
            }
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Failed to process PDF file {file_item.filename}: {str(e)}")
            
            return {
                'filename': file_item.filename,
                'status': 'failed',
                'output_format': output_format,
                'data': None,
                'error_message': str(e),
                'processing_time': processing_time
            }
            
        finally:
            # 清理临时文件
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp file {temp_file_path}: {str(e)}")
    
    async def get_batch_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        获取PDF批处理任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务状态信息
        """
        try:
            # 获取基础任务状态
            base_status = await self.get_task_status(task_id)
            if not base_status:
                return None
            
            # 获取完整任务信息（包括子任务结果）
            task = await self.storage_backend.get_task(task_id)
            if not task or not isinstance(task, BatchTask):
                return base_status
            
            # 构建PDF批处理特有的响应格式
            pdf_results = []
            for sub_result in task.sub_results:
                pdf_task = PDFParserTask(
                    pdf_parser_task_id=sub_result.sub_task_id,
                    filename=self._extract_filename_from_result(sub_result),
                    status=PDFParserTaskStatus.SUCCESS if sub_result.status == TaskStatus.COMPLETED else PDFParserTaskStatus.FAILED,
                    output_format="docx",  # 默认输出格式
                    err_msg=sub_result.error_message or "",
                    data=sub_result.result or ""
                )
                pdf_results.append(pdf_task)
            
            return {
                'pdf_parser_batch_task_id': task_id,
                'status': base_status['status'],
                'total_files': task.total_items,
                'processed_files': task.processed_items,
                'successful_files': task.successful_items,
                'failed_files': task.failed_items,
                'progress': task.progress,
                'created_at': base_status['created_at'],
                'started_at': base_status['started_at'],
                'completed_at': base_status['completed_at'],
                'results': pdf_results
            }
            
        except Exception as e:
            logger.error(f"Failed to get PDF batch task status: {str(e)}")
            return None
    
    def _extract_filename_from_result(self, sub_result: SubTaskResult) -> str:
        """从子任务结果中提取文件名"""
        # 这里可以从sub_result.result中提取filename
        # 暂时返回一个默认值，实际实现中需要根据result的结构来提取
        if isinstance(sub_result.result, dict) and 'filename' in sub_result.result:
            return sub_result.result['filename']
        
        # 从sub_task_id中提取
        if '_file_' in sub_result.sub_task_id:
            return f"file_{sub_result.sub_task_id.split('_file_')[-1]}.pdf"
        
        return "unknown.pdf"