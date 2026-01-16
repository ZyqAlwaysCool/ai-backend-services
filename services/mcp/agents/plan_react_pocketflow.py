'''
Description: 计划+执行的编排器
Author: zyq
Date: 2025-12-24 09:57:55
LastEditors: zyq
LastEditTime: 2025-12-24 15:02:05
'''

import asyncio
import json
import time
import traceback
from typing import Any, AsyncGenerator, Dict, List

from services.mcp.agents.base import BaseOrchestrator, OrchestratorFactory
from services.mcp.agents.stream_models import StreamEvent
from services.mcp.schemas import AgentMode
from services.mcp.tools.tool_executor import ToolExecutor
from pocketflow import AsyncFlow, AsyncNode


class _PlanNode(AsyncNode):
    """规划节点：生成子任务计划"""

    def __init__(self, orchestrator, event_queue, tool_map, per_llm_timeout, max_steps, start_ts):
        super().__init__()
        self.orchestrator = orchestrator
        self.event_queue = event_queue
        self.tool_map = tool_map
        self.per_llm_timeout = per_llm_timeout
        self.max_steps = max_steps
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
                    step=0
                )
            )
            shared["abort"] = True
        return None

    async def exec_async(self, _):
        if self.shared.get("abort"):
            return {"__abort__": True}
        plan = await self.orchestrator._retry_call(
            self.orchestrator._make_plan,
            timeout_ms=self.per_llm_timeout
        )
        return plan

    async def post_async(self, shared: Dict[str, Any], prep_res, plan_data):
        if shared.get("abort"):
            return "error"
        if not isinstance(plan_data, dict):
            await self.event_queue.put(
                StreamEvent(
                    type="error",
                    trace_id=self.orchestrator.trace_id,
                    agent_mode=self.orchestrator.agent_mode.value,
                    content="模型未生成有效计划",
                    step=0,
                    detail={"plan_raw": plan_data}
                )
            )
            shared["abort"] = True
            return "error"
        plan_items = plan_data.get("plan")
        if not plan_items or not isinstance(plan_items, list):
            await self.event_queue.put(
                StreamEvent(
                    type="error",
                    trace_id=self.orchestrator.trace_id,
                    agent_mode=self.orchestrator.agent_mode.value,
                    content="模型未生成有效计划",
                    step=0,
                    detail={"plan_raw": plan_data}
                )
            )
            shared["abort"] = True
            return "error"
        if len(plan_items) > self.max_steps:
            await self.event_queue.put(
                StreamEvent(
                    type="error",
                    trace_id=self.orchestrator.trace_id,
                    agent_mode=self.orchestrator.agent_mode.value,
                    content=f"计划步数超过限制({self.max_steps})",
                    step=0,
                    detail={"plan_raw": plan_items}
                )
            )
            shared["abort"] = True
            return "error"

        normalized = []
        for item in plan_items:
            tool_name = item.get("tool_name")
            args = item.get("args", {})
            goal = item.get("goal", "")
            if not tool_name or tool_name not in self.tool_map:
                await self.event_queue.put(
                    StreamEvent(
                        type="error",
                        trace_id=self.orchestrator.trace_id,
                        agent_mode=self.orchestrator.agent_mode.value,
                        content=f"计划包含未授权工具: {tool_name}",
                        step=0,
                        detail={"plan_item": item}
                    )
                )
                shared["abort"] = True
                return "error"
            normalized.append({
                "step": len(normalized) + 1,
                "goal": goal,
                "tool_name": tool_name,
                "args": args
            })
        shared["plan"] = normalized
        await self.event_queue.put(
            StreamEvent(
                type="plan",
                trace_id=self.orchestrator.trace_id,
                agent_mode=self.orchestrator.agent_mode.value,
                detail={"mode": "plan_react", "plan": normalized},
                step=0
            )
        )
        return "react"


class _ReactNode(AsyncNode):
    """按计划逐步调用工具"""

    def __init__(self, orchestrator, event_queue, tool_map, per_tool_timeout, start_ts):
        super().__init__()
        self.orchestrator = orchestrator
        self.event_queue = event_queue
        self.tool_map = tool_map
        self.per_tool_timeout = per_tool_timeout
        self.start_ts = start_ts

    async def prep_async(self, shared: Dict[str, Any]):
        self.shared = shared or {}
        return self.shared

    async def exec_async(self, shared: Dict[str, Any]):
        shared = shared or self.shared or {}
        plan = shared.get("plan") or []
        executed = shared.get("executed", [])
        if shared.get("abort") or not plan:
            return {"status": "error"}

        for item in plan:
            try:
                if self.orchestrator._time_exceeded(self.start_ts):
                    await self.event_queue.put(
                        StreamEvent(
                            type="error",
                            trace_id=self.orchestrator.trace_id,
                            agent_mode=self.orchestrator.agent_mode.value,
                            content="超出总执行时长限制",
                            step=len(executed) + 1,
                            detail={"plan_item": item}
                        )
                    )
                    shared["abort"] = True
                    break
                tool_name = item["tool_name"]
                args = item.get("args", {})
                step = len(executed) + 1
                await self.event_queue.put(
                    StreamEvent(
                        type="tool_start",
                        trace_id=self.orchestrator.trace_id,
                        agent_mode=self.orchestrator.agent_mode.value,
                        tool_name=tool_name,
                        step=step,
                        input=args,
                        detail={"goal": item.get("goal")}
                    )
                )
                executor = ToolExecutor(self.tool_map[tool_name], self.orchestrator.server_cfg)
                res = await self.orchestrator._retry_call(
                    executor.call,
                    args,
                    timeout_ms=self.per_tool_timeout
                )
                if not isinstance(res, dict):
                    raise ValueError("工具执行返回非字典结果")
                executed.append({
                    "tool_name": tool_name,
                    "args": args,
                    "result": res.get("result", {}),
                    "goal": item.get("goal")
                })
                await self.event_queue.put(
                    StreamEvent(
                        type="tool_end",
                        trace_id=self.orchestrator.trace_id,
                        agent_mode=self.orchestrator.agent_mode.value,
                        tool_name=tool_name,
                        step=step,
                        output=res.get("result", {}),
                        latency_ms=res.get("latency_ms"),
                        status="success",
                        detail={"goal": item.get("goal")}
                    )
                )
            except Exception as exc:
                executed.append({
                    "tool_name": item.get("tool_name") if isinstance(item, dict) else None,
                    "args": item.get("args") if isinstance(item, dict) else None,
                    "error": str(exc),
                    "goal": item.get("goal") if isinstance(item, dict) else None
                })
                await self.event_queue.put(
                    StreamEvent(
                        type="tool_end",
                        trace_id=self.orchestrator.trace_id,
                        agent_mode=self.orchestrator.agent_mode.value,
                        tool_name=item.get("tool_name") if isinstance(item, dict) else None,
                        step=step,
                        output=str(exc),
                        status="error",
                        detail={
                            "error": str(exc),
                            "traceback": traceback.format_exc(),
                            "goal": item.get("goal") if isinstance(item, dict) else None
                        }
                    )
                )
                shared["abort"] = True
                break
        shared["executed"] = executed
        return {"status": "error" if shared.get("abort") else "done"}

    async def post_async(self, shared: Dict[str, Any], exec_res, _):
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


class PlanReactPocketflowOrchestrator(BaseOrchestrator):
    """PocketFlow 版计划-执行编排器"""

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

    async def _make_plan(self, timeout_ms: int | None = None) -> Dict[str, Any]:
        tool_desc = "\n".join([
            f"- {item['tool_name']}: {item.get('description', '')} | 入参schema={json.dumps(item.get('input_schema', {}), ensure_ascii=False)}"
            for item in self.tool_bundle
        ])
        sys_prompt = (
            f"你是任务规划助手。请把用户问题拆解为最多{self.limits.get('max_steps', 10)}步的计划，每步给出目标、要调用的工具及其入参。\n"
            "输出JSON：{\"plan\": [{\"goal\": \"...\", \"tool_name\": \"...\", \"args\": {...}}]}"
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
            max_tokens=self.llm_params.get("max_tokens", 768),
            timeout_ms=timeout_ms
        )
        parsed = self._safe_json_loads(resp.answer)
        if not parsed or "plan" not in parsed:
            raise ValueError("计划生成解析失败")
        return parsed

    async def _summarize(self, executed: List[Dict[str, Any]], timeout_ms: int | None = None) -> str:
        sys_prompt = "你是结果汇总助手，请基于多步工具调用结果，输出简洁中文回答。"
        exec_text = json.dumps(executed, ensure_ascii=False)
        user_prompt = (
            f"业务提示词：{self.prompt}\n"
            f"用户问题：{self.query}\n"
            f"调用链路结果：{exec_text}\n"
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
        sys_prompt = "你是结果汇总助手，请基于多步工具调用结果，输出简洁中文回答。"
        exec_text = json.dumps(executed, ensure_ascii=False)
        user_prompt = (
            f"业务提示词：{self.prompt}\n"
            f"用户问题：{self.query}\n"
            f"调用链路结果：{exec_text}\n"
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
        max_steps = int(self.limits.get("max_steps", 10))

        plan = _PlanNode(self, event_queue, tool_map, per_llm_timeout, max_steps, start_ts)
        react = _ReactNode(self, event_queue, tool_map, per_tool_timeout, start_ts)
        summarize = _SummarizeNode(self, event_queue, per_llm_timeout)

        plan - "react" >> react
        plan - "error" >> summarize
        react - "summarize" >> summarize

        flow = AsyncFlow(start=plan)
        try:
            await flow.run_async(shared)
        except Exception as exc:
            await event_queue.put(
                StreamEvent(
                    type="error",
                    trace_id=self.trace_id,
                    agent_mode=self.agent_mode.value,
                    content="计划-执行编排流程内部异常",
                    step=len(shared.get("executed", [])) + 1,
                    detail={"error": str(exc), "traceback": traceback.format_exc()}
                )
            )

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
                content="计划-执行编排异常",
                step=len(shared["executed"]) + 1,
                detail={"error": str(exc), "traceback": traceback.format_exc()}
            )
        finally:
            if not flow_task.done():
                flow_task.cancel()
            try:
                await flow_task
            except Exception as exc:
                if not final_sent:
                    error_tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                    yield StreamEvent(
                        type="error",
                        trace_id=self.trace_id,
                        agent_mode=self.agent_mode.value,
                        content="计划-执行编排异常",
                        step=len(shared["executed"]) + 1,
                        detail={"error": str(exc), "traceback": error_tb}
                    )


OrchestratorFactory.register(AgentMode.PLAN_REACT, PlanReactPocketflowOrchestrator)
