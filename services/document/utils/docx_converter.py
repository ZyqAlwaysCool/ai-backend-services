'''
Description: 支持分层降级策略的DOCX文档生成器
Author: zyq
Date: 2025-08-27 16:09:23
LastEditors: zyq
LastEditTime: 2025-08-27 16:24:39
'''
import re
import base64
from io import BytesIO
from typing import Dict, Any, Optional
from loguru import logger
from docx import Document
from docx.shared import Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from bs4 import BeautifulSoup


class ConversionMetrics:
    """转换监控指标"""
    
    def __init__(self):
        self.advanced_success = 0
        self.simple_fallback = 0
        self.basic_fallback = 0
        self.total_conversions = 0
        self.error_details = []
    
    def record_result(self, level: str, error_msg: Optional[str] = None):
        """记录转换结果"""
        self.total_conversions += 1
        if level == "advanced":
            self.advanced_success += 1
        elif level == "simple":
            self.simple_fallback += 1
        elif level == "basic":
            self.basic_fallback += 1
        
        if error_msg:
            self.error_details.append({
                "level": level,
                "error": error_msg,
                "count": self.total_conversions
            })
    
    def get_success_rate(self) -> Dict:
        """获取成功率统计"""
        if self.total_conversions == 0:
            return {"advanced_rate": 0, "simple_rate": 0, "basic_rate": 0}
        
        return {
            "advanced_rate": self.advanced_success / self.total_conversions,
            "simple_rate": self.simple_fallback / self.total_conversions,
            "basic_rate": self.basic_fallback / self.total_conversions,
            "total_conversions": self.total_conversions
        }


class DocxConverter:
    """DOCX转换器，支持分层降级"""
    
    def __init__(self):
        """初始化转换器"""
        self.metrics = ConversionMetrics()
    
    async def convert_to_docx(self, text_content: str, task_id: str, output_path: str) -> str:
        """转换为DOCX格式，支持分层降级策略"""
        try:
            # 第1层：尝试完整的富文本转换
            result = await self._advanced_docx_conversion(text_content, task_id, output_path)
            self.metrics.record_result("advanced")
            logger.info(f"Advanced DOCX conversion succeeded for {task_id}")
            return result
            
        except Exception as e:
            logger.warning(f"Advanced DOCX conversion failed for {task_id}: {str(e)}")
            
            try:
                # 第2层：简化转换（保留基础格式）
                result = await self._simple_docx_conversion(text_content, task_id, output_path)
                self.metrics.record_result("simple", str(e))
                logger.info(f"Simple DOCX conversion succeeded for {task_id}")
                return result
                
            except Exception as e2:
                logger.warning(f"Simple DOCX conversion failed for {task_id}: {str(e2)}")
                
                # 第3层：最基础的纯文本转换（保底策略）
                result = await self._fallback_docx_conversion(text_content, task_id, output_path)
                self.metrics.record_result("basic", f"Advanced: {str(e)}, Simple: {str(e2)}")
                logger.info(f"Fallback DOCX conversion used for {task_id}")
                return result
    
    async def _advanced_docx_conversion(self, text_content: str, task_id: str, output_path: str) -> str:
        """高级转换：处理图片、表格、格式"""
        try:            
            doc = Document()
            
            # 添加标题
            title = doc.add_heading(f'PDF Analysis Result - {task_id}', 0)
            title.alignment = WD_ALIGN_PARAGRAPH.CENTER
            
            # 按页面分割内容
            pages = self._split_by_pages(text_content)
            
            for page_index, page_content in enumerate(pages):
                # 添加页面标题
                if page_index > 0:
                    doc.add_page_break()
                
                page_title = doc.add_heading(f'Page {page_index + 1}', level=1)
                
                # 处理页面内容中的不同元素
                elements = self._parse_page_elements(page_content)
                
                for element in elements:
                    if element['type'] == 'text':
                        # 添加文本段落
                        para = doc.add_paragraph(element['content'])
                        
                    elif element['type'] == 'image':
                        # 尝试处理base64图片
                        try:
                            self._add_image_to_doc(doc, element['content'])
                        except Exception as img_e:
                            # 图片处理失败，添加占位文本
                            doc.add_paragraph(f"[Image conversion failed: {element.get('title', 'Unknown image')}]")
                            logger.debug(f"Image processing failed: {str(img_e)}")
                            
                    elif element['type'] == 'table':
                        # 尝试处理HTML表格
                        try:
                            self._add_table_to_doc(doc, element['content'])
                        except Exception as tbl_e:
                            # 表格处理失败，添加原始HTML
                            doc.add_paragraph(f"[Table content - original HTML]")
                            doc.add_paragraph(element['content'])
                            logger.debug(f"Table processing failed: {str(tbl_e)}")
            
            # 保存文档
            doc.save(output_path)
            logger.info(f"Advanced DOCX conversion completed: {output_path}")
            return output_path
            
        except ImportError:
            raise Exception("python-docx library not available")
        except Exception as e:
            raise Exception(f"Advanced conversion failed: {str(e)}")
    
    async def _simple_docx_conversion(self, text_content: str, task_id: str, output_path: str) -> str:
        """简化转换：只处理文本，跳过复杂元素"""
        try:
            doc = Document()
            
            # 添加标题
            doc.add_heading(f'PDF Analysis Result - {task_id}', 0)
            
            # 清理文本内容：移除base64图片和复杂HTML
            cleaned_content = self._clean_text_content(text_content)
            
            # 按页面和段落分割
            pages = self._split_by_pages(cleaned_content)
            
            for page_index, page_content in enumerate(pages):
                if page_index > 0:
                    doc.add_page_break()
                
                # 添加页面标题
                doc.add_heading(f'Page {page_index + 1}', level=1)
                
                # 分段落添加文本
                paragraphs = page_content.split('\n\n')
                for para_text in paragraphs:
                    if para_text.strip():
                        doc.add_paragraph(para_text.strip())
            
            # 保存文档
            doc.save(output_path)
            logger.info(f"Simple DOCX conversion completed: {output_path}")
            return output_path
            
        except ImportError:
            raise Exception("python-docx library not available")
        except Exception as e:
            raise Exception(f"Simple conversion failed: {str(e)}")
    
    async def _fallback_docx_conversion(self, text_content: str, task_id: str, output_path: str) -> str:
        """保底转换：纯文本写入docx，确保100%成功"""
        try:
            doc = Document()
            
            # 添加标题
            doc.add_heading(f'PDF Analysis Result - {task_id}', 0)
            
            # 添加说明
            doc.add_paragraph("Note: This document was generated using fallback conversion due to processing limitations.")
            doc.add_paragraph("")
            
            # 直接添加原始文本内容
            doc.add_paragraph(text_content)
            
            # 保存文档
            doc.save(output_path)
            logger.info(f"Fallback DOCX conversion completed: {output_path}")
            return output_path
            
        except ImportError:
            # 如果连docx库都没有，创建一个简单的文本文件
            with open(output_path.replace('.docx', '.txt'), 'w', encoding='utf-8') as f:
                f.write(f"PDF Analysis Result - {task_id}\n")
                f.write("=" * 50 + "\n\n")
                f.write(text_content)
            
            logger.warning(f"Created TXT file instead of DOCX: {output_path}")
            return output_path.replace('.docx', '.txt')
        
        except Exception as e:
            logger.error(f"Fallback conversion failed: {str(e)}")
            raise Exception("All conversion methods failed")
    
    def _split_by_pages(self, text_content: str) -> list:
        """按页面分割内容"""
        # 使用页面分隔符分割
        page_pattern = r'=== 第 (\d+) 页 ==='
        pages = re.split(page_pattern, text_content)
        
        # 重新组织页面内容
        result_pages = []
        for i in range(1, len(pages), 2):
            if i + 1 < len(pages):
                page_num = pages[i]
                page_content = pages[i + 1].strip()
                if page_content:
                    result_pages.append(page_content)
        
        return result_pages if result_pages else [text_content]
    
    def _parse_page_elements(self, page_content: str) -> list:
        """解析页面内容中的不同元素"""
        elements = []
        
        # 先移除所有base64图片数据和HTML表格数据，避免重复
        cleaned_content = re.sub(r'data:image/[^;]+;base64,[^\s]+', '', page_content)
        cleaned_content = re.sub(r'<table.*?</table>', '', cleaned_content, flags=re.DOTALL)
        
        # 使用正则表达式分割不同类型的内容
        parts = re.split(r'(\[图片 \d+-\d+\]|\[表格 \d+-\d+\])', cleaned_content)
        
        current_text = ""
        for part in parts:
            part = part.strip()
            if not part:
                continue
                
            if part.startswith('[图片'):
                # 如果有累积的文本，先添加
                if current_text.strip():
                    elements.append({
                        'type': 'text',
                        'content': current_text.strip()
                    })
                    current_text = ""
                
                # 从原始内容中查找图片的base64内容
                remaining = page_content[page_content.find(part):]
                image_match = re.search(r'\[图片 \d+-\d+\]\s*(data:image/[^;]+;base64,[^\s]+)', remaining)
                if image_match:
                    elements.append({
                        'type': 'image',
                        'title': part,
                        'content': image_match.group(1)
                    })
                    
            elif part.startswith('[表格'):
                # 如果有累积的文本，先添加
                if current_text.strip():
                    elements.append({
                        'type': 'text',
                        'content': current_text.strip()
                    })
                    current_text = ""
                
                # 从原始内容中查找表格的HTML内容
                remaining = page_content[page_content.find(part):]
                table_match = re.search(r'\[表格 \d+-\d+\]\s*(<table.*?</table>)', remaining, re.DOTALL)
                if table_match:
                    elements.append({
                        'type': 'table',
                        'title': part,
                        'content': table_match.group(1)
                    })
                    
            else:
                current_text += part + " "
        
        # 添加最后的文本内容
        if current_text.strip():
            elements.append({
                'type': 'text',
                'content': current_text.strip()
            })
        
        return elements
    
    def _clean_text_content(self, text_content: str) -> str:
        """清理文本内容，移除复杂元素"""
        # 移除base64图片
        content = re.sub(r'data:image/[^;]+;base64,[^\s]+', '[Image removed]', text_content)
        
        # 移除HTML表格，但保留表格标识
        content = re.sub(r'<table.*?</table>', '[Table content removed]', content, flags=re.DOTALL)
        
        # 清理多余的换行
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        return content
    
    def _add_image_to_doc(self, doc, image_base64: str):
        """添加base64图片到文档"""
        try:
            # 解析base64图片
            header, data = image_base64.split(',', 1)
            img_data = base64.b64decode(data)
            
            # 添加到文档
            img_stream = BytesIO(img_data)
            doc.add_picture(img_stream, width=Inches(4))
            
        except Exception as e:
            raise Exception(f"Image processing failed: {str(e)}")
    
    def _add_table_to_doc(self, doc, table_html: str):
        """添加HTML表格到文档"""
        try:
            # 解析HTML表格
            soup = BeautifulSoup(table_html, 'html.parser')
            table = soup.find('table')
            
            if not table:
                raise Exception("No table found in HTML")
            
            rows = table.find_all('tr')
            if not rows:
                raise Exception("No rows found in table")
            
            # 创建docx表格
            doc_table = doc.add_table(rows=len(rows), cols=len(rows[0].find_all(['th', 'td'])))
            
            for i, row in enumerate(rows):
                cells = row.find_all(['th', 'td'])
                for j, cell in enumerate(cells):
                    if j < len(doc_table.rows[i].cells):
                        doc_table.rows[i].cells[j].text = cell.get_text(strip=True)
            
        except ImportError:
            raise Exception("beautifulsoup4 library not available")
        except Exception as e:
            raise Exception(f"Table processing failed: {str(e)}")
    
    def get_metrics(self) -> Dict:
        """获取转换统计指标"""
        return self.metrics.get_success_rate()