"""
Description: 文件处理相关数据模型
Author: zyq
"""
from typing import Optional
from pydantic import BaseModel, Field, validator


class FileInput(BaseModel):
    """统一文件输入格式"""
    input_type: str = Field(..., description="输入类型: file | base64")
    # file类型时，使用multipart/form-data上传
    # base64类型时，使用以下字段
    file_data: Optional[str] = Field(None, description="文件base64编码")
    filename: str = Field(..., description="文件名")
    file_size: Optional[int] = Field(None, description="文件大小(字节)，用于验证")
    
    @validator('input_type')
    def validate_input_type(cls, v):
        if v not in ['file', 'base64']:
            raise ValueError('input_type必须是file或base64')
        return v
    
    @validator('file_data')
    def validate_file_data(cls, v, values):
        if values.get('input_type') == 'base64' and not v:
            raise ValueError('base64输入时file_data不能为空')
        return v
    
    @validator('file_size')
    def validate_file_size(cls, v):
        if v is not None and v <= 0:
            raise ValueError('file_size必须大于0')
        return v


class FileInfo(BaseModel):
    """文件信息模型"""
    filename: str = Field(..., description="文件名")
    file_size: int = Field(..., description="文件大小(字节)")
    content_type: Optional[str] = Field(None, description="MIME类型")
    input_type: str = Field(..., description="输入类型: file | base64")
    temp_file_path: Optional[str] = Field(None, description="临时文件路径")