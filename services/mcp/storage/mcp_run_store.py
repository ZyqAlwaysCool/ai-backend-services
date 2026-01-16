'''
Description: MCP运行记录存储
Author: zyq
Date: 2025-12-24 10:17:00
LastEditors: zyq
LastEditTime: 2025-12-24 10:17:00
'''
from typing import Dict, Any
from loguru import logger
from core.storage.mongo_storage import MongoStorage
from pymongo import ASCENDING


class MCPRunStore:
    """运行与步骤审计存储"""

    def __init__(self, db_name: str, run_col: str, step_col: str):
        self.run_storage = MongoStorage(db_name=db_name, collection_name=run_col)
        self.step_storage = MongoStorage(db_name=db_name, collection_name=step_col)
        self.run_storage.col.create_index([("trace_id", ASCENDING), ("user_id", ASCENDING)], unique=True)
        self.step_storage.col.create_index([("trace_id", ASCENDING), ("user_id", ASCENDING), ("step", ASCENDING)], unique=False)

    def save_run(self, run_data: Dict[str, Any]):
        logger.info(f"保存运行记录 trace_id=({run_data.get('trace_id')})")
        self.run_storage.col.update_one(
            {"trace_id": run_data["trace_id"]},
            {"$set": run_data},
            upsert=True
        )

    def append_step(self, step_data: Dict[str, Any]):
        logger.info(f"追加步骤记录 trace_id=({step_data.get('trace_id')}) step=({step_data.get('step')})")
        self.step_storage.col.insert_one(step_data)

    def get_run_with_steps(self, trace_id: str, user_id: str) -> Dict[str, Any] | None:
        """按 trace_id+user_id 查询运行与步骤"""
        run = self.run_storage.col.find_one({"trace_id": trace_id, "user_id": user_id}, {"_id": 0})
        if not run:
            return None
        steps = list(self.step_storage.col.find({"trace_id": trace_id, "user_id": user_id}, {"_id": 0}).sort("step", ASCENDING))
        return {"run": run, "steps": steps}
