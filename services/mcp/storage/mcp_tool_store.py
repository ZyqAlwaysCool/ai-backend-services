'''
Description: MCP工具存储
Author: zyq
Date: 2025-12-24 10:16:00
LastEditors: zyq
LastEditTime: 2025-12-23 09:12:43
'''
from typing import Dict, Any, List
from loguru import logger
from core.storage.mongo_storage import MongoStorage
from pymongo import ASCENDING


class MCPToolStore:
    """管理用户注册的MCP工具"""

    def __init__(self, db_name: str, collection_name: str):
        self.storage = MongoStorage(db_name=db_name, collection_name=collection_name)
        # 为 user_id + tool_name 建索引
        self.storage.col.create_index([("user_id", ASCENDING), ("tool_name", ASCENDING)], unique=True)
    
    def upsert_tools(self, user_id: str, tools: List[Dict[str, Any]], meta: Dict[str, Any]) -> None:
        """注册或更新mcp工具集"""
        for tool in tools:
            logger.info("注册/更新工具 user=({}) tool=({})".format(user_id, tool["tool_name"]))
            self.storage.col.update_one(
                {"user_id": user_id, "tool_name": tool["tool_name"]},
                {"$set": {
                    "description": tool["description"],
                    "input_schema": tool["input_schema"],
                    "meta": meta,
                }},
                upsert=True
            )
            

    def list_tools(self, user_id: str) -> List[Dict[str, Any]]:
        """列出用户可用工具"""
        return list(self.storage.col.find({"user_id": user_id}, {"_id": 0}))

    def get_tool(self, user_id: str, tool_name: str) -> Dict[str, Any] | None:
        """获取单个工具"""
        return self.storage.col.find_one({"user_id": user_id, "tool_name": tool_name}, {"_id": 0})

    def list_tools_by_names(self, user_id: str, names: List[str]) -> List[Dict[str, Any]]:
        """按名称列表过滤"""
        return list(self.storage.col.find({"user_id": user_id, "tool_name": {"$in": names}}, {"_id": 0}))
