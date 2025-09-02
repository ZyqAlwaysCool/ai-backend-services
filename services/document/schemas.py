from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class PDFParserRequest(BaseModel):
    """PDF解析请求模型"""
    input_type: str = Field(..., description="输入类型: file | base64")
    file_data: Optional[str] = Field(None, description="PDF文件base64编码")
    filename: str = Field(..., description="文件名")
    output_format: str = Field("text", description="输出格式: text | docx")
    parser_options: Dict = Field(
        default={},
        description="解析选项"
    )


class PDFParserResponse(BaseModel):
    """PDF解析响应模型"""
    output_format: str = Field(..., description="实际输出格式")
    text_content: Optional[str] = Field(None, description="解析的文本内容(output_format=text)")
    download_url: Optional[str] = Field(None, description="docx文件下载链接(output_format=docx)")
    page_count: int = Field(..., description="PDF总页数")
    metadata: Dict = Field(..., description="PDF元数据")


class PDFFileItem(BaseModel):
    """PDF文件项模型"""
    file_data: str = Field(..., description="PDF文件base64编码")
    filename: str = Field(..., description="文件名")


class PDFParserBatchRequest(BaseModel):
    """PDF批量解析请求模型"""
    files: List[PDFFileItem] = Field(..., description="PDF文件列表,最多10个文件")
    output_format: str = Field("docx", description="统一输出格式: text | docx")
    parser_options: Dict = Field(default={}, description="统一解析选项")


class PDFParserBatchResponse(BaseModel):
    """PDF批量解析响应模型"""
    pdf_parser_batch_task_id: str = Field(..., description="pdf批处理任务ID")
    total_files: int = Field(..., description="总文件数")
    created_at: str = Field(..., description="任务创建时间")


class PDFParserTaskStatus(str, Enum):
    """PDF解析任务状态枚举"""
    SUCCESS = "success"
    FAILED = "failed"


class PDFParserTask(BaseModel):
    pdf_parser_task_id: str = Field(..., descrption="pdf解析任务Id")
    filename: str = Field(..., description="文件名")
    status: PDFParserTaskStatus = Field(..., description="pdf解析任务状态")
    output_format : str = Field("docx", description="统一输出格式: text | docx")
    err_msg: str = Field("", description="错误消息, 当PDFParserTaskStatus为failed时不为空")
    data: str = Field("", description="输出格式为text时, 字段为pdf解析的内容, 为docx时, 为文件下载链接")


class PDFParserTaskStatusResponse(BaseModel):
    """PDF批量解析任务状态响应模型"""
    pdf_parser_batch_task_id: str = Field(..., description="批处理任务ID")
    status: str = Field(..., description="任务状态: pending | processing | completed | failed")
    results: Optional[List[PDFParserTask]] = Field(None, description="任务结果")


class DocumentConvertRequest(BaseModel):
    """文档格式转换请求模型"""
    input_type: str = Field(..., description="输入类型: file | base64")
    file_data: Optional[str] = Field(None, description="文件base64编码")
    filename: str = Field(..., description="文件名")
    source_format: str = Field(..., description="源格式: docx | xlsx | markdown")
    target_format: str = Field(..., description="目标格式: pdf | docx | markdown")
    convert_options: Dict = Field(
        default={},
        description="转换选项"
    )


class DocumentConvertResponse(BaseModel):
    """文档格式转换响应模型"""
    convert_task_id: str = Field(..., description="转换任务ID")
    source_format: str = Field(..., description="源格式")
    target_format: str = Field(..., description="目标格式")
    created_at: str = Field(..., description="任务创建时间")


class ConvertTaskStatusResponse(BaseModel):
    """格式转换任务状态响应模型"""
    convert_task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态: pending | processing | completed | failed")
    download_url: Optional[str] = Field(None, description="转换成功后的下载链接")
    error_message: Optional[str] = Field(None, description="失败时的错误信息")
    created_at: str = Field(..., description="任务创建时间")
    completed_at: Optional[str] = Field(None, description="任务完成时间")
    source_format: str = Field(..., description="源格式")
    target_format: str = Field(..., description="目标格式")


class TextExtractRequest(BaseModel):
    """文本提取请求模型"""
    input_type: str = Field(..., description="输入类型: file | base64")
    file_data: Optional[str] = Field(None, description="base64编码(input_type=base64时必填)")
    filename: str = Field(..., description="文件名")
    extract_options: Dict = Field(
        default={},
        description="提取选项"
    )


class TextExtractResponse(BaseModel):
    """文本提取响应模型"""
    text_content: str = Field(..., description="提取的文本内容")
    word_count: int = Field(..., description="字数统计")
    file_info: Dict = Field(..., description="文件元信息")


class UploadFileItem(BaseModel):
    """上传文件项模型"""
    file_data: str = Field(..., description="文件base64编码")
    filename: str = Field(..., description="文件名")


class FileExtractStatus(str, Enum):
    """文件提取状态枚举"""
    SUCCESS = "success"
    FAILED = "failed"


class FileExtractTask(BaseModel):
    """文件提取任务模型"""
    extract_task_id: str = Field(..., description="提取任务Id")
    filename: str = Field(..., description="文件名")
    status: FileExtractStatus = Field(..., description="文件提取状态")
    text_content: str = Field(default="", description="文档提取内容")
    word_count: int = Field(default=0, description="字符数")


class TextExtractBatchRequest(BaseModel):
    """文本提取批处理请求模型"""
    files: List[UploadFileItem] = Field(..., description="文件列表，最多10个文件")
    extract_options: Dict = Field(default={}, description="统一提取选项")


class TextExtractBatchResponse(BaseModel):
    """文本提取批处理响应模型"""
    text_extract_batch_task_id: str = Field(..., description="批处理任务ID")
    total_files: int = Field(..., description="总文件数")
    created_at: str = Field(..., description="任务创建时间")


class ExtractTaskStatusResponse(BaseModel):
    """文本提取批处理任务状态响应模型"""
    text_extract_batch_task_id: str = Field(..., description="批处理任务ID")
    status: str = Field(..., description="任务状态: pending | processing | completed | failed")
    results: Optional[List[FileExtractTask]] = Field(None, description="任务结果")


class TableExtractRequest(BaseModel):
    """表格提取请求模型"""
    input_type: str = Field(..., description="输入类型: file | base64")
    file_data: Optional[str] = Field(None, description="xlsx文件base64编码")
    filename: str = Field(..., description="文件名")
    output_format: Optional[str] = Field("html_text", description="提取结果形式, 默认为html_text | html_file")


class TableExtractResponse(BaseModel):
    """表格提取响应模型"""
    html_content: Optional[str] = Field(None, description="html格式表格文本")
    download_url: Optional[str] = Field(None, description="html文件下载链接")


class DocumentServiceStatus(BaseModel):
    """Document服务状态模型"""
    service_name: str = Field(..., description="服务名称")
    version: str = Field(..., description="服务版本")
    enabled: bool = Field(..., description="是否启用")
    enabled_endpoints: List[str] = Field(..., description="启用的端点列表")


class DocumentTaskTypePrefix(str, Enum):
    """文档任务类型前缀枚举"""
    PDF_BATCH_PARSE_TASK = "pdf-parser-batch-task" # pdf批量解析(批处理任务前缀)
    PDF_PARSE_TASK = "pdf-to-docx-task" # pdf转换docx(单任务前缀)
    CONVERT_TASK = "convert-task" # 文档格式转换
    TEXT_EXTRACT_BATCH_TASK = "text-extract-batch-task" # 文本提取批处理(批处理任务前缀)
    