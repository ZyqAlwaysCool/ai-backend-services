#!/usr/bin/env python3
"""
Qdrant向量数据库内容统计脚本
显示所有索引和文档分块数量
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qdrant_client import QdrantClient
from core.config.config_center import get_app_config

def query_qdrant_stats():
    """查询Qdrant统计信息"""
    try:
        app_config = get_app_config()
        client = QdrantClient(host=app_config.qdrant_host, port=app_config.qdrant_port)
        
        print("=== Qdrant向量数据库统计 ===")
        print(f"服务器: {app_config.qdrant_host}:{app_config.qdrant_port}")
        print()
        
        # 获取所有集合
        collections = client.get_collections()
        collection_names = [col.name for col in collections.collections]
        
        if not collection_names:
            print("❌ 未找到任何索引/集合")
            return
        
        print(f"总索引数: {len(collection_names)}")
        print("-" * 50)
        
        total_documents = 0
        for i, name in enumerate(collection_names, 1):
            try:
                count_result = client.count(collection_name=name)
                doc_count = count_result.count
                total_documents += doc_count
                
                print(f"{i:2d}. {name:<30} {doc_count:>8} 个文档")
                
            except Exception as e:
                print(f"{i:2d}. {name:<30} {'错误':>8} ({str(e)[:20]}...)")
        
        print("-" * 50)
        print(f"{'总计':<33} {total_documents:>8} 个文档")
        
    except Exception as e:
        print(f"❌ 连接Qdrant失败: {str(e)}")

if __name__ == "__main__":
    query_qdrant_stats()