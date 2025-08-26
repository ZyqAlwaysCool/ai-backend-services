# AI服务平台

## 🎯 项目简介

本项目是一个**统一的AI能力集服务平台**，采用单体应用 + 模块化服务的架构设计，将多个AI服务（Chat、Document、Retrieval、Multimodal等）集成在一个FastAPI应用中。通过配置驱动和服务注册机制，实现AI服务的统一管理、快速开发和灵活扩展。

### 🚀 核心优势

- **统一服务平台**：多个AI服务统一部署管理，单一入口
- **统一认证体系**：JWT Token认证，Swagger UI支持，权限细粒度控制
- **配置驱动**：YAML配置控制服务启用状态和行为
- **服务注册机制**：自动发现和注册符合规范的AI服务
- **协议适配器模式**：支持多种LLM协议（OpenAI、Gemini等）
- **统一响应格式**：BaseResponse标准化所有API响应
- **请求链路追踪**：全链路trace_id支持问题定位
- **智能中间件系统**：统一异常处理、文件上传、认证拦截
- **文件处理能力**：支持multipart/form-data和base64两种文件上传方式

## 🏗️ 架构设计

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      App.py                                 │  ← 应用入口 (FastAPI + Lifespan)
│                  (统一路由管理)                              │
├─────────────────────────────────────────────────────────────┤
│               Authentication Layer                          │  ← 统一认证层
│  • JWT Token认证  • 中间件拦截  • Swagger UI支持            │     • Bearer Token验证
│  • 用户权限管理  • MongoDB存储  • 脚本化用户创建            │     • 请求拦截保护
├─────────────────────────────────────────────────────────────┤
│                  Service Registry                           │  ← 服务注册发现
│              (自动发现和管理服务生命周期)                    │
├─────────────────────────────────────────────────────────────┤
│    Chat Service      │  Document Service  │  Auth Service  │  ← 业务服务层 (继承BaseService)
│   (BaseService)      │  (BaseService)     │  (认证服务)    │     • 单轮/多轮对话
│   • qwen3-32B        │  • PDF解析         │  • 用户登录    │     • 流式/非流式响应
│   • qwen3-14B        │  • Word转换        │  • Token验证   │     • 协议适配器模式
├─────────────────────────────────────────────────────────────┤
│      Router Layer       │     Schema Layer                 │  ← 接口&数据层
│  • 统一BaseResponse     │  • Pydantic验证                  │     • HTTP路由定义
│  • 流式原始返回         │  • 类型安全                      │     • 数据模型定义
│  • 认证路由(/auth/*)   │  • 认证数据模型                  │     • JWT Payload验证
├─────────────────────────────────────────────────────────────┤
│     Handler Layer       │    Adapter Layer                 │  ← 业务逻辑&协议适配
│  • 纯业务逻辑          │  • OpenAI Protocol               │     • 与HTTP解耦
│  • 参数验证            │  • 多模型支持                    │     • 易于单元测试
│  • 认证业务处理        │  • 用户存储适配                  │     • MongoDB适配
├─────────────────────────────────────────────────────────────┤
│                    Core Modules                             │  ← 核心基础设施
│  (Config/Log/Exception/Middleware/Auth/Storage)             │     • 配置管理
│                                                             │     • 全局异常处理
└─────────────────────────────────────────────────────────────┘     • 智能中间件系统
                                                                      • 文件处理中间件
                                                                      • 认证中间件
                                                                      • 请求追踪中间件
                                                                      • 数据存储
```

### 设计模式说明

#### 1. **服务注册模式 (Service Registry Pattern)**
- 服务继承`BaseService`，实现标准化接口
- 注册器自动发现`services/{service_name}/service.py`
- 配置驱动：通过`services.yml`控制服务启用状态

#### 2. **协议适配器模式 (Protocol Adapter Pattern)**
- 抽象接口`LLMProtocolAdapter`屏蔽不同LLM API差异
- 工厂模式`ProtocolAdapterFactory`动态创建适配器
- 支持OpenAI协议的所有模型（Qwen、DeepSeek、Llama等）

#### 3. **分层职责模式 (Layered Responsibility)**
- **Schemas**: 数据验证和序列化，确保类型安全
- **Handlers**: 纯业务逻辑，与HTTP解耦，易于测试
- **Routers**: HTTP路由和响应格式化，统一BaseResponse
- **Service**: 服务生命周期管理和路由注册

#### 4. **统一认证模式 (Unified Authentication)**
- **JWT Token**: 无状态认证，支持分布式部署
- **中间件拦截**: 自动拦截请求验证，业务代码无感知
- **权限控制**: 基于用户权限的细粒度访问控制
- **脚本化管理**: 安全的用户创建和管理机制

#### 5. **智能中间件系统 (Smart Middleware System)**
- **统一异常处理**: 全局异常处理器统一转换为标准BaseResponse格式
- **文件处理中间件**: 智能处理multipart/form-data和base64文件上传
- **中间件执行顺序**: 洋葱模型，确保trace_id正确传播
- **职责分离**: 中间件专注业务逻辑，异常处理器专注响应格式化

## 📂 目录结构

```
ai-backend-services/
├── app.py                              # 🚀 应用入口 (FastAPI主应用)
├── 📁 core/                           # 🔧 核心基础设施
│   ├── auth/                          # 认证模块 (JWT Token, 用户管理)
│   ├── config/                        # 配置管理 (加载验证, 错误码定义)
│   ├── exceptions/                    # 异常处理 (全局异常处理器, 业务异常定义)
│   ├── middleware/                    # 中间件 (认证, 文件处理, 日志, 请求追踪)
│   ├── schemas/                       # 通用数据模型 (BaseResponse, 文件模型)
│   └── storage/                       # 数据存储 (MongoDB适配器)
├── 📁 configs/                        # ⚙️ 统一配置管理
│   ├── app/                          # 应用配置 (数据库, 认证, 日志)
│   ├── services/                     # 服务配置 (启用状态, 端点配置)
│   └── llm_providers/                # LLM提供商配置 (模型参数)
├── 📁 services/                       # 🏢 AI服务模块
│   ├── base.py                       # BaseService抽象基类
│   ├── registry.py                   # 服务注册发现机制
│   ├── chat/                         # 🤖 Chat服务 (单轮/多轮对话)
│   └── document/                     # 📄 Document服务 (PDF解析, 表格提取)
├── 📁 scripts/                        # 🛠️ 管理脚本
│   └── create_auth_user.py           # 认证用户创建脚本
├── 📁 logs/                          # 📝 日志文件目录
├── requirements.txt                   # Python依赖
└── README.md                         # 项目文档
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置服务

#### 配置LLM模型 (`configs/llm_providers/openai.yml`)
```yaml
provider: qwen
models:
  - name: qwen3-32B
    base_url: http://your-model-host:port/v1
    api_key: your-api-key
  - name: qwen3-14B
    base_url: http://your-model-host:port/v1
    api_key: your-api-key
```

#### 配置服务启用 (`configs/services/services.yml`)
```yaml
services:
  enabled:
    - chat
    - document
    # - retrieval   # 暂未实现
  
  chat:
    enabled: true
    endpoints:
      chat: true      # 统一对话接口(根据history判断单轮/多轮)
      chat_stream: true  # 流式对话
    enabled_models:
      - qwen3-32B
      - qwen3-14B
  
  document:
    enabled: true
    endpoints:
      pdf_parser: true
      table_extract: true
      text_extract: true
    max_file_size: 52428800  # 50MB
```

### 3. 创建认证用户

平台采用JWT Token认证机制，需要先创建认证用户：

```bash
# 创建认证用户（使用basic权限模板）
python scripts/create_auth_user.py create <业务名称> --template basic

# 创建认证用户（使用admin权限模板）  
python scripts/create_auth_user.py create <业务名称> --template admin

# 创建认证用户（自定义权限）
python scripts/create_auth_user.py create <业务名称> --permissions chat.single_turn chat.multi_turn

# 查看所有认证用户
python scripts/create_auth_user.py list
```

**权限模板说明：**
- `basic`: 基础权限，包含单轮和多轮对话权限
- `admin`: 管理员权限，包含所有可用权限

**示例：**
```bash
# 为test_business创建基础权限用户
python scripts/create_auth_user.py create test_business --template basic

# 输出示例：
# ✅ 认证用户创建成功!
# 👤 用户名: test_business_auth_user
# 🔑 密码: 4yoVnMxHnLxNs2PZsUhJ1w
# 📜 权限列表: chat.single_turn, chat.multi_turn
```

### 4. 启动服务

```bash
python app.py
```

服务启动后可访问：
- **API文档**: http://localhost:19999/docs
- **健康检查**: http://localhost:19999/health
- **服务列表**: http://localhost:19999/services

### 5. 使用认证

```bash
# 1. 登录获取token
curl -X POST http://localhost:19999/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "test_business_auth_user", "password": "4yoVnMxHnLxNs2PZsUhJ1w"}'

# 2. 使用token访问受保护的API
curl -X GET http://localhost:19999/services \
  -H "Authorization: Bearer <返回的access_token>"
```

**Swagger UI认证：**
在API文档页面点击右上角"Authorize"按钮，输入JWT token即可测试所有接口。

## 📋 开发指南

### 新增AI服务开发流程

#### 第1步：创建服务目录结构
```bash
mkdir -p services/your_service/{adapters,}
touch services/your_service/{__init__.py,service.py,schemas.py,handlers.py,routers.py}
```

#### 第2步：定义数据模型 (`schemas.py`)
```python
from pydantic import BaseModel, Field
from typing import List, Optional

class YourServiceRequest(BaseModel):
    """服务请求模型"""
    input_data: str = Field(..., description="输入数据")
    options: Optional[dict] = Field(None, description="可选参数")

class YourServiceResponse(BaseModel):
    """服务响应模型"""
    result: str = Field(..., description="处理结果")
    metadata: Optional[dict] = Field(None, description="元数据")
```

#### 第3步：实现业务处理器 (`handlers.py`)
```python
from typing import Dict, Any
from loguru import logger
from .schemas import YourServiceRequest, YourServiceResponse

class YourServiceHandlers:
    """业务逻辑处理器 - 与HTTP解耦"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    async def initialize(self):
        """轻量级初始化，不进行耗时操作"""
        logger.info("YourService handlers初始化完成")
    
    async def process_request(self, request: YourServiceRequest, trace_id: str = None) -> YourServiceResponse:
        """处理业务请求"""
        logger.info(f"Processing request - TraceID: {trace_id}")
        
        # 实现具体业务逻辑
        result = await self._your_business_logic(request)
        
        return YourServiceResponse(result=result)
    
    async def _your_business_logic(self, request: YourServiceRequest):
        """具体业务实现"""
        # 在这里实现你的AI服务逻辑
        return "processed: " + request.input_data
```

#### 第4步：定义HTTP路由 (`routers.py`)
```python
import uuid
from fastapi import APIRouter, Request
from loguru import logger

from core.schemas.base_resp_model_define import BaseResponse
from core.exceptions import ValidationException, BaseBusinessException
from .schemas import YourServiceRequest

your_service_router = APIRouter()

@your_service_router.post("/process", response_model=BaseResponse)
async def process_data(request: YourServiceRequest, http_request: Request):
    """数据处理接口"""
    trace_id = str(uuid.uuid4())
    logger.info(f"Received request - TraceID: {trace_id}")
    
    try:
        # 从service_registry获取handlers
        service_registry = getattr(http_request.app.state, 'service_registry', None)
        service = service_registry.get_service('your_service') if service_registry else None
        handlers = service.handlers if service else None
        
        if not handlers:
            return BaseResponse.error(
                code=500,
                msg="服务未初始化",
                trace_id=trace_id
            )
        
        # 调用业务逻辑
        response = await handlers.process_request(request, trace_id)
        
        return BaseResponse.success(
            data=response.dict(),
            trace_id=trace_id
        )
        
    except ValidationException as e:
        return BaseResponse.error(code=400, msg=str(e), trace_id=trace_id)
    except BaseBusinessException as e:
        return BaseResponse.error(code=e.code, msg=e.message, trace_id=trace_id)
    except Exception as e:
        logger.error(f"Unexpected error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(code=500, msg="服务内部错误", trace_id=trace_id)
```

#### 第5步：创建服务主类 (`service.py`)
```python
from typing import Dict, Any
from fastapi import APIRouter
from loguru import logger

from services.base import BaseService
from .handlers import YourServiceHandlers
from .routers import your_service_router

class YourService(BaseService):
    """YourService服务主类"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.handlers = None
    
    def _get_service_name(self) -> str:
        return "your_service"
    
    def get_router(self) -> APIRouter:
        if not self.enabled:
            return APIRouter()
        return your_service_router
    
    async def initialize(self) -> None:
        if not self.enabled:
            logger.warning("YourService未启用")
            return
        
        self.handlers = YourServiceHandlers(self.config)
        await self.handlers.initialize()
        logger.info("YourService初始化成功")
    
    async def health_check(self) -> bool:
        if not self.enabled:
            return False
        return self.handlers is not None
```

#### 第6步：配置服务导出 (`__init__.py`)
```python
from .service import YourService
from .schemas import YourServiceRequest, YourServiceResponse

__all__ = ['YourService', 'YourServiceRequest', 'YourServiceResponse']
```

#### 第7步：添加服务配置
在`configs/services/services.yml`中添加：
```yaml
services:
  enabled:
    - chat
    - your_service  # 添加新服务
  
  your_service:
    enabled: true
    version: "1.0.0"
    endpoints:
      process: true
    # 其他服务特定配置...
```

#### 第8步：启动测试
```bash
python app.py
```

访问 http://localhost:19999/docs 查看自动生成的API文档。

### 开发规范

#### 响应格式规范

**非流式接口**：统一使用BaseResponse格式
```json
{
  "code": 0,
  "msg": "success",
  "data": { "具体业务数据" },
  "trace_id": "uuid",
  "timestamp": 1234567890.123
}
```

**流式接口**：返回原始chunk块，由业务方自行解析
```
data: {"content": "chunk内容", "finish_reason": null, "model": "qwen3-32B"}
data: {"content": "", "finish_reason": "stop", "model": "qwen3-32B"}
```

#### 错误处理规范

```python
# 参数验证错误
raise ValidationException("参数不能为空")

# 业务逻辑错误
raise BaseBusinessException(code=1001, message="业务处理失败")

# 系统异常会被全局异常处理器自动转换
```

#### 日志规范

```python
# 使用loguru，自动包含trace_id
logger.info(f"业务处理开始 - TraceID: {trace_id}")
logger.error(f"处理失败 - TraceID: {trace_id} | Error: {str(e)}")
```

## 🤖 Chat服务

### API接口

| 接口 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 统一对话 | POST | `/chat/chat` | 非流式对话(根据history自动判断单轮/多轮) |
| 流式对话 | POST | `/chat/chat-stream` | 流式对话(根据history自动判断单轮/多轮) |
| 模型列表 | GET | `/chat/models` | 获取启用的模型列表 |

### 请求示例

```bash
# 单轮对话 (history为空)
curl -X POST "http://localhost:19999/chat/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_token>" \
  -d '{
    "query": "你好",
    "history": [],
    "model": "qwen3-32B",
    "temperature": 0.7,
    "max_tokens": 2000
  }'

# 多轮对话 (包含history)
curl -X POST "http://localhost:19999/chat/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_token>" \
  -d '{
    "query": "继续刚才的话题",
    "history": [
      {"role": "user", "content": "介绍一下人工智能"},
      {"role": "assistant", "content": "人工智能是..."}
    ],
    "model": "qwen3-32B"
  }'
```

### 协议适配器扩展

新增LLM协议支持：

```python
# services/chat/adapters/your_protocol_adapter.py
class YourProtocolAdapter(LLMProtocolAdapter):
    async def chat_completion(self, messages, temperature, max_tokens, **kwargs):
        # 实现你的协议调用逻辑
        pass

# services/chat/adapters/__init__.py
ProtocolAdapterFactory.register_adapter('your_protocol', YourProtocolAdapter)
```

## 🔧 配置管理

### 配置文件结构
- **app.yml**: 应用基础配置（日志、数据库等）
- **services/services.yml**: 服务启用和业务配置
- **llm_providers/*.yml**: LLM提供商和模型配置

### 配置加载优先级
1. YAML配置文件
2. 环境变量覆盖
3. 启动时配置验证

### 配置热更新
服务运行时可通过修改配置文件实现部分配置的热更新。

## 🚀 部署指南

### Docker部署(TODO)

## 📊 监控和运维

### 健康检查
- **应用级**: `/health` - 检查应用和所有服务状态
- **服务级**: 每个服务独立健康检查机制

### 日志监控
- 结构化日志输出
- 全链路trace_id追踪
- 请求处理时间统计

### 开发规范
- 遵循现有的架构模式
- 继承BaseService实现新服务
- 使用BaseResponse统一响应格式
- 添加完整的类型注解
- 编写单元测试

## 📝 更新日志

### v1.1.0 (当前版本)
- ✅ 统一AI服务平台架构
- ✅ Chat服务完整实现(统一单轮/多轮对话接口)
- ✅ Document服务完整实现(PDF解析、表格提取、文本提取)
- ✅ 智能文件处理中间件(支持multipart和base64)
- ✅ 统一异常处理机制(中间件+全局处理器)
- ✅ 服务注册发现机制
- ✅ 协议适配器模式
- ✅ 统一响应格式和全链路追踪

## 📄 Document服务

### API接口

| 接口 | 方法 | 路径 | 说明 |
|------|------|------|------|
| PDF解析 | POST | `/document/pdf-parser` | 解析PDF文档内容 |
| 批量PDF解析 | POST | `/document/pdf-parser-batch` | 批量解析PDF任务 |
| 查询解析状态 | GET | `/document/query-pdf-parser-task/{pdf_parser_batch_task_id}` | 查询批量解析任务状态 |
| 表格提取 | POST | `/document/table-extract` | 从文档中提取表格(HTML格式) |
| 文本提取 | POST | `/document/text-extract` | 从文档中提取纯文本 |
| 文本提取批量 | POST | `/document/text-extract-batch` | 批量文本提取任务 |
| 文档转换 | POST | `/document/convert` | 文档格式转换 |

### 文件上传支持

**方式1: multipart/form-data**
```bash
# 使用表单上传文件
curl -X POST "http://localhost:19999/document/pdf-parser" \
  -H "Authorization: Bearer <your_token>" \
  -F "input_type=file" \
  -F "file=@document.pdf" \
  -F "filename=document.pdf" \
  -F "output_format=text"
```

**方式2: base64编码**
```bash
# 使用base64编码上传
curl -X POST "http://localhost:19999/document/pdf-parser" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_token>" \
  -d '{
    "input_type": "base64",
    "filename": "document.pdf",
    "file_data": "<base64_encoded_file_content>",
    "output_format": "text"
  }'
```

### 中间件架构

**智能文件处理中间件**:
- 自动检测文件上传类型(multipart/base64)
- 统一文件处理逻辑，创建临时文件
- 自动文件清理机制
- 文件大小限制和验证

**统一异常处理**:
- 中间件抛出HTTPException或业务异常
- 全局异常处理器统一转换为BaseResponse格式
- 职责分离: 中间件专注业务逻辑，异常处理器专注响应格式化

### 规划中功能
- 🔄 Retrieval服务 (向量检索)
- 🔄 Multimodal服务 (图像/音频处理)