# AI能力服务平台

一个基于 FastAPI 的统一 AI 服务平台，集成了对话、文档处理、向量检索等多种 AI 能力。

## 项目介绍

这是一个模块化的 AI 服务后端，采用单体应用架构，通过服务注册机制统一管理多个 AI 服务模块。每个服务都可以独立开发和配置，同时共享统一的认证、异常处理、配置管理等基础设施。

**主要特性：**
- JWT 认证体系，支持细粒度权限控制
- 配置驱动的服务管理，可动态启用/禁用服务
- 统一的请求响应格式和异常处理
- 支持流式和非流式响应
- 完整的请求链路追踪

**当前服务模块：**
- **Chat Service**: 基于大语言模型的对话服务，支持单轮和多轮对话，适配dify等低代码平台api
- **Document Service**: 文档处理服务，支持 PDF 解析、格式转换、文本提取等
- **Retrieval Service**: 向量检索服务，支持知识库构建和语义搜索

## 架构介绍

### 整体架构

```
┌─────────────────────────────────────┐
│              FastAPI App            │  应用入口
├─────────────────────────────────────┤
│          Service Registry           │  服务注册发现
├─────────────┬─────────────┬─────────┤
│     Chat    │   Document  │Retrieval│  业务服务层
├─────────────┼─────────────┼─────────┤
│   Handlers  │   Routers   │ Schemas │  业务逻辑层
├─────────────┴─────────────┴─────────┤
│           Core Modules              │  基础设施层
│ Auth│Config│Exception│Middleware    │
└─────────────────────────────────────┘
```

### 核心设计模式

- **服务注册模式**: 自动发现和注册符合规范的服务模块
- **协议适配器模式**: 统一不同 LLM 提供商的 API 接口
- **分层职责**: Schemas → Handlers → Routers → Service，职责分离
- **配置驱动**: 通过 YAML 配置控制服务行为

### 目录结构

```
├── app.py                    # 应用入口
├── core/                     # 核心基础设施
│   ├── auth/                 # JWT 认证
│   ├── config/               # 配置管理
│   ├── exceptions/           # 异常处理
│   └── middleware/           # 中间件
├── services/                 # 业务服务
│   ├── chat/                 # 对话服务
│   ├── document/             # 文档服务
│   └── retrieval/            # 检索服务
└── configs/                  # 配置文件
```

## 快速开始

### 1. 环境准备

```bash
# 安装依赖
pip install -r requirements.txt

# 启动应用
python -m app
```
除了python的依赖库外, 还需要额外配置依赖项:
- mongodb
- redis
- qdrant

若非docker部署, 需自行找安装教程. 若使用docker部署, 可参考docker-compose.yml, 里面有各依赖项的基础镜像.

### 2. 用户认证

本平台需要 JWT Token 认证才能访问服务接口。

**创建用户**
通过/auth/register接口注册用户

**获取 Token：**
```bash
curl -X POST "http://localhost:20000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "your_username", "password": "your_password"}'
```

返回的 `access_token` 用于后续 API 调用。

### 3. 使用服务
**访问 Swagger 文档：**
访问 `http://localhost:20000/docs`，点击右上角 "Authorize" 按钮，输入 `Bearer your_token` 进行认证。

**调用 API 示例：**
```bash
# 对话服务
curl -X POST "http://localhost:20000/chat/completion" \
  -H "Authorization: Bearer your_token" \
  -H "Content-Type: application/json" \
  -d '{"query": "你好", "model": "qwen3-32B"}'
```

### 4. 配置说明

主要配置文件在 `configs/` 目录：
- `configs/services/services.yml`: 服务模块配置
- `configs/llm_providers/openai.yml`: LLM 提供商配置
可以通过修改配置文件来启用/禁用服务或调整参数。

retrieval服务需要额外下载模型:
- hanlp
- Qwen3-Embedding-0__6B