'''
Description: 图片提取器
Author: zyq
Date: 2025-09-10 15:34:09
LastEditors: zyq
LastEditTime: 2025-09-18 18:20:19
'''
"""
图片提取器

从PDF页面中提取图片并转换为base64格式。
"""

import asyncio
import base64
from typing import Dict, Any, List
from loguru import logger


class ImageExtractor:
    """图片内容提取器"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化图片提取器"""
        self.config = config
    
    async def extract_from_page(self, doc, page, page_num: int) -> List[Dict]:
        """从PDF页面提取图片块"""
        try:
            # 将同步操作移到线程池中执行
            images = await asyncio.to_thread(page.get_images, full=True)
            
            # 图片处理也是CPU密集型操作，放到线程池中
            image_blocks = await asyncio.to_thread(
                self._process_images, doc, page, images, page_num
            )
            
            return image_blocks
            
        except Exception as e:
            logger.error(f"Failed to extract images from page {page_num}: {str(e)}")
            return []
    
    def _process_images(self, doc, page, images, page_num: int) -> List[Dict]:
        """处理图片（同步方法）"""
        image_blocks = []
        
        # 提取图片数据并生成base64
        image_data = {}
        for img_index, img in enumerate(images):
            try:
                xref = img[0]  # 图片 ID
                base_image = doc.extract_image(xref)
                img_bytes = base_image["image"]
                img_ext = base_image["ext"]  # 图片格式
                
                # 生成base64编码
                img_base64 = base64.b64encode(img_bytes).decode()
                mime_type = f"image/{img_ext}"
                
                # 存储图片数据
                image_data[xref] = f"data:{mime_type};base64,{img_base64}"
                
            except Exception as e:
                logger.warning(f"Failed to extract image {img_index} from page {page_num}: {str(e)}")
                continue
        
        # 构建图片块
        for img_index, img in enumerate(images):
            try:
                xref = img[0]
                if xref not in image_data:
                    continue
                
                # 获取图片位置
                bbox = self._get_image_bbox(img, img_index, page)
                
                image_blocks.append({
                    "type": "image",
                    "bbox": bbox,
                    "y": bbox[1],
                    "x": bbox[0],
                    "content": f"\n[图片 {page_num + 1}-{img_index + 1}]\n{image_data[xref]}\n"
                })
                
            except Exception as e:
                logger.warning(f"Failed to process image {img_index}: {str(e)}")
                continue
        
        return image_blocks
    
    def _get_image_bbox(self, img: tuple, img_index: int, page) -> List[float]:
        """获取图片的边界框位置"""
        bbox = None
        
        # 尝试从页面获取图片矩形
        try:
            image_rects = page.get_image_rects()
            if img_index < len(image_rects):
                rect = image_rects[img_index]
                bbox = [rect.x0, rect.y0, rect.x1, rect.y1]
        except Exception as e:
            logger.debug(f"Failed to get image rect: {str(e)}")
        
        # 默认位置
        if not bbox:
            bbox = [100, 100, 300, 200]
        
        return bbox