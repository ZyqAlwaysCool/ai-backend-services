'''
Description: MongoDB任务存储后端实现, 基于MongoDB实现的任务状态存储后端, 支持不同任务类型存储到不同collection
Author: zyq
Date: 2025-08-28 10:15:32
LastEditors: zyq
LastEditTime: 2025-08-29 16:24:32
'''

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from loguru import logger

from ..base.storage_backend import StorageBackend
from ..models.task_models import (
    BaseTask, BatchTask, TaskResult, TaskQuery, TaskStatus, TaskType,
    SubTaskResult
)
from core.storage.mongo_storage import MongoStorage
from ..registry import collection_registry


class MongoTaskStorage(StorageBackend):
    """MongoDB任务存储后端实现"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化MongoDB存储后端
        
        Args:
            config: MongoDB配置参数
        """
        self.config = config or {}
        
        # 数据库名称
        self.db_name = self.config.get('db_name', 'ai_backend_services')
        
        # 存储实例缓存 {collection_name: MongoStorage}
        self.storage_instances = {}
        
        logger.info(f"MongoDB task storage initialized for database: {self.db_name}")
        # 在需要时动态获取映射，避免固化问题
        self._log_current_mappings()
    
    def _log_current_mappings(self):
        """记录当前映射状态用于调试"""
        current_mappings = collection_registry.get_mappings()
        logger.info(f"Collection mapping: {current_mappings}")
    
    def _get_current_collection_mapping(self) -> Dict[str, str]:
        """动态获取最新的collection映射"""
        return collection_registry.get_mappings()
    
    def get_storage_instance(self, task_type: str = None) -> MongoStorage:
        """
        根据任务类型获取对应的存储实例
        
        Args:
            task_type: 任务类型标识
            
        Returns:
            MongoDB存储实例
        """
        # 动态获取最新的collection映射
        current_mapping = self._get_current_collection_mapping()
        
        # 确定collection名称
        collection_name = current_mapping.get(
            task_type, 
            current_mapping['default']
        )
        
        # 返回缓存的存储实例或创建新实例
        if collection_name not in self.storage_instances:
            self.storage_instances[collection_name] = MongoStorage(
                self.db_name, 
                collection_name
            )
        
        return self.storage_instances[collection_name]
    
    def _task_to_dict(self, task: BaseTask) -> Dict[str, Any]:
        """将任务对象转换为字典"""
        task_dict = task.model_dump()
        
        # 处理datetime字段
        for field in ['created_at', 'started_at', 'completed_at']:
            if field in task_dict and task_dict[field]:
                if isinstance(task_dict[field], datetime):
                    task_dict[field] = task_dict[field].isoformat()
        
        # 处理子任务结果中的datetime字段
        if 'sub_results' in task_dict:
            for sub_result in task_dict['sub_results']:
                if isinstance(sub_result.get('created_at'), datetime):
                    sub_result['created_at'] = sub_result['created_at'].isoformat()
        
        return task_dict
    
    def _dict_to_task(self, task_dict: Dict[str, Any]) -> BaseTask:
        """将字典转换为任务对象"""
        # 处理datetime字段
        for field in ['created_at', 'started_at', 'completed_at']:
            if field in task_dict and task_dict[field]:
                if isinstance(task_dict[field], str):
                    task_dict[field] = datetime.fromisoformat(task_dict[field])
        
        # 处理子任务结果中的datetime字段
        if 'sub_results' in task_dict:
            for sub_result in task_dict['sub_results']:
                if isinstance(sub_result.get('created_at'), str):
                    sub_result['created_at'] = datetime.fromisoformat(sub_result['created_at'])
        
        # 根据任务类型创建对象
        task_type = task_dict.get('task_type')
        if task_type == TaskType.BATCH_PROCESSING:
            return BatchTask(**task_dict)
        else:
            return BaseTask(**task_dict)
    
    def _extract_task_type_key(self, task: BaseTask) -> str:
        """
        从任务对象中提取用于collection映射的类型键
        
        Args:
            task: 任务对象
            
        Returns:
            类型键字符串
        """
        # 1. 优先从任务的metadata中获取
        if hasattr(task, 'metadata') and task.metadata:
            if 'collection_type' in task.metadata:
                return task.metadata['collection_type']
        
        # 2. 默认使用default collection
        return 'default'
    
    def _extract_task_type_key_from_id(self, task_id: str) -> str:
        """
        从task_id中提取collection类型键 - O(1)查找
        
        Args:
            task_id: 任务ID (格式: {prefix}_{timestamp}_{uuid})
            
        Returns:
            collection类型键
        """
        # 使用注册表的前缀映射进行O(1)查找
        return collection_registry.get_collection_by_task_id(task_id)
    
    async def create_task(self, task: BaseTask) -> bool:
        """创建任务记录"""
        try:
            task_type_key = self._extract_task_type_key(task)
            storage = self.get_storage_instance(task_type_key)
            
            task_dict = self._task_to_dict(task)
            storage.create_record(task_dict)
            
            logger.info(f"Task created in collection '{storage.col.name}': {task.task_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create task {task.task_id}: {str(e)}")
            return False
    
    async def get_task(self, task_id: str) -> Optional[BaseTask]:
        """获取任务信息 - 使用直接定位优化性能"""
        try:
            # 直接定位到正确的collection查找 - 
            task_type_key = self._extract_task_type_key_from_id(task_id)
            storage = self.get_storage_instance(task_type_key)
            
            records = storage.find_record({'task_id': task_id})
            if records:
                task_dict = records[0]
                task_dict.pop('_id', None)
                return self._dict_to_task(task_dict)
            
            # 如果直接定位失败，fallback到遍历查找（容错机制）
            logger.warning(f"Task not found in predicted collection {task_type_key}, trying all collections")
            
            current_mapping = self._get_current_collection_mapping()
            for fallback_type_key, collection_name in current_mapping.items():
                if fallback_type_key == task_type_key:
                    continue  # 跳过已经尝试的
                    
                storage = self.get_storage_instance(fallback_type_key)
                records = storage.find_record({'task_id': task_id})
                
                if records:
                    task_dict = records[0]
                    task_dict.pop('_id', None)
                    logger.debug(f"Task found via fallback in {fallback_type_key}: {task_id}")
                    return self._dict_to_task(task_dict)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get task {task_id}: {str(e)}")
            return None
    
    async def update_task_status(
        self, 
        task_id: str, 
        status: TaskStatus,
        **kwargs
    ) -> bool:
        """更新任务状态"""
        try:
            update_data = {'status': status.value}
            
            # 根据状态更新时间字段
            if status == TaskStatus.PROCESSING:
                update_data['started_at'] = datetime.now().isoformat()
            elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                update_data['completed_at'] = datetime.now().isoformat()
            
            # 添加其他更新字段
            for key, value in kwargs.items():
                if value is not None:
                    if isinstance(value, datetime):
                        update_data[key] = value.isoformat()
                    else:
                        update_data[key] = value
            
            # 直接定位到正确的collection更新 - 
            task_type_key = self._extract_task_type_key_from_id(task_id)
            storage = self.get_storage_instance(task_type_key)
            
            try:
                storage.update_record({'task_id': task_id}, update_data)
                logger.debug(f"Task status updated: {task_id} -> {status.value} in {task_type_key}")
                return True
            except Exception as e:
                # 如果直接定位失败，fallback到遍历查找（容错机制）
                logger.warning(f"Failed to update in predicted collection {task_type_key}, trying all collections")
                
                current_mapping = self._get_current_collection_mapping()
                for fallback_type_key in current_mapping.keys():
                    if fallback_type_key == task_type_key:
                        continue  # 跳过已经尝试的
                        
                    storage = self.get_storage_instance(fallback_type_key)
                    try:
                        storage.update_record({'task_id': task_id}, update_data)
                        logger.debug(f"Task status updated via fallback: {task_id} -> {status.value} in {fallback_type_key}")
                        return True
                    except Exception:
                        continue
                
                logger.warning(f"Task not found in any collection: {task_id}")
                return False
            
        except Exception as e:
            logger.error(f"Failed to update task status {task_id}: {str(e)}")
            return False
    
    async def update_task_progress(
        self, 
        task_id: str, 
        processed_items: int,
        successful_items: int = None,
        failed_items: int = None
    ) -> bool:
        """更新任务进度"""
        try:
            update_data = {'processed_items': processed_items}
            
            if successful_items is not None:
                update_data['successful_items'] = successful_items
            
            if failed_items is not None:
                update_data['failed_items'] = failed_items
            
            # 直接定位到正确的collection更新 - 
            task_type_key = self._extract_task_type_key_from_id(task_id)
            storage = self.get_storage_instance(task_type_key)
            
            try:
                storage.update_record({'task_id': task_id}, update_data)
                logger.debug(f"Task progress updated: {task_id} -> {processed_items} in {task_type_key}")
                return True
            except Exception as e:
                # 容错机制：如果直接定位失败，尝试其他collection
                logger.warning(f"Failed to update progress in predicted collection {task_type_key}, trying fallback")
                
                current_mapping = self._get_current_collection_mapping()
                for fallback_type_key in current_mapping.keys():
                    if fallback_type_key == task_type_key:
                        continue
                        
                    storage = self.get_storage_instance(fallback_type_key)
                    try:
                        storage.update_record({'task_id': task_id}, update_data)
                        logger.debug(f"Task progress updated via fallback: {task_id} in {fallback_type_key}")
                        return True
                    except Exception:
                        continue
                
                logger.warning(f"Task not found in any collection: {task_id}")
                return False
            
        except Exception as e:
            logger.error(f"Failed to update task progress {task_id}: {str(e)}")
            return False
    
    async def add_sub_task_result(
        self, 
        task_id: str, 
        sub_task_id: str,
        status: TaskStatus,
        result: Any = None,
        error_message: str = None,
        processing_time: float = None
    ) -> bool:
        """添加子任务结果"""
        try:
            # 构建子任务结果
            sub_result = SubTaskResult(
                sub_task_id=sub_task_id,
                status=status,
                result=result,
                error_message=error_message,
                processing_time=processing_time
            )
            
            # 获取当前任务
            task = await self.get_task(task_id)
            if not task or not isinstance(task, BatchTask):
                logger.error(f"Task not found or not a batch task: {task_id}")
                return False
            
            # 添加子任务结果
            task.sub_results.append(sub_result)
            
            # 确定存储实例
            task_type_key = self._extract_task_type_key(task)
            storage = self.get_storage_instance(task_type_key)
            
            # 更新存储
            sub_results_dict = [sr.dict() for sr in task.sub_results]
            storage.update_record(
                {'task_id': task_id}, 
                {'sub_results': sub_results_dict}
            )
            
            logger.debug(f"Sub task result added: {task_id} -> {sub_task_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add sub task result {task_id}/{sub_task_id}: {str(e)}")
            return False
    
    async def save_task_result(
        self, 
        task_id: str, 
        result: TaskResult
    ) -> bool:
        """保存任务结果"""
        try:
            result_dict = result.dict()
            
            # 处理datetime字段
            if isinstance(result_dict.get('created_at'), datetime):
                result_dict['created_at'] = result_dict['created_at'].isoformat()
            
            # 更新任务记录，添加结果信息
            update_data = {
                'result_data': result_dict.get('result_data'),
                'result_metadata': result_dict.get('metadata', {}),
                'execution_time': result_dict.get('execution_time'),
                'memory_usage': result_dict.get('memory_usage')
            }
            
            # 尝试在所有collection中更新
            updated = False
            current_mapping = self._get_current_collection_mapping()
            for task_type_key in current_mapping.keys():
                storage = self.get_storage_instance(task_type_key)
                try:
                    storage.update_record({'task_id': task_id}, update_data)
                    updated = True
                    break
                except Exception:
                    continue
            
            if updated:
                logger.info(f"Task result saved: {task_id}")
                return True
            else:
                logger.warning(f"Task not found for result save: {task_id}")
                return False
            
        except Exception as e:
            logger.error(f"Failed to save task result {task_id}: {str(e)}")
            return False
    
    async def query_tasks(self, query: TaskQuery) -> List[BaseTask]:
        """查询任务列表"""
        try:
            all_tasks = []
            
            # 从所有collection中查询
            current_mapping = self._get_current_collection_mapping()
            for task_type_key in current_mapping.keys():
                storage = self.get_storage_instance(task_type_key)
                
                # 构建查询条件
                filter_dict = {}
                
                if query.task_id:
                    filter_dict['task_id'] = query.task_id
                
                if query.task_type:
                    filter_dict['task_type'] = query.task_type.value
                
                if query.status:
                    filter_dict['status'] = query.status.value
                
                # 时间范围查询
                if query.created_after or query.created_before:
                    created_filter = {}
                    if query.created_after:
                        created_filter['$gte'] = query.created_after.isoformat()
                    if query.created_before:
                        created_filter['$lte'] = query.created_before.isoformat()
                    filter_dict['created_at'] = created_filter
                
                # 查询当前collection
                try:
                    records = storage.find_record(filter_dict)
                    
                    # 转换为任务对象
                    for record in records:
                        record.pop('_id', None)
                        try:
                            task = self._dict_to_task(record)
                            all_tasks.append(task)
                        except Exception as e:
                            logger.warning(f"Failed to convert record to task: {str(e)}")
                            continue
                            
                except Exception as e:
                    logger.warning(f"Failed to query collection {storage.col.name}: {str(e)}")
                    continue
            
            # 排序和分页
            all_tasks.sort(key=lambda x: x.created_at, reverse=True)
            start_idx = query.offset
            end_idx = start_idx + query.limit
            
            return all_tasks[start_idx:end_idx]
            
        except Exception as e:
            logger.error(f"Failed to query tasks: {str(e)}")
            return []
    
    async def delete_task(self, task_id: str) -> bool:
        """删除任务记录"""
        try:
            deleted = False
            current_mapping = self._get_current_collection_mapping()
            for task_type_key in current_mapping.keys():
                storage = self.get_storage_instance(task_type_key)
                try:
                    storage.delete_record({'task_id': task_id})
                    deleted = True
                    break
                except Exception:
                    continue
            
            if deleted:
                logger.info(f"Task deleted: {task_id}")
                return True
            else:
                logger.warning(f"Task not found for deletion: {task_id}")
                return False
            
        except Exception as e:
            logger.error(f"Failed to delete task {task_id}: {str(e)}")
            return False
    
    async def cleanup_expired_tasks(self, days: int = 30) -> int:
        """清理过期任务"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            total_cleaned = 0
            
            current_mapping = self._get_current_collection_mapping()
            for task_type_key in current_mapping.keys():
                storage = self.get_storage_instance(task_type_key)
                
                try:
                    # 查找过期任务
                    expired_filter = {
                        'created_at': {'$lt': cutoff_date.isoformat()},
                        'status': {'$in': [
                            TaskStatus.COMPLETED.value, 
                            TaskStatus.FAILED.value, 
                            TaskStatus.CANCELLED.value
                        ]}
                    }
                    
                    expired_records = storage.find_record(expired_filter)
                    
                    # 删除过期任务
                    for record in expired_records:
                        storage.delete_record({'_id': record['_id']})
                        total_cleaned += 1
                        
                except Exception as e:
                    logger.warning(f"Failed to cleanup expired tasks in {storage.col.name}: {str(e)}")
                    continue
            
            logger.info(f"Cleaned up {total_cleaned} expired tasks older than {days} days")
            return total_cleaned
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired tasks: {str(e)}")
            return 0
    
    async def get_task_statistics(
        self, 
        task_type: str = None, 
        days: int = 7
    ) -> Dict[str, Any]:
        """获取任务统计信息"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            all_stats = {
                'total_tasks': 0,
                'pending_tasks': 0,
                'processing_tasks': 0,
                'completed_tasks': 0,
                'failed_tasks': 0,
                'cancelled_tasks': 0,
                'avg_execution_time': 0.0,
                'success_rate': 0.0
            }
            
            execution_times = []
            
            # 从所有或指定类型的collection中收集统计信息
            collections_to_check = []
            if task_type:
                collections_to_check = [task_type]
            else:
                current_mapping = self._get_current_collection_mapping()
                collections_to_check = list(current_mapping.keys())
            
            for task_type_key in collections_to_check:
                storage = self.get_storage_instance(task_type_key)
                
                try:
                    # 构建查询条件
                    filter_dict = {
                        'created_at': {'$gte': cutoff_date.isoformat()}
                    }
                    
                    records = storage.find_record(filter_dict)
                    
                    for record in records:
                        all_stats['total_tasks'] += 1
                        
                        status = record.get('status', '')
                        if f'{status}_tasks' in all_stats:
                            all_stats[f'{status}_tasks'] += 1
                        
                        # 收集执行时间
                        exec_time = record.get('execution_time')
                        if exec_time:
                            execution_times.append(exec_time)
                            
                except Exception as e:
                    logger.warning(f"Failed to get statistics from {storage.col.name}: {str(e)}")
                    continue
            
            # 计算平均执行时间
            if execution_times:
                all_stats['avg_execution_time'] = sum(execution_times) / len(execution_times)
            
            # 计算成功率
            completed_and_failed = all_stats['completed_tasks'] + all_stats['failed_tasks']
            if completed_and_failed > 0:
                all_stats['success_rate'] = (all_stats['completed_tasks'] / completed_and_failed) * 100
            
            return all_stats
            
        except Exception as e:
            logger.error(f"Failed to get task statistics: {str(e)}")
            return {}