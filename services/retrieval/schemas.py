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
    CUSTOM = "custom"       # 自定义分隔符

class SplitterType(str, Enum):
    """文档切分器类型"""
    RECURSIVE = "recursive"     # 递归切分
    HIERARCHICAL = "hierarchical"   # 层次切分
    CH = "ch"                   # 中文切分
    DEFAULT = "default"         # 默认

class ChineseGranularity(str, Enum):
    """中文分词粒度"""
    COARSE = "coarse"       # 粗粒度
    FINE = "fine"           # 细粒度

class DocumentCleanSettings(BaseModel):
    """文档清洗设置"""
    #language: DocumentLanguage = Field(DocumentLanguage.CHINESE, description="文档语言")
    split_method: SplitMethod = Field(SplitMethod.SENTENCE, description="切分方式")
    split_length: int = Field(512, description="分割长度", ge=0, le=5000)
    split_overlap: int = Field(100, description="重叠长度", ge=0, le=500) #重叠长度一般为split_length的10%~20%
    splitter: SplitterType = Field(SplitterType.DEFAULT, description="文档切分器类型")
    
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

class KnowledgeBaseBuildRequest(BaseModel):
    """知识库构建请求"""
    knowledge_base_name: str = Field(..., description="知识库名称", min_length=1)
    clean_settings: DocumentCleanSettings = Field(..., description="文档处理设置")

class FailedFileDetail(BaseModel):
    """失败文件详情"""
    filename: str = Field(..., description="文件名")
    error_message: str = Field(..., description="错误信息")
    error_code: Optional[str] = Field(None, description="错误代码")

class RetrievalTaskTypePrefix(str, Enum):
    """Retrieval服务任务类型前缀"""
    BUILD_TASK = "build-kb-task"          # 知识库构建任务


class KnowledgeBaseBuildResponse(BaseModel):
    """知识库构建响应"""
    build_task_id: str = Field(..., description="构建任务ID")
    knowledge_base_name: str = Field(..., description="知识库名称")
    settings_hash: str = Field(..., description="设置哈希值(版本标识)")
    total_files: int = Field(..., description="待处理文件数量")
    created_at: str = Field(..., description="任务创建时间")
    kb_version: str = Field(..., description="知识库版本")


class BuildTaskStatusResponse(BaseModel):
    """构建任务状态响应"""
    build_task_id: str = Field(..., description="构建任务ID")
    status: str = Field(..., description="任务状态: pending|processing|completed|failed")
    knowledge_base_name: str = Field(..., description="知识库名称")
    settings_hash: str = Field(..., description="设置哈希值")
    total_files: int = Field(..., description="总文件数")
    processed_files: int = Field(..., description="已处理文件数")
    total_chunks: int = Field(..., description="生成的文档块总数")
    created_at: str = Field(..., description="创建时间")
    completed_at: Optional[str] = Field(None, description="完成时间")
    error_message: Optional[str] = Field(None, description="错误信息")
    failed_files_detail: List[FailedFileDetail] = Field(default=[], description="失败文件详情")

class RetrievalQueryRequest(BaseModel):
    knowledge_base_name: str = Field(..., description="知识库名称")
    kb_version: str = Field(..., description="知识库版本")
    query_text: str = Field(..., description="检索内容")

class SearchResult(BaseModel):
    chunk_id: str = Field(..., description="文档块ID")
    content: str = Field(..., description="文档块内容")
    score: float = Field(..., description="相似度分数")
    source_document: str = Field(..., description="来源文档名称")
    metadata: Dict = Field(default={}, description="扩展元数据")

class RetrievalQueryResponse(BaseModel):
    knowledge_base_name: str = Field(..., description="知识库名称")
    kb_version: str = Field(..., description="知识库版本")
    query_text: str = Field(..., description="检索内容")
    results: List[SearchResult] = Field(..., description="检索结果列表")

class KnowledgeBaseInfo(BaseModel):
    knowledge_base_name: str = Field(..., description="知识库名称")
    kb_version: str = Field(..., description="知识库版本ID")
    document_count: int = Field(..., description="文档数量")
    chunk_count: int = Field(..., description="文档块数量")
    chunk_method: str = Field(..., description="切片方式")
    chunk_settings: Dict = Field(..., description="切片配置详情")
    created_at: str = Field(..., description="创建时间")
    metadata: Dict = Field(default={}, description="扩展元数据")

class KnowledgeBaseQueryResponse(BaseModel):
    knowledge_base_name: str = Field(..., description="知识库名称")
    knowledge_base_details: Optional[List[KnowledgeBaseInfo]] = Field([], description="知识库各版本配置信息")


# ================== 统一知识库/文档抽象模型（Provider 通用） ==================
class KnowledgeBaseProviderEnum(str, Enum):
    LOCAL = "local"
    DIFY = "dify"


class CredentialStatusEnum(str, Enum):
    ACTIVE = "active"
    DELETED = "deleted"

class KnowledgeBaseCreateRequest(BaseModel):
    name: str = Field(..., description="知识库名称")
    description: Optional[str] = Field(None, description="描述")
    provider: KnowledgeBaseProviderEnum = Field(KnowledgeBaseProviderEnum.LOCAL, description="provider 标识")


class KnowledgeBaseInfoExternal(BaseModel):
    kb_name: str = Field(..., description="知识库名称")
    provider: KnowledgeBaseProviderEnum = Field(..., description="provider 标识")
    description: Optional[str] = Field(None, description="描述")
    external_kb_id: Optional[str] = Field(None, description="外部平台 KB ID")


class KnowledgeBaseListResponse(BaseModel):
    items: List[KnowledgeBaseInfoExternal] = Field(default_factory=list)
    page: int = 1
    limit: int = 20
    total: int = 0
    has_more: bool = False


class KnowledgeBaseDocumentCreateRequest(BaseModel):
    input_type: str = Field(..., description="text | file")
    doc_name: Optional[str] = Field(None, description="文档名称")
    text: Optional[str] = Field(None, description="文本内容")
    file_path: Optional[str] = Field(None, description="临时文件路径")
    indexing_technique: Optional[str] = Field(None, description="索引模式")
    process_rule: Optional[Dict[str, Any]] = Field(None, description="处理规则")


class KnowledgeBaseDocumentUpdateRequest(KnowledgeBaseDocumentCreateRequest):
    pass


class KnowledgeBaseDocumentInfo(BaseModel):
    doc_id: str = Field(..., description="文档ID（内部或外部）")
    doc_name: str = Field(..., description="文档名称")
    indexing_status: str = Field("", description="索引状态")
    provider: KnowledgeBaseProviderEnum = Field(..., description="provider 标识")
    external_batch_task_id: Optional[str] = Field(None, description="外部批次ID")


class KnowledgeBaseDocumentListResponse(BaseModel):
    items: List[KnowledgeBaseDocumentInfo] = Field(default_factory=list)
    page: int = 1
    limit: int = 20
    total: int = 0
    has_more: bool = False


class KnowledgeBaseIndexStatusItem(BaseModel):
    doc_id: str = Field(..., description="文档ID")
    status: str = Field(..., description="索引状态")
    completed_segments: Optional[int] = None
    total_segments: Optional[int] = None
    error: Optional[str] = None


class KnowledgeBaseIndexStatusResponse(BaseModel):
    items: List[KnowledgeBaseIndexStatusItem] = Field(default_factory=list)


class KnowledgeBaseSegmentPayload(BaseModel):
    content: str = Field(..., description="分段内容")
    answer: Optional[str] = Field(None, description="答案")
    keywords: Optional[List[str]] = Field(None, description="关键词")
    enabled: Optional[bool] = Field(True, description="是否启用")


class KnowledgeBaseSegmentCreateRequest(BaseModel):
    kb_name: str = Field(..., description="知识库名称")
    doc_name: str = Field(..., description="文档名称")
    provider: KnowledgeBaseProviderEnum = Field(..., description="provider 标识")
    segments: List[KnowledgeBaseSegmentPayload] = Field(..., description="分段列表")


class KnowledgeBaseSegmentUpdateRequest(BaseModel):
    kb_name: str = Field(..., description="知识库名称")
    doc_name: str = Field(..., description="文档名称")
    segment_id: str = Field(..., description="分段ID")
    provider: KnowledgeBaseProviderEnum = Field(..., description="provider 标识")
    segment: KnowledgeBaseSegmentPayload = Field(..., description="分段内容")


class KnowledgeBaseSegmentDeleteRequest(BaseModel):
    kb_name: str = Field(..., description="知识库名称")
    doc_name: str = Field(..., description="文档名称")
    provider: KnowledgeBaseProviderEnum = Field(..., description="provider 标识")
    segment_id: str = Field(..., description="分段ID")


class KnowledgeBaseSegmentInfo(BaseModel):
    segment_id: str = Field(..., description="分段ID")
    doc_id: str = Field(..., description="文档ID")
    content: str = Field(..., description="内容")
    answer: Optional[str] = None
    enabled: bool = True
    status: Optional[str] = None


class KnowledgeBaseSegmentListResponse(BaseModel):
    items: List[KnowledgeBaseSegmentInfo] = Field(default_factory=list)
    page: int = 1
    limit: int = 20
    total: int = 0
    has_more: bool = False


class KnowledgeBaseMetadataField(BaseModel):
    id: str
    type: str
    name: str


class KnowledgeBaseMetadataListResponse(BaseModel):
    fields: List[KnowledgeBaseMetadataField] = Field(default_factory=list)
    built_in_field_enabled: bool = True


class BuiltInMetadataAction(str, Enum):
    ENABLE = "enable"
    DISABLE = "disable"


class KnowledgeBaseToggleBuiltInMetadataRequest(BaseModel):
    kb_name: str = Field(..., description="知识库名称")
    provider: KnowledgeBaseProviderEnum = Field(..., description="provider 标识")
    action: BuiltInMetadataAction = Field(..., description="启用/禁用内置元数据，可选: enable/disable")


class KnowledgeBaseMetadataAssignRequest(BaseModel):
    operation_data: List[Dict[str, Any]] = Field(..., description="文档元数据赋值列表")


class KnowledgeBaseMetadataAssignByNameRequest(BaseModel):
    kb_name: str = Field(..., description="知识库名称")
    provider: KnowledgeBaseProviderEnum = Field(..., description="provider 标识")
    documents: List[Dict[str, Any]] = Field(
        ...,
        description="文档与元数据列表，形如 [{'doc_name': 'doc1', 'metadata_list': [{'name': 'field', 'value': 'xx'}]}]",
    )


class KnowledgeBaseMetadataRenameRequest(BaseModel):
    kb_name: str = Field(..., description="知识库名称")
    provider: KnowledgeBaseProviderEnum = Field(..., description="provider 标识")
    old_meta_field_name: str = Field(..., description="旧的元数据字段名", min_length=1)
    new_meta_field_name: str = Field(..., description="新的元数据字段名", min_length=1)


class KnowledgeBaseMetadataDeleteRequest(BaseModel):
    kb_name: str = Field(..., description="知识库名称")
    provider: KnowledgeBaseProviderEnum = Field(..., description="provider 标识")
    meta_field_name: str = Field(..., description="待删除的元数据字段名", min_length=1)


# ================ 凭证管理模型 =================
class KBCredentialCreateRequest(BaseModel):
    provider: KnowledgeBaseProviderEnum = Field(KnowledgeBaseProviderEnum.DIFY, description="provider 标识，如 dify")
    name: str = Field(..., description="凭证名称")
    api_key: str = Field(..., description="API Key")
    workspace_id: Optional[str] = Field(None, description="可选 workspace id")
    is_default: bool = Field(False, description="是否默认")
    description: Optional[str] = Field(None, description="备注")


class KBCredentialInfo(BaseModel):
    provider: KnowledgeBaseProviderEnum
    name: str
    workspace_id: Optional[str] = None
    is_default: bool = False
    status: str = "active"
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    api_key: Optional[str] = None


class KBCredentialListResponse(BaseModel):
    items: List[KBCredentialInfo] = Field(default_factory=list)
