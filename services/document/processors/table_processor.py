'''
Description: 表格提取处理器
Author: zyq
Date: 2025-09-02
'''

import os
from typing import Dict, Any
from datetime import datetime
from loguru import logger

from core.schemas.file_models import FileInfo
from ..schemas import TableExtractRequest, TableExtractResponse, DocumentTaskTypePrefix
from ..utils.file_manager import FileManager
from .base_processor import BaseProcessor


class TableProcessor(BaseProcessor):
    """表格提取处理器"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.file_manager = FileManager()
    
    async def process(self, request: TableExtractRequest, temp_file_path: str, file_info: FileInfo, trace_id: str = None) -> TableExtractResponse:
        """
        执行XLSX表格提取
        
        Args:
            request: 表格提取请求
            temp_file_path: 临时文件路径
            file_info: 文件信息
            trace_id: 链路追踪ID
            
        Returns:
            表格提取响应
        """
        self._log_processing_start("TableProcessor", f"XLSX表格提取", trace_id)
        
        try:
            # 验证文件格式
            if not request.filename.lower().endswith('.xlsx'):
                raise ValueError("仅支持XLSX格式文件的表格提取")
            
            # 根据输出格式处理
            output_format = request.output_format or "html_text"
            logger.debug(f"TableProcessor output_format: {output_format} | request.output_format: {request.output_format}")
            
            if output_format == "html_text":
                # 直接返回HTML文本
                html_content = await self._extract_excel_to_html(temp_file_path, request, trace_id)
                
                self._log_processing_end("TableProcessor", "XLSX表格提取(html_text)", trace_id)
                
                return TableExtractResponse(
                    html_content=html_content,
                    download_url=None
                )
            
            elif output_format == "html_file":
                # 生成HTML文件并返回下载链接
                download_url = await self._extract_excel_to_html_file(temp_file_path, request, trace_id)
                
                self._log_processing_end("TableProcessor", "XLSX表格提取(html_file)", trace_id)
                
                return TableExtractResponse(
                    html_content=None,
                    download_url=download_url
                )
            
            else:
                raise ValueError(f"不支持的输出格式: {output_format}，支持格式: html_text, html_file")
            
        except Exception as e:
            self._log_error("TableProcessor", trace_id, e)
            self._log_processing_end("TableProcessor", "XLSX表格提取", trace_id, success=False)
            raise e
    
    async def _extract_excel_to_html(self, source_path: str, request: TableExtractRequest, trace_id: str) -> str:
        """将Excel表格转换为HTML格式"""
        try:
            import pandas as pd
            
            # 读取Excel文件
            excel_file = pd.ExcelFile(source_path)
            
            html_parts = []
            html_parts.append(f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>表格提取结果 - {request.filename}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; border-bottom: 1px solid #bdc3c7; padding-bottom: 5px; margin-top: 30px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; font-weight: bold; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        .sheet-info {{ background-color: #ecf0f1; padding: 10px; border-radius: 5px; margin: 10px 0; }}
    </style>
</head>
<body>
    <h1>Excel表格提取结果</h1>
    <div class="sheet-info">
        <strong>源文件：</strong>{request.filename}<br>
        <strong>提取时间：</strong>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
        <strong>工作表数量：</strong>{len(excel_file.sheet_names)}
    </div>
""")
            
            # 处理每个工作表
            for sheet_name in excel_file.sheet_names:
                try:
                    # 读取工作表数据
                    df = pd.read_excel(source_path, sheet_name=sheet_name)
                    
                    # 跳过空工作表
                    if df.empty:
                        html_parts.append(f'<h2>工作表: {sheet_name}</h2>')
                        html_parts.append('<p><em>此工作表为空</em></p>')
                        continue
                    
                    # 添加工作表标题
                    html_parts.append(f'<h2>工作表: {sheet_name}</h2>')
                    
                    # 转换为HTML表格
                    table_html = df.to_html(
                        index=False,  # 不显示行索引
                        escape=False,  # 允许HTML标签
                        classes='table',
                        table_id=f'table_{sheet_name}',
                        border=0  # 使用CSS样式控制边框
                    )
                    
                    html_parts.append(table_html)
                    
                    # 添加工作表统计信息
                    html_parts.append(f'<div class="sheet-info">')
                    html_parts.append(f'<small>行数: {len(df)} | 列数: {len(df.columns)}</small>')
                    html_parts.append(f'</div>')
                    
                except Exception as e:
                    logger.warning(f"工作表处理失败 - Sheet: {sheet_name} | Error: {e}")
                    html_parts.append(f'<h2>工作表: {sheet_name}</h2>')
                    html_parts.append(f'<p><em>工作表处理失败: {str(e)}</em></p>')
            
            html_parts.append('</body></html>')
            
            html_content = '\n'.join(html_parts)
            
            return html_content
            
        except ImportError:
            raise Exception("缺少pandas或openpyxl依赖库")
        except Exception as e:
            raise Exception(f"Excel表格转HTML失败: {str(e)}")
    
    async def _extract_excel_to_html_file(self, source_path: str, request: TableExtractRequest, trace_id: str) -> str:
        """将Excel表格转换为HTML文件并返回下载链接"""
        try:
            # 生成HTML内容
            html_content = await self._extract_excel_to_html(source_path, request, trace_id)
            
            # 生成任务ID和输出文件路径
            task_id = self.file_manager.generate_task_id("table-extract-task")
            output_filename = f"{request.filename.rsplit('.', 1)[0]}.html"
            output_path = self.file_manager.create_file_path(task_id, output_filename)
            
            # 保存HTML文件
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            # 注册文件到文件管理器
            self.file_manager.register_file(task_id, output_filename, output_path, expire_hours=24)
            
            # 生成下载链接
            download_url = f"/document/extract-download?task_id={task_id}"
            
            return download_url
            
        except Exception as e:
            raise Exception(f"Excel表格转HTML文件失败: {str(e)}")