'''
Description: 提供文档布局分析和内容排序功能
Author: zyq
Date: 2025-08-27 15:30:59
LastEditors: zyq
LastEditTime: 2025-08-27 16:10:11
'''

from typing import List, Dict, Any
from loguru import logger
from .bbox_utils import BBoxUtils


class LayoutAnalyzer:
    """布局分析器"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化布局分析器"""
        self.config = config
        self.bbox_utils = BBoxUtils()
    
    def get_reading_order_blocks(self, text_blocks: List[Dict], image_blocks: List[Dict], table_blocks: List[Dict]) -> List[Dict]:
        """获取符合阅读顺序的所有块"""
        try:
            # 1. 过滤表格区域内的文本
            filtered_text_blocks = self._filter_text_in_table_regions(text_blocks, table_blocks)
            
            # 2. 合并所有块
            all_blocks = filtered_text_blocks + image_blocks + table_blocks
            
            # 3. 高级位置排序
            return self._advanced_position_sort(all_blocks)
            
        except Exception as e:
            logger.error(f"Failed to get reading order blocks: {str(e)}")
            # 降级到简单排序
            all_blocks = text_blocks + image_blocks + table_blocks
            return sorted(all_blocks, key=lambda x: (x.get("y", 0), x.get("x", 0)))
    
    def _filter_text_in_table_regions(self, text_blocks: List[Dict], table_blocks: List[Dict]) -> List[Dict]:
        """过滤表格区域内的文本块，避免重复内容"""
        filtered_text = []
        
        for text_block in text_blocks:
            is_in_table = False
            
            # 检查文本块是否与任何表格重叠
            for table_block in table_blocks:
                if self.bbox_utils.bbox_overlap(text_block["bbox"], table_block["bbox"], threshold=0.6):
                    is_in_table = True
                    logger.debug(f"Text block filtered due to table overlap: {text_block['content'][:50]}...")
                    break
            
            if not is_in_table:
                filtered_text.append(text_block)
        
        return filtered_text
    
    def _advanced_position_sort(self, blocks: List[Dict]) -> List[Dict]:
        """改进的位置排序算法，支持多列布局"""
        if not blocks:
            return blocks
        
        text_blocks = [b for b in blocks if b["type"] == "text"]
        
        # 检测是否为多列布局
        if self._is_multi_column_layout(text_blocks):
            return self._sort_multi_column_layout(blocks)
        else:
            # 单列布局：简单的Y坐标排序
            return sorted(blocks, key=lambda x: (x.get("y", 0), x.get("x", 0)))
    
    def _is_multi_column_layout(self, text_blocks: List[Dict], column_threshold: int = 2) -> bool:
        """检测页面是否为多列布局"""
        if len(text_blocks) < column_threshold:
            return False
        
        # 获取所有文本块的X坐标
        x_positions = [block["x"] for block in text_blocks]
        
        # 使用聚类方法检测列边界
        x_positions.sort()
        
        # 检测X坐标的聚类（简化方法：相近的X坐标为同一列）
        clusters = []
        current_cluster = [x_positions[0]]
        
        for x in x_positions[1:]:
            if x - current_cluster[-1] < 50:  # 50像素内认为是同一列
                current_cluster.append(x)
            else:
                clusters.append(current_cluster)
                current_cluster = [x]
        
        if current_cluster:
            clusters.append(current_cluster)
        
        return len(clusters) >= column_threshold
    
    def _sort_multi_column_layout(self, blocks: List[Dict]) -> List[Dict]:
        """多列布局排序"""
        if not blocks:
            return blocks
        
        # 1. 按Y坐标分成行
        blocks_by_y = {}
        for block in blocks:
            y_key = int(block.get("y", 0) // 20)  # 20像素内认为是同一行
            if y_key not in blocks_by_y:
                blocks_by_y[y_key] = []
            blocks_by_y[y_key].append(block)
        
        # 2. 对每一行按X坐标排序（从左到右）
        sorted_blocks = []
        for y_key in sorted(blocks_by_y.keys()):
            row_blocks = sorted(blocks_by_y[y_key], key=lambda x: x.get("x", 0))
            sorted_blocks.extend(row_blocks)
        
        return sorted_blocks