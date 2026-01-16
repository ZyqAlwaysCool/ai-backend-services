'''
Description: MCP流式事件模型
Author: zyq
Date: 2025-12-24 10:07:00
LastEditors: zyq
LastEditTime: 2025-12-24 10:07:00
'''
from dataclasses import dataclass
from typing import Optional, Dict, Any
import time


@dataclass
class StreamEvent:
    """统一的流式事件数据结构"""
    type: str
    trace_id: str
    agent_mode: str
    content: Optional[str] = None
    model: Optional[str] = None
    tool_name: Optional[str] = None
    step: Optional[int] = None
    input: Optional[Any] = None
    output: Optional[Any] = None
    latency_ms: Optional[int] = None
    status: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None
    ts: int = None

    def __post_init__(self):
        if self.ts is None:
            self.ts = int(time.time() * 1000)
