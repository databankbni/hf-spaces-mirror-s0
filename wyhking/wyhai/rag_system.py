#!/usr/bin/env python3
"""
RAG 系统模块
加载前三个月数据作为知识库，用于定价检索和问答增强
"""

import os
import sys
from typing import List, Tuple, Any
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
from data_processor import DataCleaner, df_to_listings, RealCarListing
from demo_llm_real import RealCarRAGRetriever


class RAGSystem:
    """
    RAG 系统主类
    负责加载和管理知识库（前三个月数据）
    """
    
    def __init__(self, data_path: str = None):
        """
        初始化 RAG 系统
        
        Args:
            data_path: Excel 数据文件路径，默认使用 data/最近六月定价最终价格单.xlsx
        """
        self.knowledge_base: List[RealCarListing] = []
        self.test_set: List[RealCarListing] = []
        self.retriever: RealCarRAGRetriever = None
        self.data_stats = {}
        
        if data_path is None:
            project_root = os.path.dirname(os.path.abspath(__file__))
            data_path = os.path.join(project_root, "data", "最近六月定价最终价格单.xlsx")
        
        self.data_path = data_path
        self._load_and_split_data()
    
    def _load_and_split_data(self):
        """
        加载数据并按时间划分：
        - 前三个月：知识库（RAG 检索用）
        - 后三个月：测试集
        """
        print("=" * 80)
        print("  RAG 系统初始化 - 加载知识库")
        print("=" * 80)
        
        if not os.path.exists(self.data_path):
            print(f"  [警告] 数据文件不存在: {self.data_path}")
            print("  [提示] RAG 系统将使用空知识库，主要依赖 LLM 推理")
            self.retriever = RealCarRAGRetriever([])
            return
        
        # 1. 加载原始数据
        print("\n  [步骤1] 加载原始数据...")
        df_raw = pd.read_excel(self.data_path)
        
        # 2. 检查时间字段
        if '车源创建时间' not in df_raw.columns:
            print("  [警告] 数据中没有'车源创建时间'字段，将使用全部数据作为知识库")
            cleaner = DataCleaner(verbose=False)
            df_clean = cleaner.clean(df_raw)
            self.knowledge_base = df_to_listings(df_clean)
            self.retriever = RealCarRAGRetriever(self.knowledge_base)
            print(f"  [完成] 加载 {len(self.knowledge_base)} 条知识库记录")
            return
        
        df_raw['车源创建时间'] = pd.to_datetime(df_raw['车源创建时间'])
        
        # 3. 按时间分割（前三个月 vs 后三个月）
        print("\n  [步骤2] 按时间划分数据集...")
        min_time = df_raw['车源创建时间'].min()
        max_time = df_raw['车源创建时间'].max()
        total_days = (max_time - min_time).days
        mid_time = min_time + timedelta(days=total_days / 2)
        
        df_kb_raw = df_raw[df_raw['车源创建时间'] <= mid_time].copy()
        df_test_raw = df_raw[df_raw['车源创建时间'] > mid_time].copy()
        
        print(f"    数据时间范围: {min_time.date()} 到 {max_time.date()}")
        print(f"    分割时间点: {mid_time.date()}")
        print(f"    知识库（前三个月）: {len(df_kb_raw)} 条")
        print(f"    测试集（后三个月）: {len(df_test_raw)} 条")
        
        # 4. 清洗数据
        print("\n  [步骤3] 清洗数据...")
        cleaner = DataCleaner(verbose=False)
        
        df_kb_clean = cleaner.clean(df_kb_raw)
        df_test_clean = cleaner.clean(df_test_raw)
        
        print(f"    知识库清洗后: {len(df_kb_clean)} 条")
        print(f"    测试集清洗后: {len(df_test_clean)} 条")
        
        # 5. 转换为 RealCarListing
        print("\n  [步骤4] 转换数据格式...")
        self.knowledge_base = df_to_listings(df_kb_clean)
        self.test_set = df_to_listings(df_test_clean)
        
        print(f"    知识库转换成功: {len(self.knowledge_base)} 条")
        print(f"    测试集转换成功: {len(self.test_set)} 条")
        
        # 6. 初始化检索器
        print("\n  [步骤5] 初始化检索器...")
        self.retriever = RealCarRAGRetriever(self.knowledge_base)
        
        # 7. 保存统计信息
        self.data_stats = {
            "kb_count": len(self.knowledge_base),
            "test_count": len(self.test_set),
            "time_range": {
                "start": str(min_time.date()),
                "end": str(max_time.date()),
                "split": str(mid_time.date())
            }
        }
        
        print("\n" + "=" * 80)
        print("  RAG 系统初始化完成！")
        print("=" * 80)
        print(f"    知识库规模: {len(self.knowledge_base)} 条")
        print(f"    测试集规模: {len(self.test_set)} 条")
        print("=" * 80 + "\n")
    
    def retrieve_similar_cars(self, car: RealCarListing, top_k: int = 5) -> List[Tuple[RealCarListing, float]]:
        """
        从知识库中检索相似车源
        
        Args:
            car: 待定价车辆
            top_k: 返回的相似车源数量
            
        Returns:
            相似车源列表 [(car, similarity_score), ...]
        """
        if not self.retriever:
            return []
        
        return self.retriever.retrieve(car, top_k=top_k)
    
    def get_knowledge_context(self, car: RealCarListing, top_k: int = 3) -> str:
        """
        获取知识库上下文信息（用于增强 LLM 推理）
        
        Args:
            car: 待定价车辆
            top_k: 使用的相似车源数量
            
        Returns:
            知识库上下文的字符串描述
        """
        similar_cars = self.retrieve_similar_cars(car, top_k=top_k)
        
        if not similar_cars:
            return "无历史参考数据"
        
        context = "【历史参考车源】\n"
        for i, (ref_car, sim) in enumerate(similar_cars, 1):
            context += f"  {i}. {ref_car.model_year}款{ref_car.brand}{ref_car.series}{ref_car.model}\n"
            context += f"     车况: 里程{ref_car.mileage}万公里, 过户{ref_car.transfer_count}次, 检测{ref_car.inspection_grade}级({ref_car.inspection_score}分)\n"
            context += f"     价格: C2B={ref_car.c2b_price:.2f}万, B2C={ref_car.b2c_price:.2f}万\n"
            if ref_car.created_at:
                context += f"     创建时间: {ref_car.created_at[:10] if isinstance(ref_car.created_at, str) else str(ref_car.created_at)[:10]}\n"
        
        return context
    
    def get_kb_stats(self) -> dict:
        """获取知识库统计信息"""
        return self.data_stats


# 全局单例
_rag_system: RAGSystem = None


def get_rag_system(data_path: str = None) -> RAGSystem:
    """
    获取 RAG 系统单例
    
    Args:
        data_path: 数据文件路径（仅第一次初始化时使用）
        
    Returns:
        RAGSystem 实例
    """
    global _rag_system
    
    if _rag_system is None:
        _rag_system = RAGSystem(data_path)
    
    return _rag_system


if __name__ == "__main__":
    # 测试 RAG 系统
    rag = get_rag_system()
    
    # 创建一个测试车辆
    test_car = RealCarListing(
        brand="丰田",
        series="凯美瑞",
        model="凯美瑞2.5L",
        model_year=2021,
        mileage=5.0,
        color="白色",
        transfer_count=1,
        category="燃油车",
        inspection_score=85.0,
        inspection_grade="B",
        c2b_price=0.0,
        b2c_price=0.0
    )
    
    print("\n" + "=" * 80)
    print("  测试 RAG 检索")
    print("=" * 80)
    print(f"\n  待检索车辆: {test_car}")
    
    # 测试检索
    similar = rag.retrieve_similar_cars(test_car, top_k=3)
    
    print(f"\n  找到 {len(similar)} 条相似车源:")
    for i, (car, sim) in enumerate(similar, 1):
        print(f"\n    {i}. 相似度: {sim:.4f}")
        print(f"       {car}")
    
    # 测试上下文生成
    print("\n" + "=" * 80)
    print("  知识库上下文示例")
    print("=" * 80)
    print("\n" + rag.get_knowledge_context(test_car, top_k=2))
