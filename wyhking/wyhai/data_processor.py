"""
data_processor.py — 真实数据集导入与清洗
========================================
支持格式：CSV / Excel / MySQL
核心清洗逻辑：
  1. 剔除 C2B 价格为零值或空值的记录
  2. 剔除 B2C 价格为零值或空值的记录
  3. 异常值过滤（价格/里程超出合理范围）
  4. 字段标准化（类型转换、空字符串处理）
  5. 生成数据质量报告

运行方式：
  python data_processor.py --input data.csv --output cleaned.csv
  python data_processor.py --input data.xlsx --output cleaned.csv
"""

import os
import re
import json
import argparse
import warnings
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Tuple, Any, Union

warnings.filterwarnings("ignore")

# ── 依赖检查 ───────────────────────────────────────────
try:
    import pandas as pd
    import numpy as np
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("[错误] 请先安装依赖：pip install pandas openpyxl numpy")


# ═══════════════════════════════════════════════════════
#  真实数据字段定义（对应上传图片中的字段）
# ═══════════════════════════════════════════════════════
@dataclass
class RealCarListing:
    """
    真实数据集的车辆记录
    字段完全对应数据集表头，无假设或补全
    """
    # ── 车辆基础信息 ──────────────────────────────────
    brand: str              # 品牌
    series: str             # 车系
    model: str              # 车型
    model_year: int         # 年款
    mileage: float          # 里程（万公里）
    color: str              # 车身颜色

    # ── 车辆状态 ──────────────────────────────────────
    transfer_count: int     # 过户次数

    # ── 检测结果 ──────────────────────────────────────
    inspection_score: float # 检测报告分数
    inspection_grade: str   # 检测报告评级（A/B/C/D 或 优/良/中/差）

    # ── 车辆基础信息（可选）───────────────────────────
    brand_id: str = ""      # 品牌ID
    series_id: str = ""     # 车系ID
    model_id: str = ""      # 车型ID

    # ── 车辆状态（可选）───────────────────────────────
    category: str = ""      # 品类划分（燃油/新能源/插混等）
    acquisition_type: str = ""   # 收车类型
    acquisition_type_id: str = ""

    # ── 成本与价格信息 ────────────────────────────────
    purchase_price: float = 0.0   # 采购价格（历史/参考）
    sale_price: float = 0.0       # 销售价格（历史/参考）
    refurbish_cost: float = 0.0   # 整备预估价格（万元）
    mortgage_deduction: float = 0.0  # 抵押抵扣价格（万元）

    # ── 目标输出字段（训练标签）──────────────────────
    c2b_price: Optional[float] = None   # C2B价格（收购价）
    b2c_price: Optional[float] = None   # B2C价格（销售价）
    pricing_reason: str = ""            # 定价理由

    # ── 内部字段（数据处理后填入）────────────────────
    car_age: int = 0                    # 车龄（处理时计算）
    gross_margin_ref: float = 0.0       # 参考毛利率（处理时计算）
    
    # ── 车源创建时间（用于排序）─────────────────────────
    created_at: Optional[str] = None     # 车源创建时间（字符串格式，如 "2025-01-15 14:30:00"）

    def __post_init__(self):
        from datetime import datetime
        self.car_age = datetime.now().year - self.model_year
        # 参考毛利率：(B2C - C2B - 整备) / C2B
        if self.c2b_price and self.c2b_price > 0 and self.b2c_price and self.b2c_price > 0:
            self.gross_margin_ref = round(
                (self.b2c_price - self.c2b_price - self.refurbish_cost)
                / self.c2b_price, 4
            )

    def to_dict(self) -> Dict:
        return asdict(self)

    def __str__(self):
        return (f"{self.model_year}款{self.brand}{self.series}{self.model} "
                f"{self.mileage}万km {self.inspection_grade}级 "
                f"C2B={self.c2b_price}万 B2C={self.b2c_price}万")


# ═══════════════════════════════════════════════════════
#  字段名映射表（兼容不同命名风格）
# ═══════════════════════════════════════════════════════
COLUMN_MAPPING = {
    # 标准字段名  →  可能的原始列名列表（大小写不敏感匹配）
    "brand":               ["品牌", "brand", "品牌名称"],
    "brand_id":            ["品牌ID", "品牌id", "brand_id", "brandid"],
    "series":              ["车系", "series", "车系名称"],
    "series_id":           ["车系ID", "车系id", "series_id", "seriesid"],
    "model":               ["车型", "model", "车型名称"],
    "model_id":            ["车型ID", "车型id", "model_id", "modelid"],
    "model_year":          ["年款", "model_year", "年份", "生产年份"],
    "mileage":             ["里程", "mileage", "里程数", "行驶里程"],
    "color":               ["车身颜色", "颜色", "color", "车色"],
    "transfer_count":      ["过户次数", "transfer_count", "过手次数"],
    "category":            ["品类划分", "品类", "category", "车辆品类"],
    "acquisition_type":    ["收车类型", "acquisition_type", "收购类型"],
    "acquisition_type_id": ["收车类型ID", "acquisition_type_id"],
    "inspection_score":    ["检测报告分数", "检测分数", "inspection_score", "报告分数"],
    "inspection_grade":    ["检测报告评级", "检测评级", "inspection_grade", "报告评级"],
    "purchase_price":      ["采购价格", "purchase_price", "历史采购价", "采购价"],
    "sale_price":          ["销售价格", "sale_price", "历史销售价", "销售价"],
    "refurbish_cost":      ["整备预估价格", "整备费用", "refurbish_cost", "整备价格", "整备预估"],
    "mortgage_deduction":  ["抵押抵扣价格", "抵押价格", "mortgage_deduction", "抵押抵扣"],
    "c2b_price":           ["C2B价格", "c2b价格", "c2b_price", "C2B", "收购价"],
    "b2c_price":           ["B2C价格", "b2c价格", "b2c_price", "B2C", "销售定价"],
    "pricing_reason":      ["定价理由", "pricing_reason", "定价原因", "定价说明"],
    "created_at":          ["创建时间", "created_at", "车源创建时间", "入库时间", "记录时间"],
}

# 数值型字段（用于类型强制转换）
NUMERIC_FIELDS = [
    "model_year", "mileage", "transfer_count", "inspection_score",
    "purchase_price", "sale_price", "refurbish_cost", "mortgage_deduction",
    "c2b_price", "b2c_price",
]

# 字符串型字段
STRING_FIELDS = [
    "brand", "brand_id", "series", "series_id", "model", "model_id",
    "color", "category", "acquisition_type", "acquisition_type_id",
    "inspection_grade", "pricing_reason",
]

# 检测评级标准化映射
GRADE_MAPPING = {
    "优": "A", "良": "B", "中": "C", "差": "D",
    "a": "A", "b": "B", "c": "C", "d": "D",
    "A级": "A", "B级": "B", "C级": "C", "D级": "D",
    "1": "A", "2": "B", "3": "C", "4": "D",
    "优秀": "A", "良好": "B", "一般": "C", "较差": "D",
}


# ═══════════════════════════════════════════════════════
#  数据加载器
# ═══════════════════════════════════════════════════════
class DataLoader:
    """支持 CSV / Excel / MySQL 三种数据源"""

    @staticmethod
    def from_csv(path: str, encoding: str = "utf-8", **kwargs) -> "pd.DataFrame":
        """从 CSV 文件加载"""
        if not PANDAS_AVAILABLE:
            raise ImportError("需要安装 pandas")
        try:
            df = pd.read_csv(path, encoding=encoding, **kwargs)
        except UnicodeDecodeError:
            df = pd.read_csv(path, encoding="gbk", **kwargs)
        print(f"[加载] CSV 文件：{path}，原始行数：{len(df)}")
        return df

    @staticmethod
    def from_excel(path: str, sheet_name: Union[int, str] = 0, **kwargs) -> "pd.DataFrame":
        """从 Excel 文件加载"""
        if not PANDAS_AVAILABLE:
            raise ImportError("需要安装 pandas openpyxl")
        df = pd.read_excel(path, sheet_name=sheet_name, **kwargs)
        print(f"[加载] Excel 文件：{path}，Sheet：{sheet_name}，原始行数：{len(df)}")
        return df

    @staticmethod
    def from_mysql(host: str, user: str, password: str, database: str,
                   table: str = "car_listings", limit: int = 100000) -> "pd.DataFrame":
        """
        从 MySQL 加载
        需要安装：pip install pymysql sqlalchemy
        """
        try:
            # 类型忽略：sqlalchemy 是可选依赖
            from sqlalchemy import create_engine  # type: ignore
        except ImportError:
            raise ImportError("需要安装 sqlalchemy pymysql：pip install sqlalchemy pymysql")

        engine = create_engine(
            f"mysql+pymysql://{user}:{password}@{host}/{database}?charset=utf8mb4"
        )
        query = f"SELECT * FROM `{table}` LIMIT {limit}"
        df = pd.read_sql(query, engine)
        print(f"[加载] MySQL {database}.{table}，原始行数：{len(df)}")
        return df


# ═══════════════════════════════════════════════════════
#  数据清洗核心
# ═══════════════════════════════════════════════════════
class DataCleaner:
    """
    清洗流水线，按顺序执行每个步骤。
    每个步骤记录剔除数量，最终输出数据质量报告。
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.report: Dict[str, Any] = {
            "original_count": 0,
            "steps": [],
            "final_count": 0,
            "drop_reasons": {},
        }

    def _log_step(self, step_name: str, before: int, after: int, detail: str = ""):
        dropped = before - after
        self.report["steps"].append({
            "step": step_name,
            "before": before,
            "after": after,
            "dropped": dropped,
            "detail": detail,
        })
        if self.verbose and dropped > 0:
            print(f"  [清洗] {step_name}：剔除 {dropped} 条 → 剩余 {after} 条  {detail}")

    # ── Step 1: 列名标准化 ─────────────────────────────
    def normalize_columns(self, df: "pd.DataFrame") -> "pd.DataFrame":
        """将原始列名映射到标准字段名（大小写不敏感）"""
        col_lower = {c.lower().strip(): c for c in df.columns}
        rename_map = {}

        for std_name, candidates in COLUMN_MAPPING.items():
            for candidate in candidates:
                if candidate.lower() in col_lower:
                    original = col_lower[candidate.lower()]
                    if original != std_name:
                        rename_map[original] = std_name
                    break

        if rename_map:
            df = df.rename(columns=rename_map)
            if self.verbose:
                print(f"  [列名] 标准化映射 {len(rename_map)} 个字段：{rename_map}")

        # 检查必要字段是否存在，如果缺少 c2b_price/b2c_price，尝试使用 purchase_price/sale_price
        if "c2b_price" not in df.columns and "purchase_price" in df.columns:
            df["c2b_price"] = df["purchase_price"]
            if self.verbose:
                print("  [列名] 使用 purchase_price 作为 c2b_price")
        if "b2c_price" not in df.columns and "sale_price" in df.columns:
            df["b2c_price"] = df["sale_price"]
            if self.verbose:
                print("  [列名] 使用 sale_price 作为 b2c_price")
        
        # 检查必要字段是否存在
        required = ["c2b_price", "b2c_price"]
        missing = [f for f in required if f not in df.columns]
        if missing:
            raise ValueError(
                f"缺少必要字段：{missing}\n"
                f"当前字段：{list(df.columns)}\n"
                f"请检查 COLUMN_MAPPING 是否包含你的列名"
            )
        return df

    # ── Step 2: ★ 核心清洗：剔除 C2B / B2C 零值和空值 ─
    def drop_invalid_prices(self, df: "pd.DataFrame") -> "pd.DataFrame":
        """
        剔除 C2B 或 B2C 价格中的：
          - None / NaN / 空字符串
          - 零值（0 或 0.0）
          - 负值
          - 非数字字符串（如 "待定"、"-"、"N/A"）
        """
        before = len(df)

        # 强制转为数值，无法转换的变为 NaN
        for col in ["c2b_price", "b2c_price"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # 记录每种原因的剔除数量
        mask_c2b_null = df["c2b_price"].isna()
        mask_c2b_zero = df["c2b_price"].fillna(0) <= 0
        mask_b2c_null = df["b2c_price"].isna()
        mask_b2c_zero = df["b2c_price"].fillna(0) <= 0

        drop_c2b_null = mask_c2b_null.sum()
        drop_c2b_zero = (~mask_c2b_null & mask_c2b_zero).sum()
        drop_b2c_null = (~mask_c2b_null & ~mask_c2b_zero & mask_b2c_null).sum()
        drop_b2c_zero = (~mask_c2b_null & ~mask_c2b_zero & ~mask_b2c_null & mask_b2c_zero).sum()

        # 保留 C2B > 0 且 B2C > 0 的记录
        valid_mask = (df["c2b_price"] > 0) & (df["b2c_price"] > 0)
        df = df[valid_mask].copy()

        detail = (
            f"（C2B空值:{drop_c2b_null} 零值:{drop_c2b_zero} | "
            f"B2C空值:{drop_b2c_null} 零值:{drop_b2c_zero}）"
        )
        self._log_step("剔除C2B/B2C零值和空值", before, len(df), detail)

        # 写入报告
        self.report["drop_reasons"].update({
            "c2b_null": int(drop_c2b_null),
            "c2b_zero": int(drop_c2b_zero),
            "b2c_null": int(drop_b2c_null),
            "b2c_zero": int(drop_b2c_zero),
        })
        return df

    # ── Step 2.5: ★ 价格单位自动检测与转换 ────────────
    def convert_price_units(self, df: "pd.DataFrame") -> "pd.DataFrame":
        """自动检测价格单位：如果大多数价格 > 100，可能是'元'，自动转换为'万元'"""
        before = len(df)
        
        for col in ["c2b_price", "b2c_price", "purchase_price", "sale_price"]:
            if col in df.columns:
                median_price = df[col].median()
                if median_price > 100:
                    print(f"  [提示] {col} 中位数为 {median_price:.0f}，疑似单位为'元'，自动转换为万元")
                    df[col] = df[col] / 10000
        
        self._log_step("价格单位转换", before, len(df))
        return df

    # ── Step 3: 价格合理性过滤 ─────────────────────────
    def filter_price_range(
        self,
        df: "pd.DataFrame",
        c2b_min: float = 0.5,
        c2b_max: float = 300.0,
        b2c_min: float = 0.5,
        b2c_max: float = 300.0,
        min_spread: float = 0.0,    # B2C 必须 >= C2B（不允许倒挂）
    ) -> "pd.DataFrame":
        """
        过滤价格超出合理范围的记录，以及 B2C < C2B 的倒挂数据
        """
        before = len(df)
        mask = (
            df["c2b_price"].between(c2b_min, c2b_max)
            & df["b2c_price"].between(b2c_min, b2c_max)
            & (df["b2c_price"] >= df["c2b_price"] + min_spread)
        )
        inverted = ((df["b2c_price"] < df["c2b_price"]).sum())
        df = df[mask].copy()
        self._log_step(
            "价格范围过滤",
            before, len(df),
            f"C2B范围[{c2b_min},{c2b_max}]万 B2C范围[{b2c_min},{b2c_max}]万 价格倒挂:{inverted}条"
        )
        self.report["drop_reasons"]["price_inverted"] = int(inverted)
        return df

    # ── Step 4: 数值字段类型转换 ──────────────────────
    def convert_numeric(self, df: "pd.DataFrame") -> "pd.DataFrame":
        """强制数值字段为 float/int，无效值填入合理默认值"""
        before = len(df)
        for col in NUMERIC_FIELDS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # 整备和抵押可以为 0（没有整备费用是合理的）
        for col in ["refurbish_cost", "mortgage_deduction"]:
            if col in df.columns:
                df[col] = df[col].fillna(0.0)

        # 过户次数默认为 1
        if "transfer_count" in df.columns:
            df["transfer_count"] = df["transfer_count"].fillna(1).astype(int)

        # 里程、年款、检测分数不能为空
        critical_numeric = ["mileage", "model_year", "inspection_score"]
        for col in critical_numeric:
            if col in df.columns:
                null_count = df[col].isna().sum()
                if null_count > 0 and self.verbose:
                    print(f"  [警告] {col} 有 {null_count} 条空值，将被剔除")

        df_before = len(df)
        df = df.dropna(subset=[c for c in critical_numeric if c in df.columns])
        self._log_step("关键数值字段空值剔除", df_before, len(df))
        return df

    # ── Step 5: 里程合理性过滤 ────────────────────────
    def filter_mileage(
        self,
        df: "pd.DataFrame",
        min_km: float = 0.1,
        max_km: float = 80.0
    ) -> "pd.DataFrame":
        """过滤里程异常值（单位：万公里）"""
        before = len(df)
        if "mileage" in df.columns:
            # 自动检测单位：如果大多数值 > 100，可能是公里而非万公里
            median_mileage = df["mileage"].median()
            if median_mileage > 100:
                print(f"  [提示] 里程中位数为 {median_mileage:.0f}，疑似单位为'公里'，自动转换为万公里")
                df["mileage"] = df["mileage"] / 10000

            mask = df["mileage"].between(min_km, max_km)
            df = df[mask].copy()
        self._log_step("里程范围过滤", before, len(df), f"范围[{min_km},{max_km}]万km")
        return df

    # ── Step 6: 年款合理性过滤 ────────────────────────
    def filter_model_year(
        self,
        df: "pd.DataFrame",
        min_year: int = 2010,
        max_year: int = 2026,
    ) -> "pd.DataFrame":
        before = len(df)
        if "model_year" in df.columns:
            df["model_year"] = df["model_year"].astype(int)
            df = df[df["model_year"].between(min_year, max_year)].copy()
        self._log_step("年款范围过滤", before, len(df), f"范围[{min_year},{max_year}]")
        return df

    # ── Step 7: 字符串字段清洗 ────────────────────────
    def clean_strings(self, df: "pd.DataFrame") -> "pd.DataFrame":
        """去除首尾空格、统一空字符串为 '未知'"""
        for col in STRING_FIELDS:
            if col in df.columns:
                df[col] = (
                    df[col].fillna("未知")
                    .astype(str)
                    .str.strip()
                    .replace("", "未知")
                    .replace("nan", "未知")
                )
        return df

    # ── Step 8: 检测评级标准化 ────────────────────────
    def normalize_inspection_grade(self, df: "pd.DataFrame") -> "pd.DataFrame":
        """将多种评级表示统一为 A/B/C/D"""
        if "inspection_grade" in df.columns:
            df["inspection_grade"] = (
                df["inspection_grade"]
                .astype(str)
                .str.strip()
                .map(lambda x: GRADE_MAPPING.get(x, GRADE_MAPPING.get(x.upper(), x)))
            )
            # 仍然不在 A/B/C/D 范围内的，根据分数推断
            if "inspection_score" in df.columns:
                unknown_mask = ~df["inspection_grade"].isin(["A", "B", "C", "D"])
                df.loc[unknown_mask & (df["inspection_score"] >= 90), "inspection_grade"] = "A"
                df.loc[unknown_mask & df["inspection_score"].between(75, 90), "inspection_grade"] = "B"
                df.loc[unknown_mask & df["inspection_score"].between(60, 75), "inspection_grade"] = "C"
                df.loc[unknown_mask & (df["inspection_score"] < 60), "inspection_grade"] = "D"

        return df

    # ── Step 9: 计算衍生字段 ──────────────────────────
    def add_derived_fields(self, df: "pd.DataFrame") -> "pd.DataFrame":
        """计算车龄、参考毛利率等分析字段"""
        from datetime import datetime
        current_year = datetime.now().year

        if "model_year" in df.columns:
            df["car_age"] = current_year - df["model_year"]

        if all(c in df.columns for c in ["c2b_price", "b2c_price", "refurbish_cost"]):
            df["gross_margin_ref"] = (
                (df["b2c_price"] - df["c2b_price"] - df["refurbish_cost"].fillna(0))
                / df["c2b_price"]
            ).round(4)

            # 标记毛利率异常（<0 或 >80%）的记录
            df["margin_flag"] = df["gross_margin_ref"].apply(
                lambda x: "正常" if 0 <= x <= 0.8 else ("毛利倒挂" if x < 0 else "毛利过高")
            )
            abnormal_margin = (df["margin_flag"] != "正常").sum()
            if self.verbose and abnormal_margin > 0:
                print(f"  [提示] {abnormal_margin} 条记录毛利率异常，已标记（不剔除，供业务审查）")

        return df

    # ── Step 10: 去重 ─────────────────────────────────
    def deduplicate(self, df: "pd.DataFrame",
                    subset: Optional[List[str]] = None) -> "pd.DataFrame":
        """去除完全重复记录"""
        before = len(df)
        key_cols = subset or [c for c in ["brand_id", "series_id", "model_id",
                                           "model_year", "mileage", "c2b_price"]
                               if c in df.columns]
        df = df.drop_duplicates(subset=key_cols, keep="first")
        self._log_step("去重", before, len(df), f"去重键：{key_cols}")
        return df

    # ── 主入口：完整清洗流水线 ────────────────────────
    def clean(
        self,
        df: "pd.DataFrame",
        c2b_range: Tuple[float, float] = (0.5, 300.0),
        b2c_range: Tuple[float, float] = (0.5, 300.0),
        mileage_range: Tuple[float, float] = (0.1, 80.0),
        year_range: Tuple[int, int] = (2010, 2026),
    ) -> "pd.DataFrame":
        """
        执行完整清洗流水线，返回干净的 DataFrame
        """
        print("\n" + "="*55)
        print("  数据清洗流水线启动")
        print("="*55)

        self.report["original_count"] = len(df)

        df = self.normalize_columns(df)
        df = self.drop_invalid_prices(df)          # ★ 核心：剔除 C2B/B2C 零值空值
        df = self.convert_price_units(df)          # ★ 新：自动检测并转换价格单位（元→万元）
        df = self.filter_price_range(              # 价格合理范围
            df, *c2b_range, *b2c_range
        )
        df = self.convert_numeric(df)              # 数值类型转换
        df = self.filter_mileage(df, *mileage_range)
        df = self.filter_model_year(df, *year_range)
        df = self.clean_strings(df)
        df = self.normalize_inspection_grade(df)
        df = self.add_derived_fields(df)
        df = self.deduplicate(df)

        self.report["final_count"] = len(df)
        total_dropped = self.report["original_count"] - self.report["final_count"]
        drop_rate = total_dropped / max(self.report["original_count"], 1) * 100

        print(f"\n  清洗完成：{self.report['original_count']} → {self.report['final_count']} 条")
        print(f"  剔除率：{drop_rate:.1f}%（剔除 {total_dropped} 条）")
        print("="*55 + "\n")
        return df

    def print_report(self):
        """打印详细的数据质量报告"""
        print("\n" + "─"*55)
        print("  数据质量报告")
        print("─"*55)
        print(f"  原始数量：{self.report['original_count']}")
        print(f"  清洗后：  {self.report['final_count']}")
        print(f"\n  各步骤剔除明细：")
        for step in self.report["steps"]:
            if step["dropped"] > 0:
                bar = "▓" * min(int(step["dropped"] / max(self.report["original_count"], 1) * 50), 20)
                print(f"    {step['step']:<22} -{step['dropped']:>5}条  {bar}")
        print(f"\n  C2B/B2C 无效价格明细：")
        reasons = self.report.get("drop_reasons", {})
        for k, v in reasons.items():
            if v > 0:
                label = {
                    "c2b_null": "C2B 空值/非数字",
                    "c2b_zero": "C2B 零值/负值",
                    "b2c_null": "B2C 空值/非数字",
                    "b2c_zero": "B2C 零值/负值",
                    "price_inverted": "B2C < C2B 价格倒挂",
                }.get(k, k)
                print(f"    {label:<22} {v:>5} 条")
        print("─"*55)


# ═══════════════════════════════════════════════════════
#  DataFrame → RealCarListing 转换
# ═══════════════════════════════════════════════════════
def df_to_listings(df: "pd.DataFrame") -> List[RealCarListing]:
    """
    将清洗后的 DataFrame 转换为 RealCarListing 列表
    转换失败的行会被跳过并记录日志
    """
    listings = []
    failed = 0

    for idx, row in df.iterrows():
        def get(col, default="未知"):
            val = row.get(col, default)
            return default if (pd.isna(val) if hasattr(pd, 'isna') else val != val) else val

        def get_float(col, default=0.0):
            try:
                val = row.get(col, default)
                return float(val) if val == val else default
            except (TypeError, ValueError):
                return default

        def get_int(col, default=0):
            try:
                return int(row.get(col, default))
            except (TypeError, ValueError):
                return default

        try:
            listing = RealCarListing(
                brand=get("brand"),
                brand_id=str(get("brand_id")),
                series=get("series"),
                series_id=str(get("series_id")),
                model=get("model"),
                model_id=str(get("model_id")),
                model_year=get_int("model_year", 2020),
                mileage=get_float("mileage"),
                color=get("color"),
                transfer_count=get_int("transfer_count", 1),
                category=get("category"),
                acquisition_type=get("acquisition_type"),
                acquisition_type_id=str(get("acquisition_type_id")),
                inspection_score=get_float("inspection_score", 80.0),
                inspection_grade=get("inspection_grade", "B"),
                purchase_price=get_float("purchase_price"),
                sale_price=get_float("sale_price"),
                refurbish_cost=get_float("refurbish_cost"),
                mortgage_deduction=get_float("mortgage_deduction"),
                c2b_price=get_float("c2b_price") or None,
                b2c_price=get_float("b2c_price") or None,
                pricing_reason=str(get("pricing_reason", "")),
                created_at=get("created_at", None),
            )
            listings.append(listing)
        except Exception as e:
            failed += 1
            if failed <= 5:
                print(f"  [跳过] 第{idx}行转换失败：{e}")

    if failed > 0:
        print(f"  [警告] 共 {failed} 行转换失败被跳过")

    print(f"  [转换] 成功生成 {len(listings)} 条 RealCarListing")
    return listings


# ═══════════════════════════════════════════════════════
#  数据分析工具（清洗后调用，了解数据分布）
# ═══════════════════════════════════════════════════════
def analyze_dataset(df: "pd.DataFrame") -> Dict[str, Any]:
    """对清洗后的数据集做基础统计分析"""
    print("\n  📊 数据集统计概览")
    print("─"*55)

    analysis = {}

    # 规模
    print(f"  总记录数：{len(df)}")
    analysis["total"] = len(df)

    # 品牌分布
    if "brand" in df.columns:
        brand_dist = df["brand"].value_counts().head(10)
        print(f"\n  品牌 Top10：")
        for brand, cnt in brand_dist.items():
            bar = "█" * min(int(cnt / len(df) * 40), 20)
            print(f"    {brand:<10} {cnt:>5}条  {bar}")
        analysis["brand_top10"] = brand_dist.to_dict()

    # 品类分布
    if "category" in df.columns:
        cat_dist = df["category"].value_counts()
        print(f"\n  品类分布：")
        for cat, cnt in cat_dist.items():
            print(f"    {str(cat):<12} {cnt:>5}条  ({cnt/len(df)*100:.1f}%)")

    # 价格分布
    for col, label in [("c2b_price", "C2B"), ("b2c_price", "B2C")]:
        if col in df.columns:
            s = df[col]
            print(f"\n  {label}价格分布（万元）：")
            print(f"    最小值：{s.min():.2f}  最大值：{s.max():.2f}")
            print(f"    均值：  {s.mean():.2f}  中位数：{s.median():.2f}")
            print(f"    标准差：{s.std():.2f}")
            analysis[f"{col}_stats"] = {
                "min": s.min(), "max": s.max(),
                "mean": round(s.mean(), 2), "median": s.median()
            }

    # 毛利率分布
    if "gross_margin_ref" in df.columns:
        s = df["gross_margin_ref"]
        print(f"\n  参考毛利率分布：")
        print(f"    均值：{s.mean():.1%}  中位数：{s.median():.1%}")
        print(f"    <0（倒挂）：{(s < 0).sum()}条  >50%（异常高）：{(s > 0.5).sum()}条")
        analysis["gross_margin"] = {"mean": round(s.mean(), 4), "median": round(s.median(), 4)}

    # 检测评级分布
    if "inspection_grade" in df.columns:
        grade_dist = df["inspection_grade"].value_counts()
        print(f"\n  检测评级分布：")
        for grade in ["A", "B", "C", "D"]:
            cnt = grade_dist.get(grade, 0)
            bar = "█" * min(int(cnt / len(df) * 30), 15)
            print(f"    {grade}级：{cnt:>5}条  {bar}")

    print("─"*55)
    return analysis


# ═══════════════════════════════════════════════════════
#  主入口（命令行工具）
# ═══════════════════════════════════════════════════════
def process_file(
    input_path: str,
    output_path: str = "cleaned_data.csv",
    sheet_name: Union[str, int] = 0,
    c2b_range: Tuple[float, float] = (0.5, 300.0),
    b2c_range: Tuple[float, float] = (0.5, 300.0),
) -> Tuple["pd.DataFrame", List[RealCarListing]]:
    """
    完整的文件处理流程（供外部调用）
    返回：(清洗后的DataFrame, RealCarListing列表)
    """
    # 加载
    ext = os.path.splitext(input_path)[1].lower()
    if ext == ".csv":
        df = DataLoader.from_csv(input_path)
    elif ext in (".xlsx", ".xls"):
        df = DataLoader.from_excel(input_path, sheet_name=sheet_name)
    else:
        raise ValueError(f"不支持的文件格式：{ext}，请使用 .csv 或 .xlsx")

    # 清洗
    cleaner = DataCleaner(verbose=True)
    df_clean = cleaner.clean(df, c2b_range=c2b_range, b2c_range=b2c_range)
    cleaner.print_report()

    # 分析
    analyze_dataset(df_clean)

    # 保存
    df_clean.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n  [输出] 清洗后数据已保存至：{output_path}")

    # 转换为 RealCarListing
    listings = df_to_listings(df_clean)

    return df_clean, listings


# ── 模拟数据生成（无真实文件时用于测试）──────────────
def generate_mock_data(n: int = 200) -> "pd.DataFrame":
    """
    生成符合真实字段结构的模拟数据，用于测试清洗流程。
    包含有意设置的脏数据：零值、空值、倒挂等。
    """
    import random
    if not PANDAS_AVAILABLE:
        raise ImportError("需要 pandas")

    random.seed(42)
    brands = [("丰田", "B001", "凯美瑞", "S001"),
              ("大众", "B002", "帕萨特", "S002"),
              ("本田", "B003", "雅阁", "S003"),
              ("宝马", "B004", "3系", "S004"),
              ("比亚迪", "B005", "汉", "S005"),
              ("特斯拉", "B006", "Model3", "S006")]

    rows = []
    for i in range(n):
        brand, bid, series, sid = random.choice(brands)
        c2b = round(random.uniform(8, 45), 2)
        b2c = round(c2b * random.uniform(1.05, 1.25), 2)

        # 故意插入脏数据（约 25%）
        if i % 8 == 0:
            c2b = 0           # C2B 零值
        if i % 9 == 0:
            b2c = None        # B2C 空值
        if i % 12 == 0:
            b2c = c2b * 0.95  # B2C < C2B 倒挂
        if i % 15 == 0:
            c2b = None        # C2B 空值

        rows.append({
            "品牌": brand, "品牌ID": bid,
            "车系": series, "车系ID": sid,
            "车型": f"{series}2.5L", "车型ID": f"M{i:04d}",
            "年款": random.randint(2018, 2024),
            "里程": round(random.uniform(1, 18), 1),
            "车身颜色": random.choice(["白色", "黑色", "银色", "红色", "蓝色"]),
            "过户次数": random.randint(1, 3),
            "品类划分": random.choice(["燃油车", "新能源", "插混"]),
            "收车类型": random.choice(["C2B收车", "置换收车", "拍卖收车"]),
            "收车类型ID": f"T{random.randint(1,3)}",
            "检测报告分数": round(random.uniform(55, 98), 1),
            "检测报告评级": random.choice(["A", "B", "C", "优", "良"]),
            "采购价格": round(random.uniform(8, 45), 2),
            "销售价格": round(random.uniform(10, 55), 2),
            "整备预估价格": round(random.uniform(0, 0.8), 2),
            "抵押抵扣价格": round(random.uniform(0, 2), 2),
            "C2B价格": c2b,
            "B2C价格": b2c,
            "定价理由": random.choice(["参考同款历史成交", "品质较好溢价", "", None]),
        })

    return pd.DataFrame(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="二手车数据清洗工具")
    parser.add_argument("--input",   type=str, help="输入文件路径（.csv 或 .xlsx）")
    parser.add_argument("--output",  type=str, default="cleaned_data.csv", help="输出文件路径")
    parser.add_argument("--sheet",   type=str, default="0", help="Excel Sheet 名称或序号")
    parser.add_argument("--mock",    action="store_true", help="使用模拟数据运行测试")
    args = parser.parse_args()

    if args.mock or not args.input:
        print("[测试模式] 使用模拟数据（200条，含约25%脏数据）")
        df_raw = generate_mock_data(200)
        cleaner = DataCleaner(verbose=True)
        df_clean = cleaner.clean(df_raw)
        cleaner.print_report()
        analyze_dataset(df_clean)
        listings = df_to_listings(df_clean)
        print(f"\n  示例记录：{listings[0]}")
    else:
        sheet = int(args.sheet) if args.sheet.isdigit() else args.sheet
        process_file(args.input, args.output, sheet_name=sheet)
