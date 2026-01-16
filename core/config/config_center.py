'''
Description: 全局配置中心, 业务无关
Author: zyq
Date: 2025-07-29 17:50:05
LastEditors: zyq
LastEditTime: 2025-11-05 16:01:17
'''
import yaml
import os
from pathlib import Path
from functools import lru_cache
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from loguru import logger


class ConfigValidationError(Exception):
    """配置验证错误"""
    pass


# ===============模型服务配置===============
class ModelConfig(BaseModel):
    name: str = Field(..., description="模型名称")
    base_url: str = Field(..., description="模型服务地址", min_length=1)
    api_key: str = Field(..., description="API密钥", min_length=1)
    
    class Config:
        frozen = True  # 配置不可变


class LLMProviderConfig(BaseModel):
    provider: str = Field(..., description="LLM提供商")
    timeout: int = Field(30, description="请求超时时间(秒)", ge=1, le=300)
    temperature: float = Field(0.7, description="模型温度参数", ge=0.0, le=2.0)
    stream: bool = Field(False, description="是否启用流式响应")
    models: list[ModelConfig] = Field(..., description="模型配置列表", min_items=1)
    
    class Config:
        frozen = True


class AppConfig(BaseModel):
    """应用配置模型"""
    log_level: str = Field("INFO", description="日志级别")
    log_dir: str = Field("logs", description="日志目录")
    log_retention: str = Field("30 days", description="日志保留时间")
    mongo_host: str = Field("127.0.0.1", description="MongoDB主机")
    mongo_port: int = Field(27017, description="MongoDB端口", ge=1, le=65535)
    mongo_database: str = Field("ai_backend_services", description="MongoDB数据库名")
    redis_host: str = Field("127.0.0.1", description="Redis主机")
    redis_port: int = Field(6379, description="Redis端口", ge=1, le=65535)
    redis_db: int = Field(0, description="Redis数据库", ge=0, le=15)
    redis_password: Optional[str] = Field(None, description="Redis密码")
    redis_max_connections: int = Field(10, description="Redis最大连接数", ge=1, le=100)
    jwt_secret_key: str = Field(..., description="JWT密钥", min_length=16)
    token_expire_hours: int = Field(24, description="Token过期时间(小时)", ge=1, le=168)
    server_host: str = Field("0.0.0.0", description="服务器主机")
    server_port: int = Field(18888, description="服务器端口", ge=1, le=65535)
    qdrant_host: str = Field("localhost", description="Qdrant主机")
    qdrant_port: int = Field(6333, description="Qdrant端口", ge=1, le=65535)
    qdrant_timeout: int = Field(30, description="Qdrant超时时间(秒)", ge=1, le=300)
    embedding_dim: int = Field(1024, description="向量维度", ge=128, le=4096)
    embedding_model_path: str = Field("models/Qwen3-Embedding-0___6B", description="Embedding模型路径(相对于项目根目录)")
    embedding_batch_size: int = Field(8, description="Embedding批处理大小", ge=1, le=128)
    embedding_device: str = Field("cpu", description="Embedding模型运行设备(cpu/cuda/cuda:0/cuda:1等)")
    dify_url: str = Field("http://172.16.32.88:port/v1", description="Dify平台URL")

    class Config:
        frozen = True


# ===============服务配置===============
class BaseServiceConfig(BaseModel):
    """基础服务配置"""
    enabled: bool = Field(True, description="服务是否启用")
    version: str = Field("1.0.0", description="服务版本")
    endpoints: Dict[str, bool] = Field(default_factory=dict, description="启用的端点")
    
    class Config:
        frozen = True


class ChatConfig(BaseServiceConfig):
    """Chat服务配置"""
    enabled_models: List[str] = Field(default_factory=list, description="启用的模型列表")
    rate_limits: Dict[str, int] = Field(default_factory=dict, description="限流配置")
    chat_db_name: str = Field("ai_backend_services_chat", description="数据库名")
    chat_apikey_collection_name: str = Field("chat_apikey", description="存储各chatflow平台的API Key")
    chat_oauth_collection_name: str = Field("chat_oauth", description="存储coze oauth配置")
    coze_auth_mode: str = Field("api_key", description="coze鉴权方式(api_key|oauth)")
    coze_oauth_token_ttl: int = Field(3600, description="coze oauth token有效期(秒)")

class DocumentConfig(BaseServiceConfig):
    """Document服务配置"""
    supported_formats: List[str] = Field(default_factory=list, description="支持的文件格式")
    max_file_size: int = Field(52428800, description="最大文件大小(字节)", ge=1)
    max_batch_files: int = Field(10, description="最大批处理文件数", ge=1)


class DocumentCleanPerformanceConfig(BaseModel):
    """文档清洗性能配置"""
    sync_threshold: int = Field(20, description="同步处理阈值", ge=1, le=100)
    chunk_batch_size: int = Field(10, description="异步处理时的分批大小", ge=5, le=50)
    single_doc_timeout_seconds: int = Field(60, description="单个文档清洗超时时间(秒)", ge=10, le=300)

class RetrievalConfig(BaseServiceConfig):
    """Retrieval服务配置"""
    retrieval_db_name: str = Field("ai_backend_services_retrieval", description="数据库名")
    retrieval_document_collection_name: str = Field("retrieval_documents", description="文档集合名")
    retrieval_kb_collection_name: str = Field("retrieval_knowledge_bases", description="知识库集合名")
    max_file_size: int = Field(52428800, description="最大文件大小(字节)", ge=1)
    max_files_per_request: int = Field(10, description="单次请求最大文件数量", ge=1)
    supported_formats: List[str] = Field(default_factory=list, description="支持的文件格式")
    clean_performance: Optional[DocumentCleanPerformanceConfig] = Field(None, description="文档清洗性能配置")


class MultimodalConfig(BaseServiceConfig):
    """Multimodal服务配置"""
    pass


class MCPConfig(BaseServiceConfig):
    """MCP服务配置"""
    mcp_db_name: str = Field("ai_backend_services_mcp", description="MCP数据库名")
    tool_collection_name: str = Field("mcp_tools", description="工具集合名")
    run_collection_name: str = Field("mcp_runs", description="运行记录集合名")
    run_step_collection_name: str = Field("mcp_run_steps", description="运行步骤集合名")
    default_agent_mode: str = Field("single_agent_tool_choice", description="默认编排模式")
    allowed_agent_modes: List[str] = Field(default_factory=list, description="允许的编排模式")
    max_tools_per_request: int = Field(5, description="单次请求最大工具数", ge=1, le=20)
    limits: Dict[str, int] = Field(default_factory=dict, description="运行限制")
    cache: Dict[str, int] = Field(default_factory=dict, description="缓存配置")
    server: Dict[str, str] = Field(default_factory=dict, description="服务器配置")
    logging: Dict[str, Any] = Field(default_factory=dict, description="日志开关")
    streaming: Dict[str, Any] = Field(default_factory=dict, description="流式事件开关")


class ServicesConfig(BaseModel):
    """服务配置模型"""
    enabled: List[str] = Field(..., description="启用的服务列表")
    chat: Optional[ChatConfig] = Field(None, description="Chat服务配置")
    document: Optional[DocumentConfig] = Field(None, description="Document服务配置")
    retrieval: Optional[RetrievalConfig] = Field(None, description="Retrieval服务配置")
    multimodal: Optional[MultimodalConfig] = Field(None, description="Multimodal服务配置")
    mcp: Optional[MCPConfig] = Field(None, description="MCP服务配置")
    
    class Config:
        frozen = True

class WorkerConfig(BaseModel):
    """arq worker配置"""
    queue_name: str = Field("arq:queue", description="任务队列名称")
    max_jobs: int = Field(10, description="最大任务数量")
    job_timeout: int = Field(3600, description="任务超时时间(秒)")
    keep_result: int = Field(86400, description="保留结果时间(秒)")
    health_check_interval: int = Field(3600, description="健康检查间隔(秒)")
    retry_jobs: bool = Field(True, description="是否启用任务重试")
    max_tries: int = Field(3, description="最大重试次数")

@lru_cache(maxsize=1)
def load_worker_config() -> WorkerConfig:
    """加载worker配置"""
    cfg_path = Path(__file__).parent.parent.parent / "configs" / "services" / "worker.yml"

    if not cfg_path.exists():
        raise ConfigValidationError(f"worker配置文件不存在: {cfg_path}")
    
    try:
        with open(cfg_path, encoding='utf-8') as f:
            raw_config = yaml.safe_load(f)
        
        # 提取woker配置
        worker_data = raw_config.get('worker', {})
        return WorkerConfig(**worker_data)
        
    except Exception as e:
        raise ConfigValidationError(f"服务配置加载失败: {str(e)}")

@lru_cache(maxsize=1)
def get_worker_config() -> WorkerConfig:
    return load_worker_config()
        


@lru_cache(maxsize=1)
def load_services_config() -> ServicesConfig:
    """加载服务配置"""
    cfg_path = Path(__file__).parent.parent.parent / "configs" / "services" / "services.yml"
    
    if not cfg_path.exists():
        raise ConfigValidationError(f"服务配置文件不存在: {cfg_path}")
    
    try:
        with open(cfg_path, encoding='utf-8') as f:
            raw_config = yaml.safe_load(f)
        
        # 提取services配置
        services_data = raw_config.get('services', {})
        
        # 支持环境变量覆盖关键配置
        if 'retrieval' in services_data:
            retrieval_config = services_data['retrieval']
            retrieval_config['retrieval_db_name'] = os.getenv('RETRIEVAL_DB_NAME', 
                                                            retrieval_config.get('retrieval_db_name', 'ai_backend_services_retrieval'))
            retrieval_config['max_file_size'] = int(os.getenv('MAX_FILE_SIZE', 
                                                            retrieval_config.get('max_file_size', 52428800)))
            retrieval_config['max_files_per_request'] = int(os.getenv('MAX_FILES_PER_REQUEST', 
                                                                    retrieval_config.get('max_files_per_request', 10)))
        if 'mcp' in services_data:
            mcp_config = services_data['mcp']
            mcp_config['mcp_db_name'] = os.getenv('MCP_DB_NAME', mcp_config.get('mcp_db_name', 'ai_backend_services_mcp'))
        
        return ServicesConfig(**services_data)
        
    except Exception as e:
        raise ConfigValidationError(f"服务配置加载失败: {str(e)}")


@lru_cache(maxsize=1)
def get_services_config() -> ServicesConfig:
    """获取服务配置（带缓存）"""
    return load_services_config()


class MCPRuntimeConfig(BaseModel):
    """MCP运行时配置"""
    mcp: Dict[str, Any]


@lru_cache(maxsize=1)
def load_mcp_runtime_config() -> MCPRuntimeConfig:
    """加载MCP运行时配置"""
    cfg_path = Path(__file__).parent.parent.parent / "configs" / "mcp" / "mcp.yml"
    if not cfg_path.exists():
        raise ConfigValidationError(f"MCP配置文件不存在: {cfg_path}")
    try:
        with open(cfg_path, encoding='utf-8') as f:
            raw_config = yaml.safe_load(f)
        return MCPRuntimeConfig(**raw_config)
    except Exception as e:
        raise ConfigValidationError(f"MCP配置加载失败: {str(e)}")


def get_mcp_runtime_config() -> MCPRuntimeConfig:
    """获取MCP运行时配置"""
    return load_mcp_runtime_config()


@lru_cache(maxsize=10)
def load_llm_cfg(name: str) -> LLMProviderConfig:
    """加载LLM配置（带缓存）"""
    cfg_path = Path(__file__).parent.parent.parent / "configs" / "llm_providers" / f"{name}.yml"
    
    if not cfg_path.exists():
        raise ConfigValidationError(f"配置文件不存在: {cfg_path}")
    
    try:
        with open(cfg_path, encoding='utf-8') as f:
            raw_config = yaml.safe_load(f)
        
        # 支持环境变量替换
        if raw_config.get('models'):
            for model in raw_config['models']:
                if 'api_key' in model and model['api_key'].startswith('${'):
                    env_var = model['api_key'][2:-1]  # 移除 ${ 和 }
                    model['api_key'] = os.getenv(env_var, model['api_key'])
        
        return LLMProviderConfig(**raw_config)
    except Exception as e:
        raise ConfigValidationError(f"配置加载失败 {name}: {str(e)}")


@lru_cache(maxsize=1)
def get_app_config() -> AppConfig:
    """获取应用配置（带缓存）"""
    return load_app_config()

@lru_cache(maxsize=1)
def load_app_config() -> AppConfig:
    """加载应用配置（带缓存）"""
    # 根据环境变量选择配置文件，默认为开发环境
    env = os.getenv('ENV', 'dev')
    config_filename = f"app.{env}.yml"
    cfg_path = Path(__file__).parent.parent.parent / "configs" / "app" / config_filename
    
    if not cfg_path.exists():
        raise ConfigValidationError(f"应用配置文件不存在: {cfg_path}")
    
    try:
        with open(cfg_path, encoding='utf-8') as f:
            raw_config = yaml.safe_load(f)
        
        # 合并log和mongo配置
        config_dict = {}
        if 'log' in raw_config:
            log_config = raw_config['log']
            config_dict.update({
                'log_level': log_config.get('level', 'INFO'),
                'log_dir': log_config.get('dir', 'logs'),
                'log_retention': log_config.get('retention', '30 days')
            })
        
        if 'mongo' in raw_config:
            mongo_config = raw_config['mongo']
            config_dict.update({
                'mongo_host': mongo_config.get('host', '127.0.0.1'),
                'mongo_port': mongo_config.get('port', 27017),
                'mongo_database': mongo_config.get('database', 'ai_backend_services')
            })
        
        if 'redis' in raw_config:
            redis_config = raw_config['redis']
            config_dict.update({
                'redis_host': redis_config.get('host', '127.0.0.1'),
                'redis_port': redis_config.get('port', 6379),
                'redis_db': redis_config.get('db', 0),
                'redis_password': redis_config.get('password'),
                'redis_max_connections': redis_config.get('max_connections', 10)
            })
        
        if 'auth' in raw_config:
            auth_config = raw_config['auth']
            config_dict.update({
                'jwt_secret_key': auth_config.get('jwt_secret_key'),
                'token_expire_hours': auth_config.get('token_expire_hours', 24)
            })
        
        if 'server' in raw_config:
            server_config = raw_config['server']
            config_dict.update({
                'server_host': server_config.get('host', '0.0.0.0'),
                'server_port': server_config.get('port', 18888)
            })
        
        if 'qdrant' in raw_config:
            qdrant_config = raw_config['qdrant']
            config_dict.update({
                'qdrant_host': qdrant_config.get('host', 'localhost'),
                'qdrant_port': qdrant_config.get('port', 6333),
                'qdrant_timeout': qdrant_config.get('timeout', 30),
                'embedding_dim': qdrant_config.get('embedding_dim', 768)
            })
        
        if 'embedding' in raw_config:
            embedding_config = raw_config['embedding']
            config_dict.update({
                'embedding_model_path': embedding_config.get('model_path', 'models/Qwen3-Embedding-4B'),
                'embedding_batch_size': embedding_config.get('batch_size', 8),
                'embedding_device': embedding_config.get('device', 'cpu')
            })
        
        # 支持环境变量覆盖
        config_dict['mongo_host'] = os.getenv('MONGO_HOST', config_dict.get('mongo_host', '127.0.0.1'))
        config_dict['mongo_port'] = int(os.getenv('MONGO_PORT', config_dict.get('mongo_port', 27017)))
        config_dict['mongo_database'] = os.getenv('MONGO_DATABASE', config_dict.get('mongo_database', 'ai_backend_services'))
        config_dict['redis_host'] = os.getenv('REDIS_HOST', config_dict.get('redis_host', '127.0.0.1'))
        config_dict['redis_port'] = int(os.getenv('REDIS_PORT', config_dict.get('redis_port', 6379)))
        config_dict['redis_db'] = int(os.getenv('REDIS_DB', config_dict.get('redis_db', 0)))
        config_dict['redis_password'] = os.getenv('REDIS_PASSWORD', config_dict.get('redis_password'))
        config_dict['redis_max_connections'] = int(os.getenv('REDIS_MAX_CONNECTIONS', config_dict.get('redis_max_connections', 10)))
        config_dict['log_level'] = os.getenv('LOG_LEVEL', config_dict.get('log_level', 'INFO'))
        config_dict['jwt_secret_key'] = os.getenv('JWT_SECRET_KEY', config_dict.get('jwt_secret_key'))
        config_dict['token_expire_hours'] = int(os.getenv('TOKEN_EXPIRE_HOURS', config_dict.get('token_expire_hours', 24)))
        config_dict['server_host'] = os.getenv('HOST', config_dict.get('server_host', '0.0.0.0'))
        config_dict['server_port'] = int(os.getenv('PORT', config_dict.get('server_port', 18888)))
        config_dict['qdrant_host'] = os.getenv('QDRANT_HOST', config_dict.get('qdrant_host', 'localhost'))
        config_dict['qdrant_port'] = int(os.getenv('QDRANT_PORT', config_dict.get('qdrant_port', 6333)))
        config_dict['qdrant_timeout'] = int(os.getenv('QDRANT_TIMEOUT', config_dict.get('qdrant_timeout', 30)))
        config_dict['embedding_dim'] = int(os.getenv('EMBEDDING_DIM', config_dict.get('embedding_dim', 768)))
        config_dict['embedding_model_path'] = os.getenv('EMBEDDING_MODEL_PATH', config_dict.get('embedding_model_path', 'models/Qwen3-Embedding-4B'))
        config_dict['embedding_batch_size'] = int(os.getenv('EMBEDDING_BATCH_SIZE', config_dict.get('embedding_batch_size', 8)))
        config_dict['embedding_device'] = os.getenv('EMBEDDING_DEVICE', config_dict.get('embedding_device', 'cpu'))
        config_dict['dify_url'] = os.getenv('DIFY_URL', config_dict.get('dify_url', 'http://172.16.32.88:port/v1'))
        
        return AppConfig(**config_dict)
    except Exception as e:
        raise ConfigValidationError(f"应用配置加载失败: {str(e)}")


def validate_config_on_startup():
    """启动时配置验证"""
    try:
        app_config = load_app_config()
        logger.info(f"Application configuration loaded successfully: {app_config}")
        return True
    except ConfigValidationError as e:
        logger.error(f"Configuration validation failed: {e}")
        return False


# 全局配置实例
def get_app_config() -> AppConfig:
    """获取应用配置"""
    return load_app_config()
