"""
文本提取器

从PDF页面中提取文本内容。
"""

from typing import Dict, Any, List
from loguru import logger


class TextExtractor:
    """文本内容提取器"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化文本提取器"""
        self.config = config
    
    async def extract_from_page(self, page, page_num: int) -> List[Dict]:
        """从PDF页面提取文本块"""
        try:
            text_dict = page.get_text("dict")
            text_blocks = []
            
            for block in text_dict["blocks"]:
                if "lines" in block:  # 文本块
                    bbox = block["bbox"]  # [x0, y0, x1, y1]
                    block_text = ""
                    
                    for line in block["lines"]:
                        line_text = ""
                        for span in line["spans"]:
                            line_text += span["text"]
                        if line_text.strip():
                            block_text += line_text + "\n"
                    
                    if block_text.strip():
                        text_blocks.append({
                            "type": "text",
                            "bbox": bbox,
                            "y": bbox[1],
                            "x": bbox[0],
                            "content": block_text.strip()
                        })
            
            return text_blocks
            
        except Exception as e:
            logger.error(f"Failed to extract text from page {page_num}: {str(e)}")
            return []