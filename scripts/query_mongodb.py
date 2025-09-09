#!/usr/bin/env python3
"""
MongoDB数据库内容统计脚本
显示各数据库和集合的文档数量
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient
from core.config.config_center import get_app_config

def query_mongodb_stats():
    """查询MongoDB统计信息"""
    try:
        app_config = get_app_config()
        
        # 构建MongoDB连接URL
        if hasattr(app_config, 'mongodb_url'):
            mongo_url = app_config.mongodb_url
        else:
            # 从配置中构建URL
            host = getattr(app_config, 'mongodb_host', 'localhost')
            port = getattr(app_config, 'mongodb_port', 27017)
            mongo_url = f"mongodb://{host}:{port}/"
        
        client = MongoClient(mongo_url)
        
        print("=== MongoDB数据库统计 ===")
        print(f"连接: {mongo_url}")
        print()
        
        # 获取所有数据库
        db_names = client.list_database_names()
        # 过滤掉系统数据库
        user_dbs = [name for name in db_names if name not in ['admin', 'local', 'config']]
        
        if not user_dbs:
            print("❌ 未找到用户数据库")
            return
        
        total_documents = 0
        
        for db_name in user_dbs:
            db = client[db_name]
            collections = db.list_collection_names()
            
            print(f"📁 数据库: {db_name}")
            print("-" * 40)
            
            db_total = 0
            for i, coll_name in enumerate(collections, 1):
                try:
                    collection = db[coll_name]
                    doc_count = collection.count_documents({})
                    db_total += doc_count
                    
                    print(f"  {i:2d}. {coll_name:<25} {doc_count:>8} 个文档")
                    
                except Exception as e:
                    print(f"  {i:2d}. {coll_name:<25} {'错误':>8}")
            
            print(f"  {'小计':<28} {db_total:>8} 个文档")
            print()
            total_documents += db_total
        
        print("=" * 40)
        print(f"{'总计':<30} {total_documents:>8} 个文档")
        
    except Exception as e:
        print(f"❌ 连接MongoDB失败: {str(e)}")

def query_specific_collection(db_name: str, collection_name: str, limit: int = 5):
    """查询指定集合的文档样本"""
    try:
        app_config = get_app_config()
        
        if hasattr(app_config, 'mongodb_url'):
            mongo_url = app_config.mongodb_url
        else:
            host = getattr(app_config, 'mongodb_host', 'localhost')
            port = getattr(app_config, 'mongodb_port', 27017)
            mongo_url = f"mongodb://{host}:{port}/"
        
        client = MongoClient(mongo_url)
        db = client[db_name]
        collection = db[collection_name]
        
        print(f"=== 集合 {db_name}.{collection_name} 内容样本 ===")
        
        # 总数量
        total_count = collection.count_documents({})
        print(f"总文档数: {total_count}")
        
        if total_count == 0:
            print("集合为空")
            return
        
        print(f"\n前 {min(limit, total_count)} 个文档:")
        print("-" * 50)
        
        # 获取样本文档
        docs = list(collection.find().limit(limit))
        
        for i, doc in enumerate(docs, 1):
            print(f"文档 {i}:")
            # 显示主要字段
            for key, value in doc.items():
                if isinstance(value, str) and len(value) > 100:
                    print(f"  {key}: {str(value)[:100]}...")
                else:
                    print(f"  {key}: {value}")
            print()
        
    except Exception as e:
        print(f"❌ 查询集合失败: {str(e)}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="MongoDB数据库查询工具")
    parser.add_argument("--db", help="指定数据库名")
    parser.add_argument("--collection", "-c", help="指定集合名")
    parser.add_argument("--limit", type=int, default=5, help="显示文档数量限制")
    
    args = parser.parse_args()
    
    if args.db and args.collection:
        query_specific_collection(args.db, args.collection, args.limit)
    else:
        query_mongodb_stats()