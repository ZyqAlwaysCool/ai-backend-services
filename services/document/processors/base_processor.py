"""
基础处理器类

提供所有文档处理器的基础接口和通用功能。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from loguru import logger

from core.schemas.file_models import FileInfo


class BaseProcessor(ABC):
    """基础文档处理器"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化基础处理器"""
        self.config = config
    
    @abstractmethod
    async def process(self, request, temp_file_path: str, file_info: FileInfo, trace_id: str = None):
        """处理文档的抽象方法"""
        pass
    
    def _log_processing_start(self, processor_name: str, filename: str, trace_id: str):
        """记录处理开始日志"""
        logger.info(f"{processor_name} processing start - TraceID: {trace_id} | Filename: {filename}")
    
    def _log_processing_end(self, processor_name: str, filename: str, trace_id: str, success: bool = True):
        """记录处理结束日志"""
        status = "success" if success else "failed"
        logger.info(f"{processor_name} processing {status} - TraceID: {trace_id} | Filename: {filename}")
    
    def _log_error(self, processor_name: str, trace_id: str, error: Exception):
        """记录处理错误日志"""
        logger.error(f"{processor_name} processing error - TraceID: {trace_id} | Error: {str(error)}")