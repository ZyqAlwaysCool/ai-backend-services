'''
Description: 检索服务版本管理器
Author: zyq
Date: 2025-09-15 15:26:17
LastEditors: zyq
LastEditTime: 2025-09-15 17:29:50
'''

import re
from typing import Dict, List, Optional
from datetime import datetime
from loguru import logger

from core.storage.mongo_storage import MongoStorage
from ..schemas import DocumentCleanSettings


class RetrievalVersionManager:
    """检索服务版本管理器"""
    
    def __init__(self, config: Dict):
        """
        初始化版本管理器
        
        Args:
            config: 服务配置
        """
        self.config = config
        
        # 使用独立的集合管理知识库版本
        self.mongo_storage = MongoStorage(
            db_name=config.get('retrieval_db_name', 'ai_backend_services_retrieval'),
            collection_name=config.get('kb_versions_collection_name', 'knowledge_base_versions')
        )
        
        logger.info("RetrievalVersionManager初始化完成")
    
    def generate_kb_version(self, knowledge_base_name: str, clean_settings: DocumentCleanSettings) -> str:
        """
        生成知识库版本号：YYYYMMDD-{配置简码}-{序号}
        
        Args:
            knowledge_base_name: 知识库名称
            clean_settings: 清洗配置
            
        Returns:
            生成的版本号
        """
        today = datetime.now().strftime("%Y%m%d")
        
        # 生成配置简码
        config_code = self._generate_config_code(clean_settings)
        
        # 查找今天相同配置的版本数量
        version_pattern = f"{today}-{config_code}-"
        existing_versions = self.mongo_storage.find_record({
            "knowledge_base_name": knowledge_base_name,
            "version": {"$regex": f"^{re.escape(version_pattern)}"}
        })
        
        # 生成序号（从1开始）
        next_seq = len(existing_versions) + 1
        version = f"{today}-{config_code}-{next_seq}"
        
        logger.info(f"生成知识库版本号 - KB: {knowledge_base_name}, Version: {version}")
        return version
    
    def create_kb_version(self, knowledge_base_name: str, version: str = None,
                         clean_settings: DocumentCleanSettings = None,
                         settings_hash: str = None) -> str:
        """
        创建知识库版本记录
        
        Args:
            knowledge_base_name: 知识库名称
            version: 指定版本号，为空则自动生成
            clean_settings: 清洗配置
            settings_hash: 设置哈希值（技术兼容字段）
            
        Returns:
            创建的版本号
        """
        if not version and clean_settings:
            version = self.generate_kb_version(knowledge_base_name, clean_settings)
        
        try:
            # 标记该知识库的所有版本为非最新
            self.mongo_storage.update_many(
                {"knowledge_base_name": knowledge_base_name, "is_latest": True},
                {"is_latest": False}
            )
            
            # 创建新版本记录
            version_record = {
                "knowledge_base_name": knowledge_base_name,
                "version": version,
                "settings_hash": settings_hash,
                "is_latest": True,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
                "document_count": 0,  # 初始值，构建完成后更新
                "chunk_count": 0     # 初始值，构建完成后更新
            }
            
            # 添加清洗配置信息
            if clean_settings:
                version_record.update({
                    "chunk_method": clean_settings.split_method.value,
                    "chunk_settings": clean_settings.dict(),
                    "config_params": {
                        "split_method": clean_settings.split_method.value,
                        "split_length": clean_settings.split_length,
                        "split_overlap": clean_settings.split_overlap
                    }
                })
            
            self.mongo_storage.create_record(version_record)
            logger.info(f"知识库版本创建成功 - KB: {knowledge_base_name}, Version: {version}")
            
            return version
            
        except Exception as e:
            logger.error(f"知识库版本创建失败 - KB: {knowledge_base_name}: {str(e)}")
            raise
    
    def get_kb_versions(self, knowledge_base_name: str, limit: int = None) -> List[Dict]:
        """
        获取知识库的版本列表
        
        Args:
            knowledge_base_name: 知识库名称
            limit: 限制返回数量
            
        Returns:
            版本列表，按版本号倒序排列
        """
        try:
            query = {"knowledge_base_name": knowledge_base_name}
            # 按版本号倒序排列（最新在前）
            sort = [("version", -1)]
            
            if limit:
                result = self.mongo_storage.find_record(query, sort=sort, limit=limit)
            else:
                result = self.mongo_storage.find_record(query, sort=sort)
                
            logger.debug(f"查询知识库版本列表 - KB: {knowledge_base_name}, Count: {len(result)}")
            return result
            
        except Exception as e:
            logger.error(f"查询知识库版本列表失败 - KB: {knowledge_base_name}: {str(e)}")
            return []
    
    def get_latest_kb_version(self, knowledge_base_name: str) -> Optional[Dict]:
        """
        获取知识库最新版本
        
        Args:
            knowledge_base_name: 知识库名称
            
        Returns:
            最新版本记录，不存在则返回None
        """
        try:
            result = self.mongo_storage.find_record(
                {"knowledge_base_name": knowledge_base_name, "is_latest": True}
            )
            
            latest = result[0] if result else None
            if latest:
                logger.debug(f"查询知识库最新版本 - KB: {knowledge_base_name}, Version: {latest['version']}")
            else:
                logger.debug(f"未找到知识库最新版本 - KB: {knowledge_base_name}")
                
            return latest
            
        except Exception as e:
            logger.error(f"查询知识库最新版本失败 - KB: {knowledge_base_name}: {str(e)}")
            return None
    
    def update_kb_version_stats(self, knowledge_base_name: str, version: str,
                               document_count: int = None, chunk_count: int = None) -> bool:
        """
        更新知识库版本统计信息
        
        Args:
            knowledge_base_name: 知识库名称
            version: 版本号
            document_count: 文档数量
            chunk_count: 文档块数量
            
        Returns:
            更新成功返回True
        """
        try:
            update_data = {"updated_at": datetime.now()}
            
            if document_count is not None:
                update_data["document_count"] = document_count
            if chunk_count is not None:
                update_data["chunk_count"] = chunk_count
            
            result = self.mongo_storage.update_record(
                {"knowledge_base_name": knowledge_base_name, "version": version},
                update_data
            )
            
            if result:
                logger.info(f"知识库版本统计更新成功 - KB: {knowledge_base_name}, Version: {version}")
            else:
                logger.warning(f"知识库版本不存在或更新失败 - KB: {knowledge_base_name}, Version: {version}")
                
            return bool(result)
            
        except Exception as e:
            logger.error(f"知识库版本统计更新失败 - KB: {knowledge_base_name}, Version: {version}: {str(e)}")
            return False
    
    def parse_version_info(self, version: str) -> Dict:
        """
        解析版本号信息
        
        Args:
            version: 版本号
            
        Returns:
            解析后的版本信息
        """
        try:
            # 匹配格式：YYYYMMDD-{配置简码}-{序号}
            match = re.match(r'^(\d{8})-([^-]+)-(\d+)$', version)
            if not match:
                return {"valid": False}
            
            date_part, config_part, seq_part = match.groups()
            
            # 解析日期
            year = int(date_part[:4])
            month = int(date_part[4:6])
            day = int(date_part[6:8])
            
            return {
                "valid": True,
                "date": date_part,
                "config_code": config_part,
                "sequence": int(seq_part),
                "year": year,
                "month": month,
                "day": day,
                "readable_date": f"{year}-{month:02d}-{day:02d}",
                "config_readable": self._decode_config_code(config_part)
            }
            
        except Exception as e:
            logger.warning(f"版本号解析失败 - Version: {version}: {str(e)}")
            return {"valid": False}
    
    def _generate_config_code(self, clean_settings: DocumentCleanSettings) -> str:
        """
        生成知识库配置简码
        
        配置简码格式：{方法}{长度}[o{重叠}]
        示例：sent200, word150o10, pass500o50
        """
        try:
            # 方法映射
            method_map = {
                "sentence": "sent",
                "word": "word",
                "passage": "pass",
                "custom": "cust"
            }
            
            method_code = method_map.get(clean_settings.split_method.value, "unkn")
            
            # 基础格式：方法+长度
            config_code = f"{method_code}{clean_settings.split_length}"
            
            # 如果overlap不是默认值20，则添加
            if clean_settings.split_overlap != 20:
                config_code += f"o{clean_settings.split_overlap}"
            
            return config_code
            
        except Exception as e:
            logger.error(f"配置简码生成失败: {str(e)}")
            return "error"
    
    def _decode_config_code(self, config_code: str) -> str:
        """
        解码配置简码为可读描述
        
        Args:
            config_code: 配置简码 (如 sent200, word150o10)
            
        Returns:
            可读描述 (如 "句子切分,长度200", "词切分,长度150,重叠10")
        """
        try:
            # 方法反向映射
            method_reverse_map = {
                "sent": "句子切分",
                "word": "词切分", 
                "pass": "段落切分",
                "cust": "自定义切分",
                "unkn": "未知切分"
            }
            
            # 匹配模式：方法名+数字[o数字]
            match = re.match(r'^([a-z]+)(\d+)(?:o(\d+))?$', config_code)
            if not match:
                return config_code
            
            method_code, length, overlap = match.groups()
            method_desc = method_reverse_map.get(method_code, method_code)
            
            desc = f"{method_desc},长度{length}"
            if overlap:
                desc += f",重叠{overlap}"
            else:
                desc += ",重叠20"  # 默认重叠值
                
            return desc
            
        except Exception as e:
            logger.warning(f"配置简码解码失败 - Code: {config_code}: {str(e)}")
            return config_code