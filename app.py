'''
Description: AI服务平台主入口
Author: zyq
Date: 2025-01-21
'''
import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from core.logging import setup_logger
from core.config import validate_config_on_startup, get_app_config
from core.exceptions import global_exception_handler, business_exception_handler, BaseBusinessException
from core.middleware import RequestTraceMiddleware, RequestLoggingMiddleware
from core.schemas import BaseResponse
from services.registry import service_registry

# 设置日志
setup_logger()
from loguru import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """生命周期管理器"""
    logger.info("AI服务平台启动中...")
    
    # 启动时配置验证
    if not validate_config_on_startup():
        logger.error("配置验证失败，应用启动中止")
        raise SystemExit(1)
    
    # 发现并注册所有启用的服务
    try:
        await service_registry.discover_and_register_services()
        enabled_services = list(service_registry.get_enabled_services().keys())
        logger.info(f"已启用的服务: {enabled_services}")
        
        # 注册所有服务路由
        for service_name, service in service_registry.get_enabled_services().items():
            router = service.get_router()
            if router and router.routes:  # 只添加非空路由
                app.include_router(
                    router, 
                    prefix=f"/{service_name}",
                    tags=[service_name]
                )
        
        enabled_service_count = len(service_registry.get_enabled_services())
        logger.info(f"已注册 {enabled_service_count} 个服务路由")
        
        # 将服务注册器存储到app状态中，供路由访问
        app.state.service_registry = service_registry
        
    except Exception as e:
        logger.error(f"服务初始化失败: {str(e)}")
        raise SystemExit(1)
    
    logger.info("AI服务平台启动完成，所有组件已就绪")
    yield
    
    # 关闭时清理资源
    logger.info("AI服务平台正在关闭...")
    try:
        for service in service_registry.get_enabled_services().values():
            if hasattr(service, 'shutdown'):
                await service.shutdown()
        logger.info("所有服务已关闭")
    except Exception as e:
        logger.error(f"服务关闭时发生错误: {str(e)}")


# 创建FastAPI应用
app_config = get_app_config()
app = FastAPI(
    title="AI服务平台",
    version="1.0.0",
    description="通用AI能力集服务平台 - 提供Chat、文档处理、知识检索等服务",
    lifespan=lifespan
)

# 添加中间件（注意顺序）
app.add_middleware(RequestTraceMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加异常处理器
app.add_exception_handler(BaseBusinessException, business_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)


# 系统监控端点
@app.get("/health", response_model=BaseResponse, tags=["系统监控"])
async def health_check(request: Request):
    """健康检查端点"""
    trace_id = getattr(request.state, 'trace_id', None)
    
    # 检查所有服务健康状态
    services_health = await service_registry.health_check_all()
    
    # 判断整体健康状态
    all_healthy = all(services_health.values()) if services_health else True
    
    return BaseResponse.success(
        data={
            "status": "healthy" if all_healthy else "degraded",
            "platform": "AI服务平台",
            "version": "1.0.0",
            "services": services_health
        },
        trace_id=trace_id
    )


@app.get("/", response_model=BaseResponse, tags=["系统信息"])
async def root(request: Request):
    """根路径，返回平台信息"""
    trace_id = getattr(request.state, 'trace_id', None)
    enabled_services = list(service_registry.get_enabled_services().keys())
    
    return BaseResponse.success(
        data={
            "platform": "AI服务平台",
            "version": "1.0.0",
            "description": "通用AI能力集服务平台",
            "enabled_services": enabled_services,
            "docs": "/docs"
        },
        trace_id=trace_id
    )


@app.get("/services", response_model=BaseResponse, tags=["系统信息"])
async def list_services(request: Request):
    """列出所有启用的服务及其端点"""
    trace_id = getattr(request.state, 'trace_id', None)
    
    services_info = {}
    for name, service in service_registry.get_enabled_services().items():
        services_info[name] = service.get_metadata()
    
    return BaseResponse.success(
        data=services_info,
        trace_id=trace_id
    )



if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "19999"))
    
    logger.info(f"启动AI服务平台: http://{host}:{port}")
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=True,
    )