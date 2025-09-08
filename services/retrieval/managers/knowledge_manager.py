'''
Description: 知识库管理器
Author: zyq
Date: 2025-09-08 11:00:30
LastEditors: zyq
LastEditTime: 2025-09-08 11:02:31
'''

from typing import Dict, List, Optional
from datetime import datetime
from loguru import logger

from core.storage.mongo_storage import MongoStorage


class KnowledgeBaseManager:
    """知识库管理器"""
    
    def __init__(self, config: Dict):
        self.config = config
        # 使用单独的collection管理知识库元数据
        self.mongo_storage = MongoStorage(
            db_name=config.get('retrieval_db_name', 'ai_backend_services_retrieval'),
            collection_name=config.get('retrieval_kb_collection_name', 'retrieval_knowledge_bases')
        )
    
    def create_knowledge_base(self, knowledge_base_name: str) -> bool:
        """
        创建知识库
        
        Args:
            knowledge_base_name: 知识库名称
            
        Returns:
            创建成功返回True
        """
        try:
            # 检查知识库是否已存在
            existing_kb = self.get_knowledge_base(knowledge_base_name)
            if existing_kb:
                logger.warning(f"Knowledge base already exists: {knowledge_base_name}")
                return True  # 已存在，直接返回成功
            
            # 创建知识库元数据
            kb_metadata = {
                "knowledge_base_name": knowledge_base_name,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
                "document_count": 0,
                "total_size": 0,
                "version": "1.0.0"
            }
            
            self.mongo_storage.create_record(kb_metadata)
            logger.info(f"Knowledge base created: {knowledge_base_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create knowledge base {knowledge_base_name}: {str(e)}")
            return False
    
    def get_knowledge_base(self, knowledge_base_name: str) -> Optional[Dict]:
        """
        获取知识库信息
        
        Args:
            knowledge_base_name: 知识库名称
            
        Returns:
            知识库信息字典或None
        """
        try:
            kb_records = self.mongo_storage.find_record({
                "knowledge_base_name": knowledge_base_name
            })
            return kb_records[0] if kb_records else None
        except Exception as e:
            logger.error(f"Failed to get knowledge base {knowledge_base_name}: {str(e)}")
            return None
    
    def update_knowledge_base_stats(self, 
                                   knowledge_base_name: str, 
                                   document_count_delta: int = 0,
                                   size_delta: int = 0) -> bool:
        """
        更新知识库统计信息
        
        Args:
            knowledge_base_name: 知识库名称
            document_count_delta: 文档数量变化
            size_delta: 大小变化(字节)
            
        Returns:
            更新成功返回True
        """
        try:
            kb = self.get_knowledge_base(knowledge_base_name)
            if not kb:
                # 如果知识库不存在，先创建
                if not self.create_knowledge_base(knowledge_base_name):
                    return False
                kb = self.get_knowledge_base(knowledge_base_name)
            
            # 更新统计信息
            new_document_count = max(0, kb["document_count"] + document_count_delta)
            new_total_size = max(0, kb["total_size"] + size_delta)
            
            update_data = {
                "document_count": new_document_count,
                "total_size": new_total_size,
                "updated_at": datetime.now()
            }
            
            self.mongo_storage.update_record(
                {"knowledge_base_name": knowledge_base_name},
                update_data
            )
            
            logger.info(f"Knowledge base stats updated: {knowledge_base_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update knowledge base stats {knowledge_base_name}: {str(e)}")
            return False
    
    def list_knowledge_bases(self) -> List[Dict]:
        """
        列出所有知识库
        
        Returns:
            知识库列表
        """
        try:
            return self.mongo_storage.find_record({})
        except Exception as e:
            logger.error(f"Failed to list knowledge bases: {str(e)}")
            return []
    
    def delete_knowledge_base(self, knowledge_base_name: str) -> bool:
        """
        删除知识库(仅删除元数据，文档需要单独清理)
        
        Args:
            knowledge_base_name: 知识库名称
            
        Returns:
            删除成功返回True
        """
        try:
            self.mongo_storage.delete_record({
                "knowledge_base_name": knowledge_base_name
            })
            logger.info(f"Knowledge base deleted: {knowledge_base_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete knowledge base {knowledge_base_name}: {str(e)}")
            return False