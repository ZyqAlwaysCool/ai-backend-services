'''
Description: 日志配置
Author: zyq
Date: 2025-07-29 17:07:47
LastEditors: zyq
LastEditTime: 2025-07-31 08:44:24
'''
import os, yaml
from loguru import logger
from pathlib import Path

def setup_logger(custom_dir: str | None = None):
    """
    读取环境特定的app配置中的log配置，
    并按"每天一个独立文件"输出日志。
    custom_dir: 业务代码可选传入日志目录
    """
    # 根据环境变量选择配置文件，默认为开发环境
    env = os.getenv('ENV', 'dev')
    config_filename = f"app.{env}.yml"
    cfg_path = Path(__file__).resolve().parent.parent.parent / "configs" / "app" / config_filename
    log_cfg  = yaml.safe_load(open(cfg_path, encoding="utf-8")).get("log", {})
    
    # 2. 优先级：custom_dir -> env -> yaml
    log_dir = (
        Path(custom_dir).expanduser()
        if custom_dir
        else Path(os.getenv("LOG_DIR", log_cfg.get("dir", "logs"))).expanduser()
    )
    log_dir.mkdir(parents=True, exist_ok=True)

    level      = log_cfg.get("level", "INFO")
    file_name  = log_cfg.get("file_name", "{time:YYYY-MM-DD}.log")
    retention  = log_cfg.get("retention", "30 days")  # 自动清理
    compression = log_cfg.get("compression", "zip")
    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )
    

    # 确保目录存在
    log_dir.mkdir(parents=True, exist_ok=True)

    # 移除 loguru 默认 handler，再添加自定义 handler
    logger.remove()
    logger.add(
        log_dir / file_name,
        level       = level,
        rotation    = "00:00",      # 每天 0 点切分
        retention   = retention,
        compression = compression,
        encoding    = "utf-8",
        enqueue     = True,          # 异步写，线程安全
        format      = fmt,
    )