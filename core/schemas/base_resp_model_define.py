'''
Description: 定义统一出口响应模型
Author: zyq
Date: 2025-07-31 14:45:30
LastEditors: zyq
LastEditTime: 2025-08-13 14:40:00
'''
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, Union, List
import time


class BaseResponse(BaseModel):
    code: int = Field(0, description="响应状态码，0表示成功，非0表示失败")
    msg: str = Field("success", description="响应信息")
    data: Union[str, Dict[str, Any], List] = Field("", description="响应数据")
    trace_id: Optional[str] = Field(None, description="请求追踪ID")
    timestamp: float = Field(default_factory=time.time, description="响应时间戳")

    @classmethod
    def success(cls, data: Union[str, Dict[str, Any]], trace_id: Optional[str] = None):
        """创建成功响应"""
        return cls(data=data, trace_id=trace_id)
    
    @classmethod
    def error(cls, code: int, msg: str, trace_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        """创建错误响应"""
        response_data = {"error_details": details} if details else ""
        return cls(code=code, msg=msg, data=response_data, trace_id=trace_id)


class BizResponse(BaseModel):
    """业务层响应模型"""
    biz_code: int = Field(0, description="业务响应状态码, 0代表正常, 非0代表异常")
    biz_msg: str = Field("", description="业务响应信息, 响应状态码不为0时返回")
    biz_ext: Optional[Dict[str, Any]] = Field(None, description="业务扩展信息")
    
    @classmethod
    def success(cls, data: Optional[Dict[str, Any]] = None):
        """创建业务成功响应"""
        return cls(biz_ext=data)
    
    @classmethod
    def error(cls, code: int, msg: str, ext_data: Optional[Dict[str, Any]] = None):
        """创建业务错误响应"""
        return cls(biz_code=code, biz_msg=msg, biz_ext=ext_data)


class ApiResponse(BaseModel):
    """完整API响应模型，包含业务数据和系统信息"""
    code: int = Field(0, description="HTTP响应状态码")
    msg: str = Field("success", description="响应信息")
    data: Union[str, Dict[str, Any], List, BizResponse] = Field("", description="响应数据")
    trace_id: Optional[str] = Field(None, description="请求追踪ID")
    timestamp: float = Field(default_factory=time.time, description="响应时间戳")
    
    @classmethod
    def success_with_biz(cls, biz_data: BizResponse, trace_id: Optional[str] = None):
        """创建包含业务数据的成功响应"""
        return cls(data=biz_data, trace_id=trace_id)
    
    @classmethod
    def success_with_data(cls, data: Union[str, Dict[str, Any], List], trace_id: Optional[str] = None):
        """创建包含原始数据的成功响应"""
        return cls(data=data, trace_id=trace_id)