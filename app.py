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
from core.config import validate_config_on_startup, get_app_config, load_app_config
from core.exceptions import global_exception_handler, business_exception_handler, BaseBusinessException
from core.middleware import RequestTraceMiddleware, RequestLoggingMiddleware, AuthMiddleware
from core.middleware.file_input import FileInputMiddleware
from core.schemas import BaseResponse
from core.storage.mongo_storage import MongoStorage
from core.auth.auth_service import AuthService
from core.auth.user_storage import AuthUserStorage
from core.auth.auth_router import auth_router, set_auth_service
from core.tasks.worker_manager import get_worker_manager
from services.registry import service_registry

# 设置日志
setup_logger()
from loguru import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """生命周期管理器"""
    logger.info("Starting AI service platform...")
    
    # 启动时配置验证
    if not validate_config_on_startup():
        logger.error("Configuration validation failed, application startup aborted")
        raise SystemExit(1)
    
    # 初始化认证服务
    try:
        app_config = load_app_config()
        mongo_storage = MongoStorage(
            db_name=app_config.mongo_database
        )
        
        user_storage = AuthUserStorage(mongo_storage)
        auth_service = AuthService(
            secret_key=app_config.jwt_secret_key,
            token_expire_hours=app_config.token_expire_hours
        )
        auth_service.set_user_storage(user_storage)
        
        # 注入到路由模块
        set_auth_service(auth_service)
        
        logger.info("Auth service initialized successfully")
        
    except Exception as e:
        logger.error(f"Auth service initialization failed: {str(e)}")
        raise SystemExit(1)
    
    # 发现并注册所有启用的服务
    try:
        await service_registry.discover_and_register_services()
        enabled_services = list(service_registry.get_enabled_services().keys())
        logger.info(f"Enabled services: {enabled_services}")
        
        # 注册所有服务路由
        for service_name, service in service_registry.get_enabled_services().items():
            router = service.get_router()
            if router and router.routes:  # 只添加非空路由
                app.include_router(
                    router, 
                    prefix=f"/{service_name}"
                )
        
        enabled_service_count = len(service_registry.get_enabled_services())
        logger.info(f"Registered {enabled_service_count} service routes")
        
        # 将服务注册器存储到app状态中，供路由访问
        app.state.service_registry = service_registry
        
        # 注册认证路由
        app.include_router(auth_router)
        logger.info("Auth routes registered successfully")
        
        # 将认证服务存储到app状态供中间件使用
        app.state.auth_service = auth_service
        logger.info("Auth service stored to app state")
        
    except Exception as e:
        logger.error(f"Service initialization failed: {str(e)}")
        raise SystemExit(1)
    
    # 启动ARQ Worker
    try:
        worker_manager = get_worker_manager()
        worker_success = await worker_manager.start_worker()
        
        if worker_success:
            logger.info("ARQ Worker started successfully")
            # 将worker管理器存储到app状态
            app.state.worker_manager = worker_manager
        else:
            logger.warning("ARQ Worker failed to start, task processing will be unavailable")
            
    except Exception as e:
        logger.error(f"ARQ Worker initialization failed: {str(e)}")
        # 不终止应用启动，但记录错误
        logger.warning("Continuing without task worker - batch processing will be unavailable")
    
    logger.info("AI service platform started successfully, all components ready")
    yield
    
    # 关闭时清理资源
    logger.info("AI service platform is shutting down...")
    try:
        # 首先停止Worker
        if hasattr(app.state, 'worker_manager'):
            logger.info("Stopping ARQ Worker...")
            await app.state.worker_manager.stop_worker()
            logger.info("ARQ Worker stopped")
        
        # 然后停止其他服务
        for service in service_registry.get_enabled_services().values():
            if hasattr(service, 'shutdown'):
                await service.shutdown()
        logger.info("All services shutdown completed")
    except Exception as e:
        logger.error(f"Error occurred during service shutdown: {str(e)}")


# 创建FastAPI应用
app_config = get_app_config()
app = FastAPI(
    title="AI服务平台",
    version="1.0.0",
    description="通用AI能力集服务平台 - 提供Chat、文档处理、知识检索等服务",
    lifespan=lifespan,
    # 配置Swagger UI的认证支持
    openapi_tags=[
        {"name": "认证", "description": "用户认证相关接口"},
        {"name": "服务", "description": "AI服务相关接口"}
    ]
)

# 添加Bearer token认证到OpenAPI schema
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    # 添加Bearer token认证支持
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "输入JWT token（不需要'Bearer '前缀）"
        }
    }
    
    # 定义不需要认证的路径
    public_paths = {
        "/auth/login",
        "/auth/verify", 
        "/health",
        "/",
        "/docs",
        "/openapi.json",
        "/redoc"
    }
    
    # 为所有需要认证的接口添加安全要求
    for path, methods in openapi_schema["paths"].items():
        if path not in public_paths:
            for method, details in methods.items():
                if method in ["get", "post", "put", "delete", "patch"]:
                    details["security"] = [{"BearerAuth": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# 添加中间件（注意顺序 - 后添加的先执行）
app.add_middleware(FileInputMiddleware)  # 文件输入处理中间件
app.add_middleware(AuthMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RequestTraceMiddleware)
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
    
    app_config = get_app_config()
    host = app_config.server_host
    port = app_config.server_port
    
    logger.info(f"Starting AI service platform: http://{host}:{port}")
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=False,
    )