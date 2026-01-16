"""
Description: MCP编排器注册入口
Author: zyq
Date: 2025-12-24 10:09:00
LastEditors: zyq
LastEditTime: 2025-12-24 10:09:00
"""
# 导入编排器以完成工厂注册
from services.mcp.agents.supervisor_pocketflow import SupervisorPocketflowOrchestrator  # noqa: F401
from services.mcp.agents.single_tool_pocketflow import SingleToolPocketflowOrchestrator  # noqa: F401
from services.mcp.agents.plan_react_pocketflow import PlanReactPocketflowOrchestrator  # noqa: F401
