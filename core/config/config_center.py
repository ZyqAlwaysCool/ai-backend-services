'''
Description: 全局配置中心, 业务无关
Author: zyq
Date: 2025-07-29 17:50:05
LastEditors: zyq
LastEditTime: 2025-08-28 11:37:38
'''
import yaml
import os
from pathlib import Path
from functools import lru_cache
from typing import Optional
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
    
    class Config:
        frozen = True


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