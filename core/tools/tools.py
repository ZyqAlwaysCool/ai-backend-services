'''
Description: 工具函数
Author: zyq
Date: 2025-07-31 16:02:01
LastEditors: zyq
LastEditTime: 2025-08-01 09:25:08
'''
import os
import uuid
import time
import random
import string
import shutil
from fastapi import UploadFile
from typing import Tuple, Optional

def generate_unique_string(prefix: str = "", length: int = 8, use_timestamp: bool = True, use_uuid: bool = False) -> str:
    """
    生成唯一字符串的工具函数
    
    参数:
    - prefix: 可选的前缀字符串
    - length: 随机部分的长度（仅在不使用UUID时有效）
    - use_timestamp: 是否包含时间戳
    - use_uuid: 是否使用UUID（如果为True，length参数将被忽略）
    
    返回:
    生成的唯一字符串
    """
    components = []
    
    # 添加前缀（如果有）
    if prefix:
        components.append(prefix)
    
    # 添加时间戳（如果启用）
    if use_timestamp:
        timestamp = str(int(time.time() * 1000))  # 毫秒级时间戳
        components.append(timestamp)
    
    # 添加随机部分
    if use_uuid:
        # 使用UUID
        components.append(str(uuid.uuid4()))
    else:
        # 生成指定长度的随机字符串
        random_chars = ''.join(random.choices(
            string.ascii_letters + string.digits,
            k=length
        ))
        components.append(random_chars)
    
    # 组合所有部分
    return "-".join(components)


def get_local_ip() -> str:
    import socket
    """返回本机在内网中的 IPv4 地址"""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]