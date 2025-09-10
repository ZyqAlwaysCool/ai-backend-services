"""
表格提取器

从PDF页面中提取表格并转换为HTML格式。
"""

import asyncio
from typing import Dict, Any, List
from loguru import logger


class TableExtractor:
    """表格内容提取器"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化表格提取器"""
        self.config = config
    
    async def extract_from_page(self, page, page_num: int) -> List[Dict]:
        """从PDF页面提取表格块"""
        try:
            # 将同步操作移到线程池中执行
            tables = await asyncio.to_thread(page.find_tables)
            
            # 表格处理也可能耗时，放到线程池中
            table_blocks = await asyncio.to_thread(
                self._process_tables, tables, page_num
            )
            
            return table_blocks
            
        except Exception as e:
            logger.error(f"Failed to extract tables from page {page_num}: {str(e)}")
            return []
    
    def _process_tables(self, tables, page_num: int) -> List[Dict]:
        """处理表格（同步方法）"""
        table_blocks = []
        
        for table_index, table in enumerate(tables):
            try:
                # 提取表格数据
                table_rows = table.extract()
                if table_rows:
                    # 转换为HTML格式
                    table_html = self._convert_table_to_html(
                        table_rows, 
                        f"page{page_num + 1}_table{table_index + 1}"
                    )
                    
                    table_blocks.append({
                        "type": "table",
                        "bbox": table.bbox,
                        "y": table.bbox[1],
                        "x": table.bbox[0],
                        "content": f"\n[表格 {page_num + 1}-{table_index + 1}]\n{table_html}\n"
                    })
                    
            except Exception as e:
                logger.warning(f"Failed to extract table {table_index} from page {page_num}: {str(e)}")
                continue
        
        return table_blocks
    
    def _convert_table_to_html(self, table_data: List, table_id: str = "") -> str:
        """将表格数据转换为HTML格式"""
        if not table_data or not table_data[0]:
            return "<p>表格数据为空</p>"
        
        html_parts = [
            f'<table id="{table_id}" class="extracted-table" border="1" '
            f'style="border-collapse: collapse; margin: 10px 0;">'
        ]
        
        # 第一行作为表头
        if table_data:
            html_parts.append("<thead><tr>")
            for header in table_data[0]:
                html_parts.append(
                    f"<th style='padding: 5px; background-color: #f0f0f0;'>"
                    f"{header if header else ''}</th>"
                )
            html_parts.append("</tr></thead>")
        
        # 其余行作为表体
        if len(table_data) > 1:
            html_parts.append("<tbody>")
            for row in table_data[1:]:
                html_parts.append("<tr>")
                for cell in row:
                    html_parts.append(
                        f"<td style='padding: 5px; border: 1px solid #ccc;'>"
                        f"{cell if cell else ''}</td>"
                    )
                html_parts.append("</tr>")
            html_parts.append("</tbody>")
        
        html_parts.append("</table>")
        return "\n".join(html_parts)