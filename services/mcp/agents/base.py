'''
Description: MCP编排器基类与工厂
Author: zyq
Date: 2025-12-18 10:43:57
LastEditors: zyq
LastEditTime: 2025-12-19 09:02:24
'''

from abc import ABC, abstractmethod
import json
import asyncio
import time
from typing import AsyncGenerator, Dict, Any, List, Optional

from .stream_models import StreamEvent
from services.mcp.schemas import AgentMode


class BaseOrchestrator(ABC):
    """编排器基类"""

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
        self.agent_mode = agent_mode
        self.tool_bundle = tool_bundle
        self.limits = limits
        self.trace_id = trace_id
        self.llm_adapter = llm_adapter
        self.llm_params = llm_params
        self.server_cfg = server_cfg
        self.retry_cfg = retry_cfg
        self.query = query
        self.prompt = prompt
        self.stream_final = stream_final

    @abstractmethod
    async def run_stream(self) -> AsyncGenerator[StreamEvent, None]:
        """运行编排流程，产出流式事件"""
        pass

    def _tool_map(self) -> Dict[str, Dict[str, Any]]:
        return {item["tool_name"]: item for item in self.tool_bundle}

    def _digest(self, data: Any, limit: int = 500) -> str:
        text = json.dumps(data, ensure_ascii=False) if isinstance(data, (dict, list)) else str(data)
        return text if len(text) <= limit else text[:limit] + "..."

    def _safe_json_loads(self, text: str) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(text)
        except Exception:
            return None

    def _time_exceeded(self, start_ts: float) -> bool:
        """检查是否超过总时长限制"""
        max_total = self.limits.get("max_total_duration_ms")
        if not max_total:
            return False
        return (time.time() - start_ts) * 1000 > max_total

    async def _retry_call(self, coro_func, *args, **kwargs):
        """通用重试逻辑"""
        max_attempts = int(self.retry_cfg.get("max_attempts", 3))
        backoff_ms = int(self.retry_cfg.get("backoff_ms", 500))
        last_exc = None
        for attempt in range(1, max_attempts + 1):
            try:
                return await coro_func(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < max_attempts:
                    await asyncio.sleep(backoff_ms / 1000)
        raise last_exc


class OrchestratorFactory:
    """编排器工厂"""
    _registry = {}

    @classmethod
    def register(cls, mode: AgentMode, orchestrator_cls: type):
        cls._registry[mode.value] = orchestrator_cls

    @classmethod
    def create(
        cls,
        mode: AgentMode,
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
    ) -> BaseOrchestrator:
        if mode.value not in cls._registry:
            raise ValueError(f"不支持的编排模式: {mode}")
        orch_cls = cls._registry[mode.value]
        return orch_cls(
            mode,
            tool_bundle,
            limits,
            trace_id,
            llm_adapter,
            llm_params,
            server_cfg,
            retry_cfg,
            query,
            prompt,
            stream_final=stream_final
        )
