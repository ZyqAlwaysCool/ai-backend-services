#!/usr/bin/env python3
"""
检查Redis中ARQ任务的存储情况
用于分析服务重启后任务恢复机制
"""

import asyncio
import redis.asyncio as redis
from datetime import datetime
from core.config.config_center import get_app_config

async def check_arq_tasks():
    """检查ARQ任务存储情况"""
    
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
        print("ARQ任务存储情况检查")
        print("=" * 60)
        print(f"Redis: {app_config.redis_host}:{app_config.redis_port}/{app_config.redis_db}")
        print(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # 1. 检查ARQ相关的所有keys
        print("1. ARQ相关的Redis Keys:")
        arq_keys = await redis_client.keys("arq:*")
        if arq_keys:
            for key in sorted(arq_keys):
                key_type = await redis_client.type(key)
                if key_type == 'list':
                    length = await redis_client.llen(key)
                    print(f"   {key} ({key_type}) - 长度: {length}")
                elif key_type == 'hash':
                    length = await redis_client.hlen(key)
                    print(f"   {key} ({key_type}) - 字段数: {length}")
                elif key_type == 'set':
                    length = await redis_client.scard(key)
                    print(f"   {key} ({key_type}) - 元素数: {length}")
                else:
                    print(f"   {key} ({key_type})")
        else:
            print("   未找到ARQ相关的keys")
        print()
        
        # 2. 检查队列中的任务
        queue_key = "arq:queue"
        try:
            key_type = await redis_client.type(queue_key)
            print(f"2. 任务队列状态:")
            print(f"   队列名称: {queue_key}")
            print(f"   队列类型: {key_type}")
            
            if key_type == 'list':
                queue_length = await redis_client.llen(queue_key)
                print(f"   待处理任务数: {queue_length}")
                
                if queue_length > 0:
                    print("   队列中的任务:")
                    # 查看队列中的前10个任务
                    tasks = await redis_client.lrange(queue_key, 0, min(9, queue_length-1))
                    for i, task in enumerate(tasks):
                        print(f"     [{i+1}] {task[:100]}..." if len(task) > 100 else f"     [{i+1}] {task}")
            elif key_type == 'none':
                print(f"   队列不存在或为空")
            else:
                print(f"   队列类型异常: {key_type}")
                # 如果不是list类型，尝试获取内容看看
                if key_type == 'string':
                    content = await redis_client.get(queue_key)
                    print(f"   内容: {content[:200]}...")
        except Exception as e:
            print(f"   检查队列失败: {e}")
        print()
        
        # 3. 检查作业详情keys
        job_keys = await redis_client.keys("arq:job:*")
        print(f"3. 作业详情:")
        print(f"   作业数量: {len(job_keys)}")
        
        if job_keys:
            print("   作业状态分布:")
            status_count = {}
            
            for job_key in job_keys[:20]:  # 只检查前20个作业
                try:
                    job_data = await redis_client.hgetall(job_key)
                    if job_data:
                        status = job_data.get('status', 'unknown')
                        status_count[status] = status_count.get(status, 0) + 1
                        
                        # 显示作业详情
                        if len(job_keys) <= 10:  # 只有少量作业时显示详情
                            job_id = job_key.replace('arq:job:', '')
                            enqueue_time = job_data.get('enqueue_time', 'N/A')
                            function = job_data.get('function', 'N/A')
                            print(f"     作业ID: {job_id}")
                            print(f"     状态: {status}")
                            print(f"     函数: {function}")
                            print(f"     入队时间: {enqueue_time}")
                            print(f"     ---")
                            
                except Exception as e:
                    print(f"     读取作业 {job_key} 失败: {e}")
            
            print("   状态统计:")
            for status, count in status_count.items():
                print(f"     {status}: {count}")
        print()
        
        # 4. 检查结果存储
        result_keys = await redis_client.keys("arq:result:*")
        print(f"4. 任务结果:")
        print(f"   结果数量: {len(result_keys)}")
        
        if result_keys and len(result_keys) <= 5:
            for result_key in result_keys:
                try:
                    result_data = await redis_client.get(result_key)
                    ttl = await redis_client.ttl(result_key)
                    print(f"   {result_key} (TTL: {ttl}s)")
                    if result_data and len(result_data) < 200:
                        print(f"     数据: {result_data}")
                except Exception as e:
                    print(f"     读取结果 {result_key} 失败: {e}")
        print()
        
        # 5. 检查ARQ特定的配置或元数据
        print("5. ARQ系统信息:")
        arq_info_keys = await redis_client.keys("arq:*")
        system_keys = [k for k in arq_info_keys if not k.startswith(('arq:job:', 'arq:result:', 'arq:queue'))]
        for key in system_keys:
            key_type = await redis_client.type(key)
            print(f"   {key} ({key_type})")
        
        # 6. 检查重试队列 (重要发现!)
        retry_keys = await redis_client.keys("arq:retry:*")
        print(f"6. 重试队列状态:")
        print(f"   重试任务数量: {len(retry_keys)}")
        
        if retry_keys:
            print("   重试任务详情:")
            for retry_key in retry_keys[:10]:  # 只显示前10个
                try:
                    retry_data = await redis_client.get(retry_key)
                    ttl = await redis_client.ttl(retry_key)
                    job_id = retry_key.replace('arq:retry:', '')
                    print(f"     任务ID: {job_id}")
                    print(f"     TTL: {ttl}s")
                    if retry_data and len(retry_data) < 500:
                        print(f"     数据: {retry_data[:200]}...")
                    print(f"     ---")
                except Exception as e:
                    print(f"     读取重试任务 {retry_key} 失败: {e}")
        print()
        
        print("=" * 60)
        
        # 7. 总结和建议
        print("任务恢复分析:")
        
        # 检查主队列
        try:
            main_queue_length = 0
            if await redis_client.type("arq:queue") == 'list':
                main_queue_length = await redis_client.llen("arq:queue")
        except:
            main_queue_length = 0
            
        if main_queue_length > 0:
            print(f"✓ Redis中有 {main_queue_length} 个待处理任务")
            print("✓ 服务重启后ARQ Worker会自动处理这些任务")
        else:
            print("! 主队列为空")
            
        if len(retry_keys) > 0:
            print(f"! 发现 {len(retry_keys)} 个重试队列任务")
            print("! 这些任务可能是之前执行失败的任务")
            print("! ARQ Worker重启后会根据重试策略处理这些任务")
            
        if len(job_keys) > 0:
            print(f"✓ 发现 {len(job_keys)} 个作业记录")
            print("✓ ARQ会维护这些作业的状态和结果")
        
        # 特别提醒
        if len(retry_keys) > 0 and main_queue_length == 0:
            print("\n⚠️  重要发现:")
            print("   - 主队列为空，但有重试队列任务")
            print("   - 可能的原因：")
            print("     1. 任务执行失败，进入重试队列")
            print("     2. Worker配置问题导致任务无法正确处理")
            print("     3. 函数注册问题")
            print("   - 建议检查Worker启动日志和任务函数注册情况")
        
    except Exception as e:
        print(f"检查失败: {e}")
        
    finally:
        await redis_client.close()

if __name__ == "__main__":
    asyncio.run(check_arq_tasks())