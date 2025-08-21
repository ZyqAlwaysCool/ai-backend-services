# AI服务平台

## 🎯 项目简介

本项目是一个**统一的AI能力集服务平台**，采用单体应用 + 模块化服务的架构设计，将多个AI服务（Chat、Document、Retrieval、Multimodal等）集成在一个FastAPI应用中。通过配置驱动和服务注册机制，实现AI服务的统一管理、快速开发和灵活扩展。

### 🚀 核心优势

- **统一服务平台**：多个AI服务统一部署管理，单一入口
- **快速启动**：移除启动时健康检查，1秒内完成服务初始化
- **配置驱动**：YAML配置控制服务启用状态和行为
- **服务注册机制**：自动发现和注册符合规范的AI服务
- **协议适配器模式**：支持多种LLM协议（OpenAI、Qwen、DeepSeek等）
- **统一响应格式**：BaseResponse标准化所有API响应
- **请求链路追踪**：全链路trace_id支持问题定位
- **懒加载设计**：配置错误在实际调用时报错，不阻塞启动

## 🏗️ 架构设计

### 整体架构图

```
┌─────────────────────────────────────────┐
│                App.py                   │  ← 应用入口 (FastAPI + Lifespan)
│            (统一路由管理)                │
├─────────────────────────────────────────┤
│            Service Registry             │  ← 服务注册发现
│         (自动发现和管理服务生命周期)      │
├─────────────────────────────────────────┤
│  Chat Service    │ Document Service    │  ← 业务服务层 (继承BaseService)
│  (BaseService)   │  (BaseService)      │     • 单轮/多轮对话
│     • qwen3-32B  │     • PDF解析       │     • 流式/非流式响应
│     • qwen3-14B  │     • Word转换      │     • 协议适配器模式
├─────────────────────────────────────────┤
│    Router Layer   │   Schema Layer     │  ← 接口&数据层
│  • 统一BaseResponse │ • Pydantic验证    │     • HTTP路由定义
│  • 流式原始返回     │ • 类型安全        │     • 数据模型定义
├─────────────────────────────────────────┤
│   Handler Layer   │  Adapter Layer     │  ← 业务逻辑&协议适配
│  • 纯业务逻辑      │ • OpenAI Protocol  │     • 与HTTP解耦
│  • 参数验证        │ • 多模型支持       │     • 易于单元测试
├─────────────────────────────────────────┤
│              Core Modules               │  ← 核心基础设施
│      (Config/Log/Exception/Middleware)  │     • 配置管理
│                                         │     • 异常处理
└─────────────────────────────────────────┘     • 中间件支持
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

## 📂 目录结构

```
ai-backend-services/
├── app.py                              # 🚀 应用入口 (FastAPI主应用)
├── 📁 core/                           # 🔧 核心基础设施
│   ├── config/                        # 配置管理
│   │   ├── config_center.py          # 配置加载和验证
│   │   └── error_codes.py            # 统一错误码定义
│   ├── logging/                       # 日志系统
│   │   └── logger.py                 # 结构化日志配置
│   ├── exceptions/                    # 异常处理
│   │   └── exceptions.py             # 全局异常处理器
│   ├── middleware/                    # 中间件
│   │   └── middleware.py             # 请求追踪和日志中间件
│   └── schemas/                       # 通用数据模型
│       └── base_resp_model_define.py  # BaseResponse统一响应格式
├── 📁 configs/                        # ⚙️ 统一配置管理
│   ├── app.yml                       # 应用基础配置
│   ├── services/                     # 服务配置
│   │   └── services.yml              # 服务启用和端点配置
│   └── llm_providers/                # LLM提供商配置
│       └── openai.yml                # OpenAI兼容模型配置
├── 📁 services/                       # 🏢 AI服务模块
│   ├── base.py                       # BaseService抽象基类
│   ├── registry.py                   # 服务注册发现机制
│   └── chat/                         # 🤖 Chat服务示例
│       ├── __init__.py               # 模块导出
│       ├── service.py                # ChatService主类
│       ├── schemas.py                # 数据模型定义
│       ├── handlers.py               # 业务逻辑处理
│       ├── routers.py                # HTTP路由定义
│       └── adapters/                 # 协议适配器
│           ├── base.py               # 适配器抽象接口
│           └── openai_adapter.py     # OpenAI协议适配器
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
    # - document    # 暂未实现
    # - retrieval   # 暂未实现
  
  chat:
    enabled: true
    endpoints:
      single_turn_chat: true
      multi_turn_chat: true
    enabled_models:
      - qwen3-32B
      - qwen3-14B
```

### 3. 启动服务

```bash
python app.py
```

服务启动后可访问：
- **API文档**: http://localhost:19999/docs
- **健康检查**: http://localhost:19999/health
- **服务列表**: http://localhost:19999/services

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

## 🤖 Chat服务示例

当前已实现的Chat服务包含以下功能：

### API接口

| 接口 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 单轮对话 | POST | `/chat/single_turn_chat` | 非流式单轮对话 |
| 多轮对话 | POST | `/chat/multi_turn_chat` | 非流式多轮对话 |
| 单轮流式 | POST | `/chat/single_turn_chat_stream` | 流式单轮对话 |
| 多轮流式 | POST | `/chat/multi_turn_chat_stream` | 流式多轮对话 |
| 模型列表 | GET | `/chat/models` | 获取启用的模型列表 |

### 请求示例

```bash
# 单轮对话
curl -X POST "http://localhost:19999/chat/single_turn_chat" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "你好",
    "model": "qwen3-32B",
    "temperature": 0.7,
    "max_tokens": 2000
  }'

# 多轮对话
curl -X POST "http://localhost:19999/chat/multi_turn_chat" \
  -H "Content-Type: application/json" \
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

### Docker部署

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 19999

CMD ["python", "app.py"]
```

### 生产环境配置

```yaml
# configs/app.yml
log_level: INFO
log_retention: "7 days"

# 环境变量覆盖
export LOG_LEVEL=WARNING
export MONGO_HOST=production-mongo-host
```

## 📊 监控和运维

### 健康检查
- **应用级**: `/health` - 检查应用和所有服务状态
- **服务级**: 每个服务独立健康检查机制

### 日志监控
- 结构化日志输出
- 全链路trace_id追踪
- 请求处理时间统计

### 性能监控
- 启动时间优化：1秒内完成初始化
- 懒加载设计：避免启动时耗时操作
- 内存占用监控

## 🤝 贡献指南

1. Fork项目
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 开启Pull Request

### 开发规范
- 遵循现有的架构模式
- 继承BaseService实现新服务
- 使用BaseResponse统一响应格式
- 添加完整的类型注解
- 编写单元测试

## 📝 更新日志

### v1.0.0 (当前版本)
- ✅ 统一AI服务平台架构
- ✅ Chat服务完整实现
- ✅ 服务注册发现机制
- ✅ 协议适配器模式
- ✅ 快速启动优化
- ✅ 统一响应格式
- ✅ 全链路追踪

### 规划中功能
- 🔄 Document服务 (PDF/Word处理)
- 🔄 Retrieval服务 (向量检索)
- 🔄 Multimodal服务 (图像/音频处理)
- 🔄 监控面板和metrics
- 🔄 配置管理界面

## 📞 技术支持

如有问题或建议，请：
1. 查看项目文档和示例代码
2. 提交Issue描述问题
3. 参与Discussion讨论

---

**AI服务平台** - 让AI服务开发更简单、更统一、更高效！ 🚀