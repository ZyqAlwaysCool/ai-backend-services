# MCP 能力域技术方案（初稿）

## 背景与目标
- 背景：平台需支持业务方注册自建 MCP 工具，并在请求时按传入的工具白名单动态组织 Agent 调用，结果流式返回；平台不感知业务逻辑，但需完整审计链路。
- 目标：提供独立的 MCP 能力域，支持工具注册/查询/同步、`agent_mode` 多策略编排、流式输出与审计留痕，按 `user_id` 隔离。

## 关键设计
- 独立服务：新增 `services/mcp`，路由与存储与既有服务隔离。
- 工具元数据：调用 MCP 服务器提供的工具信息接口（参考 `examples/mcp_client.py`），拉取 `desc/schema` 等信息；apikey 按 `user_id` 隔离存储，加密或脱敏。
- 动态编排：请求参数带 `agent_mode`，根据工具白名单动态装配一次性编排器，运行时仅允许调用本次白名单工具。
- 流式协议：自定义 `McpStreamChunk`，统一事件类型，SSE 输出 `data: {json}\n\n`。
- 审计：落库 `mcp_runs` 与 `mcp_run_steps`，记录调用顺序、耗时、结果摘要、错误与终止原因，可回放/统计。

## 接口与协议（草案）
- 工具管理
  - `POST /mcp/tools/register`：`tool_name, api_key`，后台自动拉取工具信息并存库（按 user_id）。
  - `POST /mcp/tools/sync`：拉取/刷新指定或全量工具元数据。
  - `GET /mcp/tools/list`：按 user_id 查看可用工具。
- 问答入口
  - `POST /mcp/ask`：
    - 入参：`query`、`prompt`、`tool_names: List[str]`、`agent_mode`（`single_tool`|`plan_react`|`supervisor`）、`stream`（默认 true）。
    - 仅允许调用 `tool_names` 与用户注册且启用的工具交集。
- 流式事件（McpStreamChunk）
  - 公共字段：`type`、`trace_id`、`agent_mode`、`ts`
  - 事件类型：
    - `delta`：模型最终回答的增量文本（仅 stream=true 时输出）
    - `tool_start`：`{tool_name, step, input}`
    - `tool_end`：`{tool_name, step, output, latency_ms, status}`
    - `final`：`{content}`
    - `error`：`{message, detail?, step?, tool_name?}`

## Agent 编排模式
- `single_tool`（默认）
  - 场景：单工具即可满足需求。流程：LLM 选定一个工具+参数 → 调用一次 → 汇总回答；仅一轮，时延最低。
- `plan_react`
  - 场景：需要多步但不必逐步推理。流程：先生成计划（若干步，每步工具+参数）→ 按计划顺序调用工具 → 汇总回答；计划以 `plan` 事件产出，便于审计。
- `supervisor`（原先的 multi-agent）
  - 场景：需要逐步决策、根据结果调整。流程：Supervisor 循环决策 `CALL/FINISH`，多轮调用工具，直至终止或超限。

## 运行时流程（通用骨架）
1. 鉴权拿 user_id → 校验 `tool_names`。
2. 从存储读取工具元数据与 apikey，构建 `tool_bundle`，必要时调用 MCP 服务器刷新元数据。
3. `OrchestratorFactory` 按 `agent_mode` 创建编排器实例，加载限流/超时配置。
4. 编排器产生事件流 → handlers 转换为 SSE，事件并行写入 `mcp_run_store`。
5. 达到终止条件（FINISH、步数/时长上限、错误终止）后输出 `final`/`error`。

## 存储设计（独立表）
- `mcp_tools`（按 user_id 隔离）：`user_id` + `tool_name` 唯一；字段：`desc`、`schema`、`api_key_cipher`、`status`、`source_server`、`updated_at`。
- `mcp_runs`：`trace_id`、`user_id`、`agent_mode`、`query`、`prompt`、`tool_names`、`limits`、`status`、`finish_reason`、`started_at`、`ended_at`、`total_tokens?`。
- `mcp_run_steps`：`trace_id`、`step`、`step_type`(llm|tool|plan)、`tool_name?`、`input_digest`、`output_digest`、`latency_ms`、`status`、`error?`。

## 配置（默认值见 `configs/mcp/mcp.yml`）
- 全局：`enabled`、`default_agent_mode`（默认 `single_tool`）、`allowed_agent_modes`、`max_tools_per_request`、`max_steps`、`max_total_duration_ms`、`per_tool_timeout_ms`、`per_llm_timeout_ms`。
- 缓存：工具元数据/客户端 TTL。
- 模式细项：保持轻量，仅保留 `supervisor.max_rounds/allow_retry_on_tool_error`，其余模式复用通用 limits。
- LLM：OpenAI 兼容协议模型配置 `model_name/base_url/api_key/temperature/max_tokens/timeout`。
- 重试：`retry.max_attempts`、`backoff_ms`。

## 风险与缓解
- 成本与上下文膨胀：限制工具数量、步数、时长，对工具描述做摘要，截断历史仅保留决策要点。
- 调度不稳定：明确终止信号与输出格式，异常输出重试一次后中止。
- 工具失败拖慢：单步超时 + 熔断；失败结果结构化返回，交由编排器决策继续/终止。
- 安全：严格白名单校验，不在日志写入 apikey，全链路 trace_id 便于审计。

## 流式异常处理补充
- `handlers.ask` 创建编排流后立即校验是否满足异步迭代协议，不满足直接返回业务错误，避免路由层拿到空生成器。
- 流迭代过程中若编排器内部异常，捕获后落库 `status=error` 并输出首个 `error` 事件（含 `detail`），`_stream_wrapper` 仅负责序列化，不再抛出 TypeError。
- `_stream_wrapper` 入口增加生成器判空保护，首帧输出 error 事件而非报错日志，保证客户端收到结构化错误提示。

## LLM 调用配置
- `configs/mcp/mcp.yml` 的 `llm.api_key` 支持 `${ENV_NAME}` 占位或直接填写密钥，若为空则自动读取 `MCP_LLM_API_KEY`，再回退 `OPENAI_API_KEY`。
- 未找到有效密钥时直接抛出业务异常，提示明确配置或注入环境变量。

## 工具调用配置
- 编排器调用工具时，`ToolExecutor` 优先使用工具元信息中的 `meta.mcp_server_host/mcp_server_port/mcp_server_apikey` 建立 MCPClient；若缺失则回退服务配置中的 `default_host/default_port`（支持 `host_env/port_env` 环境变量），apikey 回退 `tool.api_key` 或 `MCP_SERVER_API_KEY`。
- 基础信息缺失将直接返回业务异常，避免 TypeError 并为客户端提供结构化错误。

## 上下文传递
- Supervisor 模式在 LLM 决策时不再截断历史执行结果，直接传递完整 `executed` JSON，确保表名/字段等关键信息不被省略。
- SSE 事件中的 `output_digest` 仍做摘要，仅用于日志/前端展示，不影响 LLM 决策上下文。

## Supervisor 决策提示
- 决策提示中包含每个工具的描述与 `input_schema`，并明确要求严格按 schema 字段名填参（如 `tableName` 而非 `table_name`），避免模型因字段名错误导致调用失败。

## 审计与查询
- 运行与步骤存储：`trace_id` 按 `user_id` 隔离，步骤表带 `user_id`，可按 `mcp_agent_trace_id + user_id` 查询。
- 新增接口 `GET /mcp/ask/trace?mcp_agent_trace_id=...`，返回 run 记录与步骤列表。
- 日志前缀 `mcp_agent_trace_` 记录 query/prompt/trace_id，用于排障审计。
- 审计步骤字段：`input`/`output` 存工具完整入参/出参，`input_digest`/`output_digest` 字段已弃用。

## ask 接口返回
- 不再向客户端输出完整链路事件；若 `stream=true`，仅输出最终结果的 SSE 事件；若 `stream=false`，返回非流式 JSON（最终结果）。
- 完整链路可通过审计查询接口获取。
- `stream=true` 时，最终回答通过 LLM 流式生成，输出若干 `delta` 事件后再输出 `final`；`stream=false` 直接返回最终结果 JSON。

## 后续动作
- 如实现与文档有差异需同步更新本文件。 

## 当前实现状态
- 已新增独立的 `services/mcp` 目录、路由/handlers/service，支持工具注册/同步、提问流式接口、审计存储。
- 已提供三种编排模式：`single_tool`（默认）、`plan_react`、`supervisor`，均基于 PocketFlow，配置于 `configs/mcp/mcp.yml`，可实际调用 MCP 工具（默认 `http://10.10.20.69:28080/sse`，可环境变量覆盖）。
- 支持重试策略、工具白名单校验、时长/超时限制（max_total_duration_ms、per_tool_timeout_ms、per_llm_timeout_ms）、流式事件（plan/tool_start/tool_end/delta/final/error 以及步骤审计）；apikey 明文存库但日志不打印敏感值。
- 待优化：模型输出格式健壮性、更多安全校验、指标与回放接口。 
