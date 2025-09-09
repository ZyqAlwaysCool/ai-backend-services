'''
Description: Retrieval服务数据模型定义
Author: zyq
Date: 2025-09-08
'''

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

class RetrievalUploadRequest(BaseModel):
    knowledge_base_name: str = Field(..., description="知识库名称", min_length=1)
    # 只支持multipart/form-data文件上传
    # files: List[UploadFile] - 通过表单上传
    upload_options: Optional[Dict[str, Any]] = Field(
        default=None,
        description="上传选项配置(预留扩展字段)"
    )

class FileUploadResult(BaseModel):
    filename: str = Field(..., description="文件名")
    file_size: int = Field(..., description="文件大小(字节)")
    upload_time: datetime = Field(..., description="上传时间") 
    status: str = Field(..., description="上传状态: success/failed")
    error_message: Optional[str] = Field(None, description="错误信息")
    file_path: Optional[str] = Field(None, description="存储文件路径")

class RetrievalUploadResponse(BaseModel):
    knowledge_base_name: str = Field(..., description="知识库名称")
    total_files: int = Field(..., description="总文件数")
    success_count: int = Field(..., description="成功上传数量") 
    failed_count: int = Field(..., description="失败上传数量")
    upload_results: List[FileUploadResult] = Field(..., description="详细上传结果")


class DocumentLanguage(str, Enum):
    """文档语言"""
    CHINESE = "zh"
    ENGLISH = "en"

class SplitMethod(str, Enum):
    """切分方式"""
    WORD = "word"           # 按词切分
    SENTENCE = "sentence"   # 按句子切分  
    PASSAGE = "passage"     # 按段落切分
    CUSTOM = "custom"       # 自定义分隔符

class ChineseGranularity(str, Enum):
    """中文分词粒度"""
    COARSE = "coarse"       # 粗粒度
    FINE = "fine"           # 细粒度

class DocumentCleanSettings(BaseModel):
    """文档清洗设置"""
    language: DocumentLanguage = Field(DocumentLanguage.CHINESE, description="文档语言")
    split_method: SplitMethod = Field(SplitMethod.SENTENCE, description="切分方式")
    split_length: int = Field(200, description="分割长度", ge=10, le=2000)
    split_overlap: int = Field(20, description="重叠长度", ge=0, le=500)
    
    # 中文特有配置
    chinese_granularity: Optional[ChineseGranularity] = Field(
        ChineseGranularity.COARSE, 
        description="中文分词粒度(仅中文生效)"
    )
    
    # 自定义分隔符配置
    custom_separator: Optional[str] = Field(
        None, 
        description="自定义分隔符(仅split_method=custom时生效)"
    )

class DocumentCleanRequest(BaseModel):
    knowledge_base_name: str = Field(..., description="知识库名称", min_length=1)
    clean_settings: DocumentCleanSettings = Field(..., description="清洗配置")

class FailedFileDetail(BaseModel):
    """失败文件详情"""
    filename: str = Field(..., description="文件名")
    error_message: str = Field(..., description="错误信息")
    error_code: Optional[str] = Field(None, description="错误代码")

class RetrievalTaskTypePrefix(str, Enum):
    """Retrieval服务任务类型前缀"""
    CLEAN_TASK = "clean-task"


class DocumentCleanTaskResponse(BaseModel):
    """清洗任务提交响应"""
    clean_task_id: str = Field(..., description="清洗任务ID")
    knowledge_base_name: str = Field(..., description="知识库名称")
    total_pending_files: int = Field(..., description="待处理文件数量")
    created_at: str = Field(..., description="任务创建时间")


class CleanTaskStatusResponse(BaseModel):
    """清洗任务状态查询响应"""
    clean_task_id: str = Field(..., description="清洗任务ID")
    status: str = Field(..., description="任务状态: pending|processing|completed|failed|cancelled")
    knowledge_base_name: str = Field(..., description="知识库名称") 
    total_files: int = Field(..., description="总文件数")
    processed_files: int = Field(..., description="已处理文件数")
    successful_files: int = Field(..., description="成功处理文件数")
    failed_files: int = Field(..., description="失败处理文件数")
    total_chunks: int = Field(..., description="生成的文档块总数")
    created_at: str = Field(..., description="创建时间")
    started_at: Optional[str] = Field(None, description="开始处理时间") 
    completed_at: Optional[str] = Field(None, description="完成时间")
    error_message: Optional[str] = Field(None, description="错误信息")
    failed_files_detail: List[FailedFileDetail] = Field(default=[], description="失败文件详情")