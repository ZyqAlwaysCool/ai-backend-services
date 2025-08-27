"""
边界框工具函数

提供边界框相关的计算和分析功能。
"""

from typing import List


class BBoxUtils:
    """边界框工具类"""
    
    @staticmethod
    def bbox_overlap(bbox1: List[float], bbox2: List[float], threshold: float = 0.5) -> bool:
        """检测两个边界框是否重叠"""
        x1, y1, x2, y2 = bbox1
        x3, y3, x4, y4 = bbox2
        
        # 计算重叠区域
        overlap_x = max(0, min(x2, x4) - max(x1, x3))
        overlap_y = max(0, min(y2, y4) - max(y1, y3))
        overlap_area = overlap_x * overlap_y
        
        # 计算较小框的面积
        area1 = (x2 - x1) * (y2 - y1)
        area2 = (x4 - x3) * (y4 - y3)
        min_area = min(area1, area2)
        
        if min_area == 0:
            return False
            
        # 重叠比例超过阈值
        return overlap_area / min_area > threshold
    
    @staticmethod
    def bbox_distance(bbox1: List[float], bbox2: List[float]) -> float:
        """计算两个边界框的距离"""
        # 计算边界框中心点
        center1_x = (bbox1[0] + bbox1[2]) / 2
        center1_y = (bbox1[1] + bbox1[3]) / 2
        center2_x = (bbox2[0] + bbox2[2]) / 2
        center2_y = (bbox2[1] + bbox2[3]) / 2
        
        # 欧几里得距离
        return ((center1_x - center2_x) ** 2 + (center1_y - center2_y) ** 2) ** 0.5
    
    @staticmethod
    def bbox_area(bbox: List[float]) -> float:
        """计算边界框面积"""
        return (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    
    @staticmethod
    def bbox_union(bbox1: List[float], bbox2: List[float]) -> List[float]:
        """计算两个边界框的并集"""
        return [
            min(bbox1[0], bbox2[0]),  # x0
            min(bbox1[1], bbox2[1]),  # y0
            max(bbox1[2], bbox2[2]),  # x1
            max(bbox1[3], bbox2[3]),  # y1
        ]
    
    @staticmethod
    def bbox_intersection(bbox1: List[float], bbox2: List[float]) -> List[float]:
        """计算两个边界框的交集"""
        x0 = max(bbox1[0], bbox2[0])
        y0 = max(bbox1[1], bbox2[1])
        x1 = min(bbox1[2], bbox2[2])
        y1 = min(bbox1[3], bbox2[3])
        
        if x0 >= x1 or y0 >= y1:
            return [0, 0, 0, 0]  # 无交集
        
        return [x0, y0, x1, y1]