'''
Description: 文档清洗组件 - 支持同步/异步清洗策略和超时控制
Author: zyq
Date: 2025-09-08 16:53:50
LastEditors: zyq
LastEditTime: 2025-09-08 17:07:59
'''

import asyncio
import hashlib
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from haystack import Document
from haystack.components.preprocessors import DocumentSplitter
from haystack_integrations.components.preprocessors.hanlp import ChineseDocumentSplitter
from loguru import logger

from ..schemas import DocumentLanguage, SplitMethod, ChineseGranularity, DocumentCleanSettings
from core.config import get_services_config


class DocumentCleanTimeout(Exception):
    """文档清洗超时异常"""
    pass


class DocumentCleaner:
    """文档清洗组件 - 支持中英文文档分割和性能优化"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化文档清洗器"""
        self.config = config
        
        # 从配置中心获取清洗性能配置
        services_config = get_services_config()
        retrieval_config = services_config.retrieval
        
        if retrieval_config and retrieval_config.clean_performance:
            self.perf_config = retrieval_config.clean_performance.model_dump()
        else:
            # 默认配置
            self.perf_config = {
                "sync_threshold": 20,
                "chunk_batch_size": 10,
                "single_doc_timeout_seconds": 30
            }
            
        logger.info(f"DocumentCleaner initialized with performance config: {self.perf_config}")
    
    def determine_processing_mode(self, pending_count: int) -> str:
        """
        确定处理模式
        
        Args:
            pending_count: 待处理文档数量
            
        Returns:
            处理模式：'sync', 'async'
        """
        if pending_count <= self.perf_config['sync_threshold']:
            return 'sync'
        else:
            # 超过同步阈值的都用异步处理，不拒绝用户请求
            return 'async'
    
    def generate_settings_hash(self, settings: DocumentCleanSettings) -> str:
        """生成清洗设置的哈希值，用于判断是否需要重新清洗"""
        settings_str = f"{settings.language}_{settings.split_method}_{settings.split_length}_{settings.split_overlap}"
        if settings.chinese_granularity:
            settings_str += f"_{settings.chinese_granularity}"
        if settings.custom_separator:
            settings_str += f"_{settings.custom_separator}"
        
        return hashlib.md5(settings_str.encode('utf-8')).hexdigest()
    
    def _create_splitter(self, settings: DocumentCleanSettings):
        """根据设置创建合适的分割器"""
        if settings.language == DocumentLanguage.CHINESE:
            return self._create_chinese_splitter(settings)
        else:
            return self._create_english_splitter(settings)
    
    def _create_chinese_splitter(self, settings: DocumentCleanSettings) -> ChineseDocumentSplitter:
        """创建中文分割器"""
        # 处理自定义分隔符
        if settings.split_method == SplitMethod.CUSTOM:
            if not settings.custom_separator:
                raise ValueError("使用自定义分割方式时必须提供custom_separator")
            
            return ChineseDocumentSplitter(
                split_by="function",
                split_length=settings.split_length,
                split_overlap=settings.split_overlap,
                splitting_function=lambda text: text.split(settings.custom_separator),
                granularity=settings.chinese_granularity.value if settings.chinese_granularity else "coarse"
            )
        
        # 标准分割方式
        return ChineseDocumentSplitter(
            split_by=settings.split_method.value,
            split_length=settings.split_length, 
            split_overlap=settings.split_overlap,
            granularity=settings.chinese_granularity.value if settings.chinese_granularity else "coarse"
        )
    
    def _create_english_splitter(self, settings: DocumentCleanSettings) -> DocumentSplitter:
        """创建英文分割器"""
        # 处理自定义分隔符
        if settings.split_method == SplitMethod.CUSTOM:
            if not settings.custom_separator:
                raise ValueError("使用自定义分割方式时必须提供custom_separator")
                
            return DocumentSplitter(
                split_by="function",
                split_length=settings.split_length,
                split_overlap=settings.split_overlap,
                splitting_function=lambda text: text.split(settings.custom_separator)
            )
        
        # 标准分割方式
        return DocumentSplitter(
            split_by=settings.split_method.value,
            split_length=settings.split_length,
            split_overlap=settings.split_overlap,
            language="en"
        )
    
    async def clean_single_document_with_timeout(self,
                                                document: Document,
                                                splitter,
                                                trace_id: str = None) -> Tuple[List[Document], Optional[str]]:
        """
        清洗单个文档，带超时控制
        
        Args:
            document: 待清洗的文档
            splitter: 分割器
            trace_id: 请求追踪ID
            
        Returns:
            Tuple[清洗后的文档块列表, 错误信息(如果有)]
        """
        timeout_seconds = self.perf_config['single_doc_timeout_seconds']
        
        try:
            # 使用asyncio.wait_for实现超时控制
            result = await asyncio.wait_for(
                self._run_splitter_async(splitter, [document]),
                timeout=timeout_seconds
            )
            
            split_documents = result.get("documents", [])
            return split_documents, None
            
        except asyncio.TimeoutError:
            error_msg = f"文档清洗超时(>{timeout_seconds}秒)"
            logger.warning(f"Document cleaning timeout - TraceID: {trace_id}, File: {document.meta.get('filename', 'unknown')}")
            return [], error_msg
            
        except Exception as e:
            error_msg = f"文档清洗失败: {str(e)}"
            logger.error(f"Document cleaning failed - TraceID: {trace_id}, File: {document.meta.get('filename', 'unknown')}: {str(e)}")
            return [], error_msg
    
    async def _run_splitter_async(self, splitter, documents: List[Document]) -> Dict:
        """异步运行分割器（将同步操作包装为异步）"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, splitter.run, documents)
    
    async def clean_documents_batch_with_timeout(self, 
                                               documents: List[Document], 
                                               settings: DocumentCleanSettings,
                                               trace_id: str = None) -> Tuple[List[Document], Dict[str, Any], List[Dict]]:
        """
        批量清洗文档，带超时控制
        
        Args:
            documents: 待清洗的文档列表
            settings: 清洗设置
            trace_id: 请求追踪ID
            
        Returns:
            Tuple[清洗后的文档块列表, 处理统计信息, 失败文档列表]
        """
        logger.info(f"Start cleaning document batch with timeout - TraceID: {trace_id}, Count: {len(documents)}")
        
        try:
            # 创建分割器
            splitter = self._create_splitter(settings)
            logger.info(f"Created splitter - Language: {settings.language}, Method: {settings.split_method}")
            
            all_chunks = []
            failed_docs = []
            success_count = 0
            
            # 逐个处理文档，每个都有独立的超时控制
            for doc in documents:
                filename = doc.meta.get('filename', 'unknown')
                
                chunks, error_msg = await self.clean_single_document_with_timeout(
                    doc, splitter, trace_id
                )
                
                if error_msg:
                    # 记录失败文档
                    failed_docs.append({
                        "filename": filename,
                        "error_message": error_msg,
                        "error_code": "TIMEOUT" if "超时" in error_msg else "PROCESSING_ERROR"
                    })
                else:
                    # 成功处理
                    all_chunks.extend(chunks)
                    success_count += 1
            
            # 统计信息
            stats = {
                "input_documents": len(documents),
                "success_documents": success_count,
                "failed_documents": len(failed_docs),
                "output_chunks": len(all_chunks),
                "avg_chunk_size": self._calculate_avg_chunk_size(all_chunks),
                "language_used": settings.language.value,
                "split_method_used": settings.split_method.value,
                "splitter_type": "chinese" if settings.language == DocumentLanguage.CHINESE else "english"
            }
            
            logger.info(f"Document cleaning batch completed - TraceID: {trace_id}, Success: {success_count}, Failed: {len(failed_docs)}, Chunks: {len(all_chunks)}")
            
            return all_chunks, stats, failed_docs
            
        except Exception as e:
            logger.error(f"Document cleaning batch failed - TraceID: {trace_id}: {str(e)}")
            raise
    
    async def clean_documents_in_chunks_with_timeout(self,
                                                   documents: List[Document],
                                                   settings: DocumentCleanSettings,
                                                   trace_id: str = None) -> Tuple[List[Document], Dict[str, Any], List[Dict]]:
        """
        分块清洗大量文档（用于异步处理），带超时控制
        
        Args:
            documents: 待清洗的文档列表
            settings: 清洗设置
            trace_id: 请求追踪ID
            
        Returns:
            Tuple[清洗后的文档块列表, 处理统计信息, 失败文档列表]
        """
        logger.info(f"Start chunked cleaning with timeout - TraceID: {trace_id}, Total: {len(documents)}")
        
        all_chunks = []
        all_failed_docs = []
        total_success = 0
        chunk_size = self.perf_config['chunk_batch_size']
        
        # 分批处理
        for i in range(0, len(documents), chunk_size):
            batch_docs = documents[i:i + chunk_size]
            batch_num = i // chunk_size + 1
            total_batches = (len(documents) + chunk_size - 1) // chunk_size
            
            logger.info(f"Processing batch {batch_num}/{total_batches} - TraceID: {trace_id}")
            
            try:
                batch_chunks, batch_stats, batch_failed = await self.clean_documents_batch_with_timeout(
                    batch_docs, settings, trace_id
                )
                
                all_chunks.extend(batch_chunks)
                all_failed_docs.extend(batch_failed)
                total_success += batch_stats['success_documents']
                
            except Exception as e:
                logger.error(f"Batch {batch_num} failed - TraceID: {trace_id}: {str(e)}")
                # 将整个批次标记为失败
                for doc in batch_docs:
                    all_failed_docs.append({
                        "filename": doc.meta.get('filename', 'unknown'),
                        "error_message": f"批次处理失败: {str(e)}",
                        "error_code": "BATCH_ERROR"
                    })
        
        # 总体统计信息
        stats = {
            "input_documents": len(documents),
            "success_documents": total_success,
            "failed_documents": len(all_failed_docs),
            "output_chunks": len(all_chunks),
            "avg_chunk_size": self._calculate_avg_chunk_size(all_chunks),
            "language_used": settings.language.value,
            "split_method_used": settings.split_method.value,
            "splitter_type": "chinese" if settings.language == DocumentLanguage.CHINESE else "english",
            "batches_processed": (len(documents) + chunk_size - 1) // chunk_size
        }
        
        logger.info(f"Chunked cleaning completed - TraceID: {trace_id}, Success: {total_success}, Failed: {len(all_failed_docs)}, Total chunks: {len(all_chunks)}")
        return all_chunks, stats, all_failed_docs
    
    def _calculate_avg_chunk_size(self, documents: List[Document]) -> float:
        """计算平均块大小"""
        if not documents:
            return 0.0
        
        total_size = sum(len(doc.content or "") for doc in documents)
        return total_size / len(documents)
    
    def validate_settings(self, settings: DocumentCleanSettings) -> None:
        """验证清洗设置"""
        # 验证自定义分隔符
        if settings.split_method == SplitMethod.CUSTOM and not settings.custom_separator:
            raise ValueError("使用自定义分割方式时必须提供custom_separator")
        
        # 验证中文粒度设置（只在中文模式下需要）
        if settings.language == DocumentLanguage.CHINESE and not settings.chinese_granularity:
            raise ValueError("中文模式下必须设置chinese_granularity")
        
        # 验证参数范围
        if settings.split_overlap >= settings.split_length:
            raise ValueError("split_overlap必须小于split_length")
        
        logger.info("Settings validation passed")