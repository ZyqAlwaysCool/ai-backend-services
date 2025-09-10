#!/usr/bin/env python3
"""
清理ARQ重试任务的脚本
用于解决重试队列中堆积的任务
"""

import asyncio
import redis.asyncio as redis
from datetime import datetime
from core.config.config_center import get_app_config

async def clean_retry_tasks():
    """清理ARQ重试任务"""
    
    # 获取Redis配置
    app_config = get_app_config()
    
    # 连接Redis
    redis_client = redis.Redis(
        host=app_config.redis_host,
        port=app_config.redis_port,
        db=app_config.redis_db,
        password=app_config.redis_password,
        decode_responses=True
    )
    
    try:
        print("=" * 60)
        print("清理ARQ重试任务")
        print("=" * 60)
        print(f"Redis: {app_config.redis_host}:{app_config.redis_port}/{app_config.redis_db}")
        print(f"清理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # 1. 检查重试任务
        retry_keys = await redis_client.keys("arq:retry:*")
        print(f"发现 {len(retry_keys)} 个重试任务")
        
        if not retry_keys:
            print("没有需要清理的重试任务")
            return
        
        # 2. 显示任务详情并确认清理
        print("\n重试任务列表:")
        for i, retry_key in enumerate(retry_keys[:10]):  # 只显示前10个
            try:
                ttl = await redis_client.ttl(retry_key)
                job_id = retry_key.replace('arq:retry:', '')
                print(f"  {i+1}. 任务ID: {job_id} (TTL: {ttl}s)")
            except Exception as e:
                print(f"  {i+1}. {retry_key} (读取失败: {e})")
        
        if len(retry_keys) > 10:
            print(f"  ... 还有 {len(retry_keys) - 10} 个任务")
        
        # 3. 用户确认
        print(f"\n是否要清理这 {len(retry_keys)} 个重试任务？")
        print("注意：这将永久删除这些任务，无法恢复！")
        confirm = input("输入 'yes' 确认清理，其他任何输入取消: ")
        
        if confirm.lower() != 'yes':
            print("清理操作已取消")
            return
        
        # 4. 执行清理
        print("\n开始清理...")
        cleaned_count = 0
        failed_count = 0
        
        for retry_key in retry_keys:
            try:
                result = await redis_client.delete(retry_key)
                if result:
                    cleaned_count += 1
                    print(f"✓ 已删除: {retry_key}")
                else:
                    failed_count += 1
                    print(f"✗ 删除失败: {retry_key}")
            except Exception as e:
                failed_count += 1
                print(f"✗ 删除失败: {retry_key} - {e}")
        
        print(f"\n清理完成!")
        print(f"成功清理: {cleaned_count} 个任务")
        print(f"清理失败: {failed_count} 个任务")
        
        # 5. 检查是否还有相关的job记录需要清理
        print(f"\n检查相关的job记录...")
        job_keys_to_clean = []
        
        for retry_key in retry_keys:
            job_id = retry_key.replace('arq:retry:', '')
            job_key = f"arq:job:{job_id}"
            if await redis_client.exists(job_key):
                job_keys_to_clean.append(job_key)
        
        if job_keys_to_clean:
            print(f"发现 {len(job_keys_to_clean)} 个相关的job记录")
            confirm_jobs = input("是否也要清理这些job记录？输入 'yes' 确认: ")
            
            if confirm_jobs.lower() == 'yes':
                for job_key in job_keys_to_clean:
                    try:
                        await redis_client.delete(job_key)
                        print(f"✓ 已删除job记录: {job_key}")
                    except Exception as e:
                        print(f"✗ 删除job记录失败: {job_key} - {e}")
        
        print(f"\n建议:")
        print("1. 重启ARQ Worker服务，确保新的重试配置生效")
        print("2. 重新提交测试任务，验证任务恢复机制")
        print("3. 查看Worker启动日志，确认重试任务处理已启用")
        
    except Exception as e:
        print(f"清理失败: {e}")
        
    finally:
        await redis_client.close()

if __name__ == "__main__":
    asyncio.run(clean_retry_tasks())