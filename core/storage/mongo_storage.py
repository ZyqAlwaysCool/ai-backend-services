'''
Description: mongo存储
Author: zyq
Date: 2025-08-04 16:34:04
LastEditors: zyq
LastEditTime: 2025-08-08 11:17:32
'''

import os
from typing import List
from pathlib import Path
import gridfs
import yaml
from pymongo import MongoClient
from gridfs.errors import NoFile
from loguru import logger

class MongoStorage:
    def __init__(self, db_name: str = "mongo_storage_default_database", collection_name: str = "mongo_storage_default_collection"):
        # 根据环境变量选择配置文件，默认为开发环境
        env = os.getenv('ENV', 'dev')
        config_filename = f"app.{env}.yml"
        cfg_path = Path(__file__).resolve().parent.parent.parent / "configs" / "app" / config_filename
        mongo_cfg  = yaml.safe_load(open(cfg_path, encoding="utf-8")).get("mongo", {})
        mg_host = os.getenv("MONGO_HOST") or mongo_cfg.get("host", "localhost")
        mg_port = os.getenv("MONGO_PORT") or mongo_cfg.get("port", 27017)
        
        self.client = MongoClient(host=mg_host, port=int(mg_port))
        self.db = self.client[db_name]
        self.col = self.db[collection_name]
        self.fs = gridfs.GridFS(self.db)
        
        logger.info(f"MongoStorage init done. db=({self.db}) collection=({self.col})")
        
    def upload_to_gridfs(self, file_path: str | Path, filename: str | None = None) -> str:
        """上传文件至GridFS"""
        file_path = Path(file_path)
        filename = filename or file_path.name
        with file_path.open("rb") as f:
            file_id = self.fs.put(f, filename=filename)
        return str(file_id)
    
    def download_from_gridfs(self, filename: str, save_path: str | Path) -> bool:
        """按照文件名下载文件"""
        save_path = Path(save_path)
        grid_out = self.fs.find_one({"filename": filename})
        if not grid_out:
            logger.error(f"'{filename}' not found in GridFS")
            #raise FileNotFoundError(f"'{filename}' not found in GridFS")
            return False
        with save_path.open("wb") as f:
            f.write(grid_out.read())
        return True
    
    def download_from_gridfs_by_fid(self, file_id: str, save_path: str | Path) -> None:
        out = self.fs.get(file_id)   
        with open(save_path, 'wb') as f:
            f.write(out.read())
    
    def delete_from_gridfs(self, filename: str) -> bool:
        """按文件名删除文件(同名只删第一条)"""
        file_doc = self.fs.find_one({"filename": filename})
        if not file_doc:
            return False
        self.fs.delete(file_doc._id)
        return True

    def list_files_from_gridfs(self) -> List[str]:
        """列出 GridFS 中所有文件名(去重)"""
        return list({doc.filename for doc in self.fs.find()})
    
    def create_record(self, data: dict) -> None:
        logger.info(f"create record. data=({data})")
        self.col.insert_one(data)
        logger.info(f"create record success.")
    
    def delete_record(self, data: dict) -> None:
        logger.info(f"delete record. data=({data})")
        self.col.delete_one(data)
        logger.info(f"delete record success.")
    
    def find_record(self, filter: dict) -> List[dict]:
        logger.info(f"find record. filter=({filter})")
        record_list = []
        for doc in self.col.find(filter):
            record_list.append(doc)
        logger.info(f"find record success.")
        return record_list
    
    def update_record(self, filter: dict, data: dict) -> None:
        logger.info(f"update record. filter=({filter}) data=({data})")
        self.col.update_one(filter, {"$set": data})
        logger.info(f"update record success.")
            
    def close_client(self) -> None:
        logger.info(f"close mongo client.")
        self.client.close()