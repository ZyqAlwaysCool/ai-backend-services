'''
Description: MCP服务业务处理
Author: zyq
Date: 2025-12-24 10:22:00
LastEditors: zyq
LastEditTime: 2025-12-22 17:17:05
'''
import time
from typing import Dict, Any, List
from loguru import logger

from services.mcp.schemas import SyncMCPToolRequest, SyncToolMetaRequest, AskRequest, AgentMode
from services.mcp.storage.mcp_tool_store import MCPToolStore
from services.mcp.storage.mcp_run_store import MCPRunStore
from services.mcp.tools.tool_meta_provider import ToolMetaProvider
import services.mcp.agents  # noqa: F401  # 注册所有编排器
from services.mcp.agents.base import OrchestratorFactory
from services.mcp.agents.stream_models import StreamEvent
from services.mcp.llm_adapter import MCPOpenAIAdapter
from core.config import get_mcp_runtime_config
from core.exceptions import BaseBusinessException
from core.config.error_codes import COMMON_ERROR_REQUEST_PARSE_ERROR


class MCPHandlers:
    """MCP服务核心处理"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        runtime_cfg = get_mcp_runtime_config().mcp
        self.runtime_cfg = runtime_cfg
        db_name = config.get("mcp_db_name", "ai_backend_services_mcp")
        self.tool_store = MCPToolStore(db_name, config.get("tool_collection_name", "mcp_tools"))
        self.run_store = MCPRunStore(db_name, config.get("run_collection_name", "mcp_runs"), config.get("run_step_collection_name", "mcp_run_steps"))
        self.server_cfg = runtime_cfg.get("server", {})
        self.tool_meta_provider = ToolMetaProvider()
        self.allowed_modes = set(runtime_cfg.get("allowed_agent_modes", config.get("allowed_agent_modes", [])))
        self.default_mode = runtime_cfg.get("default_agent_mode", config.get("default_agent_mode", "single_tool"))
        # 合并运行限制，runtime优先
        merged_limits = {}
        merged_limits.update(config.get("limits", {}))
        merged_limits.update(runtime_cfg.get("limits", {}))
        self.max_tools_per_request = runtime_cfg.get("max_tools_per_request", config.get("max_tools_per_request", 5))
        merged_limits["max_tools_per_request"] = self.max_tools_per_request
        self.limits = merged_limits
        self.llm_cfg = runtime_cfg.get("llm", {})
        self.retry_cfg = runtime_cfg.get("retry", {"max_attempts": 3, "backoff_ms": 500})
        self.llm_adapter = MCPOpenAIAdapter(self.llm_cfg, timeout=self.llm_cfg.get("timeout", 30))

    async def initialize(self):
        """预留初始化逻辑"""
        return

    async def sync_mcp_tool(self, request: SyncMCPToolRequest, user_id: str, trace_id: str) -> Dict[str, Any]:
        """同步指定服务器的mcp工具信息"""
        self.tool_meta_provider.set_mcp_client(request.mcp_server_host, request.mcp_server_port, request.mcp_server_apikey)
        mcp_tools_info_list = await self.tool_meta_provider.fetch_meta_batch()
        meta = {
            "mcp_server_host": request.mcp_server_host,
            "mcp_server_port": request.mcp_server_port,
            "mcp_server_apikey": request.mcp_server_apikey,
        }
        self.tool_store.upsert_tools(user_id, mcp_tools_info_list, meta)
        return {"mcp_sync_tools": [t["tool_name"] for t in mcp_tools_info_list]}

    def list_tools(self, user_id: str, trace_id: str) -> List[Dict[str, Any]]:
        """查询工具"""
        return self.tool_store.list_tools(user_id)

    def get_run_trace(self, user_id: str, trace_id: str) -> Dict[str, Any]:
        """查询单次运行的审计记录"""
        data = self.run_store.get_run_with_steps(trace_id, user_id)
        if not data:
            raise BaseBusinessException(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                message="未找到对应的运行记录"
            )
        return data

    async def ask(self, request: AskRequest, user_id: str, trace_id: str, need_stream: bool):
        """提问入口，创建编排器并返回最终结果或最终结果流"""
        agent_mode = request.agent_mode.value
        if agent_mode not in self.allowed_modes:
            agent_mode = self.default_mode
        if len(request.tool_names) > self.max_tools_per_request:
            raise BaseBusinessException(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                message=f"单次请求最多允许 {self.max_tools_per_request} 个工具"
            )
        tools = self.tool_store.list_tools_by_names(user_id, request.tool_names)
        if not tools:
            raise BaseBusinessException(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                message="工具未注册或已禁用, 请检查tool_names或手动同步mcp可用工具集"
            )

        orchestrator = OrchestratorFactory.create(
            AgentMode(agent_mode),
            tool_bundle=tools,
            limits=self.limits,
            trace_id=trace_id,
            llm_adapter=self.llm_adapter,
            llm_params=self.llm_cfg,
            server_cfg=self.server_cfg,
            retry_cfg=self.retry_cfg,
            query=request.query,
            prompt=request.prompt,
            stream_final=need_stream
        )
        logger.info(f"use mcp orchestrator: {orchestrator}")
        # 保存运行记录
        self.run_store.save_run({
            "trace_id": trace_id,
            "user_id": user_id,
            "agent_mode": agent_mode,
            "query": request.query,
            "prompt": request.prompt,
            "tool_names": request.tool_names,
            "status": "running",
            "started_at": int(time.time() * 1000)
        })
        stream = orchestrator.run_stream()
        if not hasattr(stream, "__aiter__"):
            raise BaseBusinessException(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                message="编排器未返回流式结果，请检查agent_mode实现"
            )

        async def _consume_stream():
            step_idx = 0
            final_event = None
            try:
                async for event in stream:
                    # 消费StreamEvent事件, 保存审计日志
                    step_idx += 1
                    if event.type in {"plan", "tool_start", "tool_end"}:
                        if self.config.get("logging", {}).get("enable_step_log", True):
                            self.run_store.append_step({
                                "trace_id": trace_id,
                                "user_id": user_id,
                                "step": event.step or step_idx,
                                "step_type": event.type,
                                "tool_name": event.tool_name,
                                "input": event.input,
                                "output": event.output,
                                "latency_ms": event.latency_ms,
                                "status": event.status,
                                "detail": event.detail
                            })
                    if event.type in {"final", "error"}:
                        final_event = event
                        self.run_store.save_run({
                            "trace_id": trace_id,
                            "user_id": user_id,
                            "agent_mode": agent_mode,
                            "query": request.query,
                            "prompt": request.prompt,
                            "tool_names": request.tool_names,
                            "status": "finished" if event.type == "final" else "error",
                            "finish_reason": event.detail or {},
                            "ended_at": int(time.time() * 1000)
                        })
                if final_event:
                    return final_event
                error_event = StreamEvent(
                    type="error",
                    trace_id=trace_id,
                    agent_mode=agent_mode,
                    content="编排未产出最终结果",
                    step=step_idx,
                )
                self.run_store.save_run({
                    "trace_id": trace_id,
                    "user_id": user_id,
                    "agent_mode": agent_mode,
                    "query": request.query,
                    "prompt": request.prompt,
                    "tool_names": request.tool_names,
                    "status": "error",
                    "finish_reason": {"error": "编排未产出最终结果"},
                    "ended_at": int(time.time() * 1000)
                })
                return error_event
            except Exception as exc:
                logger.error(f"MCP编排流异常 trace_id={trace_id} mode={agent_mode} error={str(exc)}")
                error_event = StreamEvent(
                    type="error",
                    trace_id=trace_id,
                    agent_mode=agent_mode,
                    content="编排流处理失败",
                    step=step_idx,
                    detail={"error": str(exc)}
                )
                self.run_store.save_run({
                    "trace_id": trace_id,
                    "user_id": user_id,
                    "agent_mode": agent_mode,
                    "query": request.query,
                    "prompt": request.prompt,
                    "tool_names": request.tool_names,
                    "status": "error",
                    "finish_reason": error_event.detail,
                    "ended_at": int(time.time() * 1000)
                })
                return error_event
        async def _stream_and_forward():
            # 消费StreamEvent事件, 保存审计日志
            step_idx = 0
            final_event = None
            try:
                async for event in stream:
                    step_idx += 1
                    if event.type in {"plan", "tool_start", "tool_end"}:
                        if self.config.get("logging", {}).get("enable_step_log", True):
                            self.run_store.append_step({
                                "trace_id": trace_id,
                                "user_id": user_id,
                                "step": event.step or step_idx,
                                "step_type": event.type,
                                "tool_name": event.tool_name,
                                "input": event.input,
                                "output": event.output,
                                "latency_ms": event.latency_ms,
                                "status": event.status,
                                "detail": event.detail
                            })
                        continue
                    if event.type == "delta":
                        yield event
                        continue
                    if event.type in {"final", "error"}:
                        final_event = event
                        self.run_store.save_run({
                            "trace_id": trace_id,
                            "user_id": user_id,
                            "agent_mode": agent_mode,
                            "query": request.query,
                            "prompt": request.prompt,
                            "tool_names": request.tool_names,
                            "status": "finished" if event.type == "final" else "error",
                            "finish_reason": event.detail or {},
                            "ended_at": int(time.time() * 1000)
                        })
                        yield event
                if final_event:
                    return
                error_event = StreamEvent(
                    type="error",
                    trace_id=trace_id,
                    agent_mode=agent_mode,
                    content="编排未产出最终结果",
                    step=step_idx,
                )
                self.run_store.save_run({
                    "trace_id": trace_id,
                    "user_id": user_id,
                    "agent_mode": agent_mode,
                    "query": request.query,
                    "prompt": request.prompt,
                    "tool_names": request.tool_names,
                    "status": "error",
                    "finish_reason": {"error": "编排未产出最终结果"},
                    "ended_at": int(time.time() * 1000)
                })
                yield error_event
            except Exception as exc:
                logger.error(f"MCP编排流异常 trace_id={trace_id} mode={agent_mode} error={str(exc)}")
                error_event = StreamEvent(
                    type="error",
                    trace_id=trace_id,
                    agent_mode=agent_mode,
                    content="编排流处理失败",
                    step=step_idx,
                    detail={"error": str(exc)}
                )
                self.run_store.save_run({
                    "trace_id": trace_id,
                    "user_id": user_id,
                    "agent_mode": agent_mode,
                    "query": request.query,
                    "prompt": request.prompt,
                    "tool_names": request.tool_names,
                    "status": "error",
                    "finish_reason": error_event.detail,
                    "ended_at": int(time.time() * 1000)
                })
                yield error_event

        if need_stream:
            return _stream_and_forward()

        final_event = await _consume_stream()
        return final_event
