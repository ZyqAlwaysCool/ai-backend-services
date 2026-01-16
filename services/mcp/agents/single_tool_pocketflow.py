'''
Description: 单轮工具编排器
Author: zyq
Date: 2025-12-24 09:56:50
LastEditors: zyq
LastEditTime: 2025-12-24 15:01:34
'''

import asyncio
import json
import time
from typing import Any, AsyncGenerator, Dict, List

from services.mcp.agents.base import BaseOrchestrator, OrchestratorFactory
from services.mcp.agents.stream_models import StreamEvent
from services.mcp.schemas import AgentMode
from services.mcp.tools.tool_executor import ToolExecutor
from pocketflow import AsyncFlow, AsyncNode


class _PlanNode(AsyncNode):
    """单轮计划节点：仅选择一次工具并给出入参"""

    def __init__(self, orchestrator, event_queue, tool_map, per_llm_timeout, start_ts):
        super().__init__()
        self.orchestrator = orchestrator
        self.event_queue = event_queue
        self.tool_map = tool_map
        self.per_llm_timeout = per_llm_timeout
        self.start_ts = start_ts

    async def prep_async(self, shared: Dict[str, Any]):
        self.shared = shared
        if self.orchestrator._time_exceeded(self.start_ts):
            await self.event_queue.put(
                StreamEvent(
                    type="error",
                    trace_id=self.orchestrator.trace_id,
                    agent_mode=self.orchestrator.agent_mode.value,
                    content="超出总执行时长限制",
                    step=len(shared["executed"]) + 1
                )
            )
            shared["abort"] = True
        return None

    async def exec_async(self, _):
        if self.shared.get("abort"):
            return {"action": "ABORT"}
        decision = await self.orchestrator._retry_call(
            self.orchestrator._decide_single_call,
            timeout_ms=self.per_llm_timeout
        )
        return decision

    async def post_async(self, shared: Dict[str, Any], prep_res, decision):
        if shared.get("abort"):
            return "error"
        tool_name = decision.get("tool_name")
        args = decision.get("args", {})
        if not tool_name or tool_name not in self.tool_map:
            await self.event_queue.put(
                StreamEvent(
                    type="error",
                    trace_id=self.orchestrator.trace_id,
                    agent_mode=self.orchestrator.agent_mode.value,
                    content=f"模型选择的工具不在白名单: {tool_name}",
                    step=len(shared["executed"]) + 1,
                    detail={"decision": decision}
                )
            )
            shared["abort"] = True
            return "error"
        shared["curr_tool"] = tool_name
        shared["curr_args"] = args
        await self.event_queue.put(
            StreamEvent(
                type="plan",
                trace_id=self.orchestrator.trace_id,
                agent_mode=self.orchestrator.agent_mode.value,
                detail={"mode": "single_tool", "tool": tool_name, "args": args},
                step=0
            )
        )
        return "call"


class _ExecuteNode(AsyncNode):
    """执行节点：调用选定工具"""

    def __init__(self, orchestrator, event_queue, tool_map, per_tool_timeout):
        super().__init__()
        self.orchestrator = orchestrator
        self.event_queue = event_queue
        self.tool_map = tool_map
        self.per_tool_timeout = per_tool_timeout

    async def prep_async(self, shared: Dict[str, Any]):
        tool_name = shared.get("curr_tool")
        args = shared.get("curr_args", {})
        if shared.get("abort") or not tool_name:
            return None
        step = len(shared["executed"]) + 1
        await self.event_queue.put(
            StreamEvent(
                type="tool_start",
                trace_id=self.orchestrator.trace_id,
                agent_mode=self.orchestrator.agent_mode.value,
                tool_name=tool_name,
                step=step,
                input=args
            )
        )
        return tool_name, args

    async def exec_async(self, inputs):
        if not inputs:
            return {"__skip__": True}
        tool_name, args = inputs
        executor = ToolExecutor(self.tool_map[tool_name], self.orchestrator.server_cfg)
        return await self.orchestrator._retry_call(
            executor.call,
            args,
            timeout_ms=self.per_tool_timeout
        )

    async def exec_fallback_async(self, inputs, exc):
        return {"__error__": str(exc)}

    async def post_async(self, shared: Dict[str, Any], prep_res, exec_res):
        tool_name = None
        args = {}
        if prep_res:
            tool_name, args = prep_res
        step = len(shared["executed"]) + 1
        if not prep_res or exec_res.get("__error__"):
            shared["executed"].append({
                "tool_name": tool_name,
                "args": args,
                "error": exec_res.get("__error__") if exec_res else "执行前已中止"
            })
            await self.event_queue.put(
                StreamEvent(
                    type="tool_end",
                    trace_id=self.orchestrator.trace_id,
                    agent_mode=self.orchestrator.agent_mode.value,
                    tool_name=tool_name,
                    step=step,
                    output=exec_res.get("__error__") if exec_res else "执行前已中止",
                    status="error",
                    detail={"error": exec_res.get("__error__")} if exec_res else {"error": "执行前已中止"}
                )
            )
            shared["abort"] = True
            return "summarize"
        shared["executed"].append({
            "tool_name": tool_name,
            "args": args,
            "result": exec_res.get("result", {})
        })
        await self.event_queue.put(
            StreamEvent(
                type="tool_end",
                trace_id=self.orchestrator.trace_id,
                agent_mode=self.orchestrator.agent_mode.value,
                tool_name=tool_name,
                step=step,
                output=exec_res.get("result", {}),
                latency_ms=exec_res.get("latency_ms"),
                status="success"
            )
        )
        return "summarize"


class _SummarizeNode(AsyncNode):
    """汇总节点：生成最终回答并产出 delta/final 事件"""

    def __init__(self, orchestrator, event_queue, per_llm_timeout):
        super().__init__()
        self.orchestrator = orchestrator
        self.event_queue = event_queue
        self.per_llm_timeout = per_llm_timeout

    async def prep_async(self, shared: Dict[str, Any]):
        return shared.get("executed", [])

    async def exec_async(self, executed: List[Dict[str, Any]]):
        step = len(executed) + 1
        if self.orchestrator.stream_final:
            parts: List[str] = []
            async for chunk in self.orchestrator._summarize_stream(executed, timeout_ms=self.per_llm_timeout):
                parts.append(chunk)
                await self.event_queue.put(
                    StreamEvent(
                        type="delta",
                        trace_id=self.orchestrator.trace_id,
                        agent_mode=self.orchestrator.agent_mode.value,
                        content=chunk,
                        step=step
                    )
                )
            return "".join(parts)
        return await self.orchestrator._summarize(executed, timeout_ms=self.per_llm_timeout)

    async def post_async(self, shared: Dict[str, Any], prep_res, answer: str):
        step = len(prep_res) + 1
        await self.event_queue.put(
            StreamEvent(
                type="final",
                trace_id=self.orchestrator.trace_id,
                agent_mode=self.orchestrator.agent_mode.value,
                content=answer,
                step=step
            )
        )


class SingleToolPocketflowOrchestrator(BaseOrchestrator):
    """PocketFlow 版单轮工具直连编排器"""

    def __init__(
        self,
        agent_mode: AgentMode,
        tool_bundle: List[Dict[str, Any]],
        limits: Dict[str, Any],
        trace_id: str,
        llm_adapter: Any,
        llm_params: Dict[str, Any],
        server_cfg: Dict[str, Any],
        retry_cfg: Dict[str, Any],
        query: str,
        prompt: str,
        stream_final: bool = False
    ):
        super().__init__(agent_mode, tool_bundle, limits, trace_id, llm_adapter, llm_params, server_cfg, retry_cfg, query, prompt, stream_final=stream_final)

    async def _decide_single_call(self, timeout_ms: int | None = None) -> Dict[str, Any]:
        tool_desc = "\n".join([
            f"- {item['tool_name']}: {item.get('description', '')} | 入参schema={json.dumps(item.get('input_schema', {}), ensure_ascii=False)}"
            for item in self.tool_bundle
        ])
        sys_prompt = (
            "你是工具选择助手。基于需求从给定工具中选择最合适的一个，并给出严格符合入参schema的参数。\n"
            "输出JSON：{\"tool_name\": \"...\", \"args\": {...}, \"reason\": \"...\"}"
        )
        user_prompt = (
            f"业务提示词：{self.prompt}\n"
            f"用户问题：{self.query}\n"
            f"可用工具：\n{tool_desc}\n"
            "请直接输出JSON，不要添加多余文本。"
        )
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt}
        ]
        resp = await self.llm_adapter.chat_completion(
            messages=messages,
            temperature=self.llm_params.get("temperature", 0.7),
            max_tokens=self.llm_params.get("max_tokens", 512),
            timeout_ms=timeout_ms
        )
        parsed = self._safe_json_loads(resp.answer)
        if not parsed or "tool_name" not in parsed:
            raise ValueError("单轮工具决策解析失败")
        return parsed

    async def _summarize(self, executed: List[Dict[str, Any]], timeout_ms: int | None = None) -> str:
        sys_prompt = "你是结果汇总助手，请基于工具调用结果输出简洁中文回答。"
        exec_text = json.dumps(executed, ensure_ascii=False)
        user_prompt = (
            f"业务提示词：{self.prompt}\n"
            f"用户问题：{self.query}\n"
            f"调用结果：{exec_text}\n"
            "请给出最终回答。"
        )
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt}
        ]
        resp = await self.llm_adapter.chat_completion(
            messages=messages,
            temperature=self.llm_params.get("temperature", 0.7),
            max_tokens=self.llm_params.get("max_tokens", 512),
            timeout_ms=timeout_ms
        )
        return resp.answer

    async def _summarize_stream(self, executed: List[Dict[str, Any]], timeout_ms: int | None = None):
        sys_prompt = "你是结果汇总助手，请基于工具调用结果输出简洁中文回答。"
        exec_text = json.dumps(executed, ensure_ascii=False)
        user_prompt = (
            f"业务提示词：{self.prompt}\n"
            f"用户问题：{self.query}\n"
            f"调用结果：{exec_text}\n"
            "请给出最终回答。"
        )
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt}
        ]
        async for chunk in self.llm_adapter.chat_completion_stream(
            messages=messages,
            temperature=self.llm_params.get("temperature", 0.7),
            max_tokens=self.llm_params.get("max_tokens", 512),
            timeout_ms=timeout_ms
        ):
            yield chunk

    async def _run_flow(self, shared: Dict[str, Any], event_queue: asyncio.Queue, start_ts: float):
        tool_map = self._tool_map()
        per_tool_timeout = self.limits.get("per_tool_timeout_ms")
        per_llm_timeout = self.limits.get("per_llm_timeout_ms")

        plan = _PlanNode(self, event_queue, tool_map, per_llm_timeout, start_ts)
        execute = _ExecuteNode(self, event_queue, tool_map, per_tool_timeout)
        summarize = _SummarizeNode(self, event_queue, per_llm_timeout)

        plan - "call" >> execute
        plan - "error" >> summarize
        execute - "summarize" >> summarize

        flow = AsyncFlow(start=plan)
        await flow.run_async(shared)

    async def run_stream(self) -> AsyncGenerator[StreamEvent, None]:
        tool_map = self._tool_map()
        max_tools = int(self.limits.get("max_tools_per_request", len(tool_map)))
        start_ts = time.time()
        final_sent = False

        if not tool_map:
            yield StreamEvent(
                type="error",
                trace_id=self.trace_id,
                agent_mode=self.agent_mode.value,
                content="本次请求无可用工具",
                step=0
            )
            return
        if len(tool_map) > max_tools:
            yield StreamEvent(
                type="error",
                trace_id=self.trace_id,
                agent_mode=self.agent_mode.value,
                content=f"本次请求工具数量超过限制({max_tools})",
                step=0
            )
            return

        event_queue: asyncio.Queue = asyncio.Queue()
        shared: Dict[str, Any] = {
            "executed": [],
            "abort": False
        }
        flow_task = asyncio.create_task(self._run_flow(shared, event_queue, start_ts))

        try:
            while True:
                if flow_task.done() and event_queue.empty():
                    break
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
                    if event.type == "final":
                        final_sent = True
                    yield event
                except asyncio.TimeoutError:
                    continue
        except Exception as exc:
            yield StreamEvent(
                type="error",
                trace_id=self.trace_id,
                agent_mode=self.agent_mode.value,
                content="单轮编排执行异常",
                step=len(shared["executed"]) + 1,
                detail={"error": str(exc)}
            )
        finally:
            if not flow_task.done():
                flow_task.cancel()
            error_from_flow = None
            try:
                await flow_task
            except Exception as exc:
                error_from_flow = exc
            if error_from_flow and not final_sent:
                yield StreamEvent(
                    type="error",
                    trace_id=self.trace_id,
                    agent_mode=self.agent_mode.value,
                    content="单轮编排执行异常",
                    step=len(shared["executed"]) + 1,
                    detail={"error": str(error_from_flow)}
                )


OrchestratorFactory.register(AgentMode.SINGLE_TOOL, SingleToolPocketflowOrchestrator)
