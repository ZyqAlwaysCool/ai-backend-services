# PocketFlow 版 Supervisor 编排设计

## 目标与范围
- 用 PocketFlow 的节点/流概念重写现有 `supervisor_multi_agent` 编排，行为对齐原有 Supervisor（相同 `agent_mode`，对外协议不变）。
- 只改内部实现：新增 `services/mcp/agents/supervisor_pocketflow.py`，在 `__init__.py` 注册；不新增或改动 `AgentMode`。

## 方案对比
1. **保留旧循环，PocketFlow 只作为壳子**：改动小，但 PocketFlow 价值低、后续插桩不便。
2. **用 PocketFlow AsyncFlow 拆成节点**：决策/执行/汇总分层，事件收集统一由节点推送，流程清晰便于扩展。

选择方案 2：结构可视、后续新增节点（如风险审计、输出修正）无需改主循环。

## 节点与流转
```
Decide(action=CALL|FINISH|错误) -->[CALL] Execute -->[decide] Decide
Decide -->[FINISH] Summarize
Execute -->[error] Summarize
```
- **DecideNode**：调用 LLM 读取 `executed` 历史决定 `CALL/FINISH`。超时或步数超限直接产出 `error` 事件并跳转汇总。
- **ExecuteNode**：调用 MCP 工具（带重试）；落地 `tool_start/tool_end` 事件，异常落地 `tool_end status=error` 后进入汇总。
- **SummarizeNode**：按配置生成最终回答，`stream_final=true` 时推送 `delta`，最后产出 `final`。

事件映射：`plan`（工具列表）→`tool_start/tool_end`→`delta`（可选）→`final`，中途任何异常会额外产出 `error` 事件但仍进入最终汇总。

## 限制与容错
- 步数：`limits.max_steps` 控制决策轮次；超限立刻产出 `error` 并进入汇总。
- 时长：每轮决策前检查 `_time_exceeded`，触发后产出 `error`。
- 超时：`per_llm_timeout_ms`、`per_tool_timeout_ms` 透传到 LLM/工具调用；调用失败落地错误并进入汇总。
- 工具校验：若模型返回的 `tool_name` 不在白名单，产出 `error`，停止继续调用。

## 使用方式
- 对外接口与 `agent_mode` 不变，直接通过 `services/mcp/agents/__init__.py` 自动注册 PocketFlow 版。
- 代码自动尝试导入安装的 `pocketflow`，若未安装则回退使用仓库内 `docs/mcp/PocketFlow/pocketflow`。

## 后续可扩展点
- 在节点间新增审计/风控节点（如输出安全检测）。
- 在 DecideNode 增加基于执行结果摘要的截断逻辑，减少上下文开销。
