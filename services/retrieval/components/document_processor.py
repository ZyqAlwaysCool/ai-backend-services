'''
Description: 基于Haystack的文档处理组件
Author: zyq
Date: 2025-09-08 10:50:57
LastEditors: zyq
LastEditTime: 2025-09-08 10:54:08
'''

import os
import hashlib
from typing import List, Dict, Optional
from datetime import datetime

from haystack.components.converters.docx import DOCXToDocument
from loguru import logger

from core.storage.mongo_storage import MongoStorage


class DocumentProcessor:
    """基于Haystack的文档处理组件"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.mongo_storage = MongoStorage(
            db_name=config.get('retrieval_db_name', 'ai_backend_services_retrieval'),
            collection_name=config.get('retrieval_document_collection_name', 'retrieval_documents')
        )
        # 初始化Haystack DOCX转换器
        self.docx_converter = DOCXToDocument()
        
    def _calculate_file_hash(self, file_path: str) -> str:
        """计算文件hash值用于去重"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    def _check_file_exists(self, knowledge_base_name: str, file_hash: str) -> Optional[Dict]:
        """检查文件是否已存在(基于hash去重)"""
        existing_docs = self.mongo_storage.find_record({
            "knowledge_base_name": knowledge_base_name,
            "file_hash": file_hash
        })
        return existing_docs[0] if existing_docs else None
    
    def validate_docx_file(self, file_path: str) -> bool:
        """验证文件是否为有效的DOCX格式"""
        try:
            # 使用Haystack转换器验证文件
            result = self.docx_converter.run(sources=[file_path])
            return len(result.get('documents', [])) > 0
        except Exception as e:
            logger.error(f"DOCX validation failed for {file_path}: {str(e)}")
            return False
    
    def upload_document(self, 
                       file_path: str, 
                       original_filename: str,
                       knowledge_base_name: str,
                       overwrite_existing: bool = False) -> Dict:
        """
        上传单个文档到GridFS
        
        Args:
            file_path: 临时文件路径
            original_filename: 原始文件名
            knowledge_base_name: 知识库名称
            overwrite_existing: 是否覆盖已存在文件
            
        Returns:
            上传结果字典
        """
        try:
            # 1. 验证文件格式
            if not self.validate_docx_file(file_path):
                return {
                    "status": "failed",
                    "error_message": "文件格式验证失败，请确保是有效的DOCX文件"
                }
            
            # 2. 计算文件hash
            file_hash = self._calculate_file_hash(file_path)
            file_size = os.path.getsize(file_path)
            
            # 3. 检查重复文件
            existing_doc = self._check_file_exists(knowledge_base_name, file_hash)
            if existing_doc and not overwrite_existing:
                return {
                    "status": "failed", 
                    "error_message": f"文件已存在: {existing_doc['original_filename']}"
                }
            
            # 4. 上传到GridFS
            gridfs_filename = f"{knowledge_base_name}/{original_filename}"
            file_id = self.mongo_storage.upload_to_gridfs(
                file_path=file_path,
                filename=gridfs_filename
            )
            
            # 5. 保存文档元数据
            upload_time = datetime.now()
            doc_metadata = {
                "knowledge_base_name": knowledge_base_name,
                "original_filename": original_filename,
                "gridfs_file_id": file_id,
                "gridfs_filename": gridfs_filename,
                "file_size": file_size,
                "file_hash": file_hash,
                "upload_time": upload_time,
                "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            }
            
            # 如果是覆盖操作，先删除旧记录
            if existing_doc and overwrite_existing:
                self.mongo_storage.delete_record({
                    "knowledge_base_name": knowledge_base_name,
                    "file_hash": file_hash
                })
                # 删除旧的GridFS文件
                self.mongo_storage.delete_from_gridfs(existing_doc['gridfs_filename'])
            
            self.mongo_storage.create_record(doc_metadata)
            
            logger.info(f"Document uploaded successfully: {original_filename} -> {knowledge_base_name}")
            
            return {
                "status": "success",
                "filename": original_filename,
                "file_size": file_size,
                "upload_time": upload_time,
                "file_path": gridfs_filename
            }
            
        except Exception as e:
            logger.error(f"Failed to upload document {original_filename}: {str(e)}")
            return {
                "status": "failed",
                "error_message": f"上传失败: {str(e)}"
            }
    
    def batch_upload_documents(self, 
                              files: List[Dict], 
                              knowledge_base_name: str,
                              upload_options: Optional[Dict] = None) -> Dict:
        """
        批量上传文档
        
        Args:
            files: 文件列表，格式: [{"file_path": "", "filename": ""}, ...]
            knowledge_base_name: 知识库名称
            upload_options: 上传选项
            
        Returns:
            批量上传结果
        """
        upload_options = upload_options or {}
        overwrite_existing = upload_options.get("overwrite_existing", False)
        
        results = []
        success_count = 0
        failed_count = 0
        
        for file_info in files:
            file_path = file_info["file_path"]
            filename = file_info["filename"]
            
            result = self.upload_document(
                file_path=file_path,
                original_filename=filename,
                knowledge_base_name=knowledge_base_name,
                overwrite_existing=overwrite_existing
            )
            
            result["filename"] = filename
            results.append(result)
            
            if result["status"] == "success":
                success_count += 1
            else:
                failed_count += 1
        
        return {
            "total_files": len(files),
            "success_count": success_count,
            "failed_count": failed_count,
            "upload_results": results
        }