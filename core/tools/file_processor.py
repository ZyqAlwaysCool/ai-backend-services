'''
Description: 文件预处理工具
Author: zyq
Date: 2025-07-31 17:09:03
LastEditors: zyq
LastEditTime: 2025-08-07 16:12:56
'''
import os
from typing import List, Optional, Set, Tuple, Dict, Any
import docx
import re
from fastapi import UploadFile
import shutil
from spire.doc import *
from spire.doc.common import *
from docx import Document as DocxDocument
import random
import string
import hashlib
import time

from loguru import logger


class FileProcessor:
    def __init__(self, allowed_extensions: Optional[Set[str]] = None):
        """初始化文件预处理器

        Args:
            allowed_extensions (Optional[Set[str]], optional): 允许的文件扩展名集合. Defaults to None.
        """
        
        self.allowed_extensions = allowed_extensions or {'.docx', '.txt'}

    async def extract_text(self, file: UploadFile) -> Tuple[Optional[str], str]:
        """
        从 UploadFile 对象提取文本内容

        Args:
            file: FastAPI UploadFile 对象

        Returns:
            Tuple[Optional[str], str]: (提取的文本内容, 错误信息或成功信息)
        """
        _, ext = os.path.splitext(file.filename)
        ext = ext.lower()

        try:
            if ext == '.docx':
                doc = docx.Document(file.file)
                text = '\n'.join([para.text for para in doc.paragraphs if para.text.strip()])
                return text, "Successfully extracted text from docx"
            elif ext == '.txt':
                content = await file.read()
                text = content.decode('utf-8')
                return text, "Successfully extracted text from txt"
            else:
                return None, f"Unsupported file extension: {ext}"
        except Exception as e:
            return None, f"Failed to extract text: {str(e)}"
        finally:
            await file.seek(0)  # 确保文件指针复位
    
    def save_upload_file(self, file: UploadFile, save_path: str) -> str:
        """保存上传的文件到指定路径"""
        if not os.path.exists(save_path):
            os.makedirs(save_path)
        
        fpath = os.path.join(save_path, file.filename)
        with open(fpath, 'wb') as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        return os.path.abspath(fpath)
    
    def save_md_text_to_docx(self, md_text: str, save_path: str) -> bool:
        """将 Markdown 文本保存为 .docx 文件"""
        import pypandoc
        
        try:
            pypandoc.convert_text(md_text, to='docx', format="markdown", outputfile=save_path)
        except Exception as e:
            logger.error(f"convert md text to docx failed. error: {str(e)}")
            return False
        return True