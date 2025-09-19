"""
PDF处理器

专门处理PDF文档的解析、提取和转换功能。
"""

from typing import Dict, Any
import pymupdf

from core.schemas.file_models import FileInfo
from ..schemas import PDFParserRequest, PDFParserResponse, DocumentTaskTypePrefix
from ..extractors import TextExtractor, ImageExtractor, TableExtractor
from ..utils.layout_utils import LayoutAnalyzer
from ..utils.file_manager import FileManager
from ..utils.docx_converter import DocxConverter
from .base_processor import BaseProcessor


class PDFProcessor(BaseProcessor):
    """PDF文档处理器"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化PDF处理器"""
        super().__init__(config)
        self.text_extractor = TextExtractor(config)
        self.image_extractor = ImageExtractor(config) 
        self.table_extractor = TableExtractor(config)
        self.layout_analyzer = LayoutAnalyzer(config)
        self.file_manager = FileManager()
        self.docx_converter = DocxConverter()
    
    async def process(self, request: PDFParserRequest, temp_file_path: str, file_info: FileInfo, trace_id: str = None) -> PDFParserResponse:
        """处理PDF文档解析"""
        self._log_processing_start("PDFProcessor", request.filename, trace_id)
        
        try:
            # 打开PDF文档
            doc = pymupdf.open(temp_file_path)
            page_count = len(doc)
            
            if request.output_format == "text":
                # 提取文本和图片，生成带base64图片的文本内容
                text_content = await self._extract_content_with_layout(doc)
                
                doc.close()
                
                self._log_processing_end("PDFProcessor", request.filename, trace_id)
                
                return PDFParserResponse(
                    output_format="text",
                    text_content=text_content,
                    page_count=page_count,
                    metadata={
                        "filename": request.filename,
                        "file_type": "pdf",
                        "file_size": file_info.file_size,
                        "input_type": request.input_type
                    }
                )
            elif request.output_format == "docx":
                # docx格式输出
                text_content = await self._extract_content_with_layout(doc)
                doc.close()
                
                # 生成任务ID和文件路径
                task_id = self.file_manager.generate_task_id(DocumentTaskTypePrefix.PDF_PARSE_TASK.value)
                docx_filename = f"{request.filename.rsplit('.', 1)[0]}.docx"
                docx_path = self.file_manager.create_file_path(task_id, docx_filename)
                
                # 转换为DOCX格式
                await self.docx_converter.convert_to_docx(text_content, task_id, docx_path)
                
                # 注册文件到文件管理器
                self.file_manager.register_file(task_id, docx_filename, docx_path, expire_hours=24)
                
                self._log_processing_end("PDFProcessor", request.filename, trace_id)
                
                # 生成下载URL
                download_url = f"/document/pdf-parser-download?task_id={task_id}"
                
                return PDFParserResponse(
                    output_format="docx",
                    download_url=download_url,
                    page_count=page_count,
                    metadata={
                        "filename": request.filename,
                        "file_type": "pdf",
                        "file_size": file_info.file_size,
                        "input_type": request.input_type,
                        "task_id": task_id,
                        "docx_filename": docx_filename
                    }
                )
            else:
                raise ValueError(f"不支持的输出格式: {request.output_format}")
                
        except Exception as e:
            self._log_error("PDFProcessor", trace_id, e)
            self._log_processing_end("PDFProcessor", request.filename, trace_id, success=False)
            raise e
    
    async def _extract_content_with_layout(self, doc) -> str:
        """从PDF中提取内容并按布局排序"""
        full_content = []
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            
            # 添加页面标识
            full_content.append(f"\n=== 第 {page_num + 1} 页 ===\n")
            
            # 提取各类内容
            text_blocks = await self.text_extractor.extract_from_page(page, page_num)
            image_blocks = await self.image_extractor.extract_from_page(doc, page, page_num)
            table_blocks = await self.table_extractor.extract_from_page(page, page_num)
            
            # 使用布局分析器排序内容
            ordered_blocks = self.layout_analyzer.get_reading_order_blocks(
                text_blocks, image_blocks, table_blocks
            )
            
            # 生成页面内容
            page_content = []
            for block in ordered_blocks:
                page_content.append(block["content"])
            
            full_content.append("\n".join(page_content))
        
        return "\n".join(full_content)