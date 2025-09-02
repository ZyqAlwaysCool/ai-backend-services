'''
Description: 提供临时文件的创建、存储、下载和过期清理功能
Author: zyq
Date: 2025-08-27 16:06:49
LastEditors: zyq
LastEditTime: 2025-09-01 09:18:05
'''

import os
import uuid
import asyncio
import shutil
from datetime import datetime, timedelta
from typing import Dict, Optional
from pathlib import Path
from loguru import logger


class FileManager:
    """文件管理器"""
    
    _startup_cleaned = False  # 类变量，记录是否已执行过启动清理
    
    def __init__(self, base_dir: str = "temp_files", default_expire_hours: int = 24):
        """初始化文件管理器"""
        self.base_dir = Path(base_dir)
        self.outputs_dir = self.base_dir / "outputs"  # 输出文件专用目录
        self.processing_dir = self.base_dir / "processing"  # 队列处理中的文件
        self.default_expire_hours = default_expire_hours
        
        # 文件元数据存储 {task_id: file_info} - 仅用于下载计数，不持久化
        self._file_registry: Dict[str, Dict] = {}
        
        # 确保目录结构存在
        self._ensure_directories()
        
        # 只在第一次实例化时执行启动清理
        if not FileManager._startup_cleaned:
            self._startup_cleanup()
            FileManager._startup_cleaned = True
        
        # 启动清理任务
        self._cleanup_task = None
        self._start_cleanup_task()
    
    def _ensure_directories(self):
        """确保目录结构存在"""
        for directory in [self.outputs_dir, self.processing_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        logger.info(f"File manager directories initialized: {self.base_dir}")
    
    def _startup_cleanup(self):
        """启动时只清理输出文件目录"""
        if self.outputs_dir.exists():
            logger.info(f"Cleaning up outputs directory on startup: {self.outputs_dir}")
            shutil.rmtree(self.outputs_dir)
            self.outputs_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"File manager initialized: {self.base_dir}")
    
    def _start_cleanup_task(self):
        """启动清理任务"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_files())
    
    def generate_task_id(self, prefix: str = "pdf") -> str:
        """生成任务ID"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        return f"{prefix}_{timestamp}_{unique_id}"
    
    def register_file(self, task_id: str, filename: str, file_path: str, expire_hours: Optional[int] = None) -> Dict:
        """注册文件到管理器"""
        expire_hours = expire_hours or self.default_expire_hours
        expire_at = datetime.now() + timedelta(hours=expire_hours)
        
        file_info = {
            "task_id": task_id,
            "filename": filename,
            "file_path": file_path,
            "created_at": datetime.now(),
            "expire_at": expire_at,
            "download_count": 0,
            "max_downloads": 50  # 最大下载次数
        }
        
        self._file_registry[task_id] = file_info
        logger.info(f"File registered: {task_id} -> {filename}, expires at {expire_at}")
        
        return file_info
    
    def get_file_info(self, task_id: str) -> Optional[Dict]:
        """获取输出文件信息 - 基于文件系统检查"""
        # 检查task_id是否过期 (基于时间戳解析)
        if not self._is_task_valid(task_id):
            logger.info(f"Task expired based on timestamp: {task_id}")
            return None
        
        # 构建文件路径并检查文件是否存在
        task_dir = self.outputs_dir / task_id
        if not task_dir.exists():
            logger.info(f"Task output directory not found: {task_id}")
            return None
        
        # 查找目录中的文件
        files = list(task_dir.glob("*"))
        if not files:
            logger.info(f"No output files found in task directory: {task_id}")
            return None
        
        file_path = files[0]  # 假设每个任务目录只有一个文件
        
        # 构建文件信息
        file_info = {
            "task_id": task_id,
            "filename": file_path.name,
            "file_path": str(file_path),
            "created_at": datetime.fromtimestamp(file_path.stat().st_ctime),
            "download_count": self._file_registry.get(task_id, {}).get("download_count", 0),
            "max_downloads": 50
        }
        
        return file_info
    
    def get_file_path(self, task_id: str) -> Optional[str]:
        """获取文件路径用于下载"""
        file_info = self.get_file_info(task_id)
        
        if not file_info:
            return None
        
        # 检查下载次数限制
        if file_info["download_count"] >= file_info["max_downloads"]:
            logger.warning(f"Download limit exceeded for {task_id}")
            return None
        
        # 增加下载计数
        file_info["download_count"] += 1
        self._file_registry[task_id] = file_info
        
        return file_info["file_path"]
    
    def create_file_path(self, task_id: str, filename: str) -> str:
        """创建输出文件存储路径"""
        # 使用任务ID作为子目录，避免文件名冲突
        task_dir = self.outputs_dir / task_id
        task_dir.mkdir(exist_ok=True)
        
        return str(task_dir / filename)
    
    def _is_task_valid(self, task_id: str) -> bool:
        """检查task_id是否在有效期内 - 基于时间戳解析"""
        try:
            # 解析task_id中的时间戳: pdf-to-docx-task_20250827_174251_393223ad
            parts = task_id.split('_')
            if len(parts) < 3:
                return False
            
            # 提取日期和时间部分
            date_part = parts[1]  # 20250827
            time_part = parts[2]  # 174251
            
            # 构建时间戳
            timestamp_str = f"{date_part}_{time_part}"
            created_time = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
            
            # 检查是否过期
            expire_time = created_time + timedelta(hours=self.default_expire_hours)
            return datetime.now() < expire_time
            
        except (ValueError, IndexError) as e:
            logger.warning(f"Invalid task_id format: {task_id}, error: {str(e)}")
            return False
    
    def _remove_file(self, task_id: str):
        """删除文件和记录"""
        file_info = self._file_registry.pop(task_id, None)
        
        if file_info:
            try:
                file_path = Path(file_info["file_path"])
                if file_path.exists():
                    file_path.unlink()
                
                # 删除任务目录（如果为空）
                task_dir = file_path.parent
                if task_dir.exists() and not any(task_dir.iterdir()):
                    task_dir.rmdir()
                
                logger.info(f"File removed: {task_id}")
                
            except Exception as e:
                logger.error(f"Failed to remove file {task_id}: {str(e)}")
    
    async def _cleanup_expired_files(self):
        """定期清理过期文件 - 基于文件系统扫描"""
        while True:
            try:
                if not self.base_dir.exists():
                    await asyncio.sleep(3600)
                    continue
                
                # 清理过期的输出文件
                expired_count = await self._cleanup_expired_outputs()
                
                # 清理孤儿处理文件
                orphan_count = await self._cleanup_orphan_processing_files()
                
                total_cleaned = expired_count + orphan_count
                
                if total_cleaned > 0:
                    logger.info(f"Cleaned up {total_cleaned} files (outputs: {expired_count}, processing: {orphan_count})")
                
                # 每小时检查一次
                await asyncio.sleep(3600)
                
            except Exception as e:
                logger.error(f"Error in cleanup task: {str(e)}")
                await asyncio.sleep(60)  # 出错时1分钟后重试
    
    def get_stats(self) -> Dict:
        """获取文件管理统计信息"""
        # 统计不同目录的文件数量
        outputs_count = len(list(self.outputs_dir.glob("*"))) if self.outputs_dir.exists() else 0
        processing_count = len(list(self.processing_dir.glob("*"))) if self.processing_dir.exists() else 0
        
        return {
            "outputs_count": outputs_count,
            "processing_count": processing_count,
            "total_downloads": sum(info["download_count"] for info in self._file_registry.values()),
            "registry_count": len(self._file_registry)
        }
    
    # ==================== 队列输入文件管理 ====================
    
    async def persist_input_file(self, source_path: str, original_filename: str) -> str:
        """
        将临时文件持久化到处理目录（避免中间件清理）
        
        Args:
            source_path: 源文件路径
            original_filename: 原始文件名
            
        Returns:
            持久化后的文件路径
        """
        try:
            # 获取文件扩展名
            file_ext = ""
            if "." in original_filename:
                file_ext = "." + original_filename.split(".")[-1]
            
            # 生成处理文件名（随机UUID + 原后缀）
            processing_filename = f"{uuid.uuid4().hex}{file_ext}"
            processing_path = self.processing_dir / processing_filename
            
            # 异步复制文件（避免阻塞）
            import asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, shutil.copy2, source_path, processing_path)
            
            logger.info(f"Persisted input file: {source_path} -> {processing_path}")
            return str(processing_path)
            
        except Exception as e:
            logger.error(f"Failed to persist input file: {str(e)}")
            raise
    
    def cleanup_input_file(self, processing_path: str):
        """清理队列输入文件"""
        try:
            if os.path.exists(processing_path):
                os.unlink(processing_path)
                logger.debug(f"Cleaned up input file: {processing_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup input file {processing_path}: {str(e)}")
    
    async def _cleanup_expired_outputs(self) -> int:
        """清理过期的输出文件"""
        if not self.outputs_dir.exists():
            return 0
        
        expired_count = 0
        for task_dir in self.outputs_dir.iterdir():
            if not task_dir.is_dir():
                continue
            
            task_id = task_dir.name
            if not self._is_task_valid(task_id):
                try:
                    shutil.rmtree(task_dir)
                    # 清理内存中的记录
                    self._file_registry.pop(task_id, None)
                    expired_count += 1
                    logger.debug(f"Removed expired output task: {task_id}")
                except Exception as e:
                    logger.error(f"Failed to remove expired output task {task_id}: {str(e)}")
        
        return expired_count
    
    async def _cleanup_orphan_processing_files(self) -> int:
        """清理孤儿处理文件（超过6小时的文件）"""
        if not self.processing_dir.exists():
            return 0
        
        cutoff_time = datetime.now() - timedelta(hours=6)
        cleaned_count = 0
        
        for file_path in self.processing_dir.glob("*"):
            if file_path.is_file():
                file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_mtime < cutoff_time:
                    try:
                        file_path.unlink()
                        cleaned_count += 1
                        logger.debug(f"Removed orphan processing file: {file_path}")
                    except Exception as e:
                        logger.error(f"Failed to cleanup orphan processing file {file_path}: {str(e)}")
        
        return cleaned_count