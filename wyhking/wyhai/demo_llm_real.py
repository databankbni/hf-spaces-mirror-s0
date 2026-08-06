"""
demo_llm_real.py — 二手车双价格智能定价系统（真实数据版）
=========================================================
基于真实数据集字段，同时输出 C2B（收购价）和 B2C（销售价）
以及「定价理由」文字说明

架构：
  data_processor.py → 清洗真实数据 → RealCarListing
  demo_llm_real.py  → RAG检索 + LLM四步CoT推理 → C2B + B2C + 定价理由

运行方式：
  # 使用模拟数据（无需真实文件）
  python demo_llm_real.py

  # 使用真实数据文件
  python demo_llm_real.py --data cleaned.csv

  # 指定定价单车（传入JSON）
  python demo_llm_real.py --single '{"brand":"丰田","series":"凯美瑞",...}'
"""

import os
import re
import math
import json
import argparse
import statistics
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Any

# 导入数据处理模块
from data_processor import (
    RealCarListing,
    df_to_listings, generate_mock_data, PANDAS_AVAILABLE
)

# ─────────────────────────────────────────────────────
#  REPLACE-1: LLM 客户端
#  修改 _call_llm() 即可切换到任意模型，其余代码不变
# ─────────────────────────────────────────────────────
try:
    import anthropic
    _client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    LLM_AVAILABLE = bool(os.environ.get("ANTHROPIC_API_KEY"))
except ImportError:
    LLM_AVAILABLE = False


def _call_llm(prompt: str, temperature: float = 0.0, max_tokens: int = 1500) -> str:
    """
    统一 LLM 调用入口。

    REPLACE-1: 切换模型只需改这一个函数
      OpenAI:  from openai import OpenAI; client.chat.completions.create(...)
      Qwen:    import dashscope; dashscope.Generation.call(model="qwen2.5-72b-instruct",...)
      本地:    requests.post("http://localhost:11434/api/generate",...)
    """
    if not LLM_AVAILABLE:
        return ""
    msg = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text


# ─────────────────────────────────────────────────────
#  Step 0：验车师文字描述 → 结构化字段（属性提取）
#
#  这是验车师输入场景的入口。
#  LLM 从自然语言中提取出 RealCarListing 所需的所有字段，
#  提取结果直接进入后续 RAG 检索和定价推理。
# ─────────────────────────────────────────────────────

# few-shot 示例，覆盖常见的验车师描述风格。
# 上线前建议从真实验车记录中挑选 8~10 个补进来，尤其是：
#   - 事故描述模糊的（"换过机盖"算几级？）
#   - 营运车隐晦表述的（"跑过滴滴"）
#   - 新能源车（无排量无变速箱描述）
_EXTRACTION_EXAMPLES = """
示例1（标准燃油车）：
输入："2021年款丰田凯美瑞2.5L豪华版，白色，AT，行驶6.8万公里，外观良好，内饰干净，机械状况优。有一次轻微追尾已修复。过户1次，非营运。北京收车，检测评分85分B级，整备费用0.15万，无抵押。"
输出：{"brand":"丰田","brand_id":"","series":"凯美瑞","series_id":"","model":"凯美瑞2.5L","model_id":"","model_year":2021,"mileage":6.8,"color":"白色","transfer_count":1,"category":"燃油车","acquisition_type":"C2B收车","acquisition_type_id":"","inspection_score":85,"inspection_grade":"B","purchase_price":0,"sale_price":0,"refurbish_cost":0.15,"mortgage_deduction":0}

示例2（高风险车）：
输入："19年本田雅阁2.0CVT标准版，红色，里程13万公里，车况较差，有中等碰撞记录右前叶子板换过。过户3次，曾用于网约车运营。检测65分C级，整备预估0.6万，抵押抵扣1.5万。"
输出：{"brand":"本田","brand_id":"","series":"雅阁","series_id":"","model":"雅阁2.0L","model_id":"","model_year":2019,"mileage":13.0,"color":"红色","transfer_count":3,"category":"燃油车","acquisition_type":"C2B收车","acquisition_type_id":"","inspection_score":65,"inspection_grade":"C","purchase_price":0,"sale_price":0,"refurbish_cost":0.6,"mortgage_deduction":1.5}

示例3（新能源车）：
输入："2022款比亚迪汉EV荣耀版，黑色，纯电，5.5万公里，车况极好无事故，首任车主非营运，检测93分A级，整备0.05万，无抵押。"
输出：{"brand":"比亚迪","brand_id":"","series":"汉","series_id":"","model":"汉EV","model_id":"","model_year":2022,"mileage":5.5,"color":"黑色","transfer_count":1,"category":"新能源","acquisition_type":"C2B收车","acquisition_type_id":"","inspection_score":93,"inspection_grade":"A","purchase_price":0,"sale_price":0,"refurbish_cost":0.05,"mortgage_deduction":0}

示例4（描述模糊的事故和营运）：
输入："2020帕萨特280TSI豪华版，银色，DSG，9万公里，有过一次小剐蹭修过漆面，两次过户，之前跑过一段时间专车，检测72分B级，整备约0.3万，无抵押贷款。"
输出：{"brand":"大众","brand_id":"","series":"帕萨特","series_id":"","model":"帕萨特280TSI","model_id":"","model_year":2020,"mileage":9.0,"color":"银色","transfer_count":2,"category":"燃油车","acquisition_type":"C2B收车","acquisition_type_id":"","inspection_score":72,"inspection_grade":"B","purchase_price":0,"sale_price":0,"refurbish_cost":0.3,"mortgage_deduction":0}
"""

# 规则兜底（LLM 不可用时）
def _fallback_extract(description: str) -> dict:
    """从描述中用正则提取关键字段，仅作兜底"""
    import re
    result = {
        "brand": "未知", "brand_id": "", "series": "未知", "series_id": "",
        "model": "未知", "model_id": "", "model_year": 2020,
        "mileage": 0.0, "color": "未知", "transfer_count": 1,
        "category": "燃油车", "acquisition_type": "C2B收车", "acquisition_type_id": "",
        "inspection_score": 80.0, "inspection_grade": "B",
        "purchase_price": 0.0, "sale_price": 0.0,
        "refurbish_cost": 0.0, "mortgage_deduction": 0.0,
    }
    for brand in ["丰田","大众","本田","宝马","比亚迪","特斯拉","奔驰","奥迪","吉利","长城"]:
        if brand in description:
            result["brand"] = brand
            break
    m = re.search(r'(\d{4})[年款]', description)
    if m: result["model_year"] = int(m.group(1))
    m = re.search(r'(\d+\.?\d*)\s*万[公里km]', description)
    if m: result["mileage"] = float(m.group(1))
    # 里程单位为"公里"而非"万公里"
    m = re.search(r'(\d+\.?\d*)\s*公里', description)
    if m and result["mileage"] == 0.0:
        result["mileage"] = round(float(m.group(1)) / 10000, 1)
    m = re.search(r'(\d+\.?\d*)\s*分', description)
    if m: result["inspection_score"] = float(m.group(1))
    for grade in ["A级","B级","C级","D级"]:
        if grade in description:
            result["inspection_grade"] = grade[0]
            break
    m = re.search(r'整备[预估费用约]*(\d+\.?\d*)万', description)
    if m: result["refurbish_cost"] = float(m.group(1))
    m = re.search(r'抵押[抵扣]*(\d+\.?\d*)万', description)
    if m: result["mortgage_deduction"] = float(m.group(1))
    m = re.search(r'过户(\d+)次', description)
    if m: result["transfer_count"] = int(m.group(1))
    if any(w in description for w in ["纯电","EV","新能源","电动"]):
        result["category"] = "新能源"
    elif any(w in description for w in ["插混","PHEV","混动"]):
        result["category"] = "插混"
    for color in ["白色","黑色","银色","灰色","红色","蓝色","橙色","绿色","黄色"]:
        if color in description:
            result["color"] = color
            break
    return result


def extract_from_description(description: str) -> RealCarListing:
    """
    【对外接口】验车师文字描述 → RealCarListing

    这是验车师输入场景的唯一入口。
    调用方式：
        car = extract_from_description("2021年款丰田凯美瑞，里程6.8万...")
        result = price_car(car, retriever)

    字段说明（LLM 负责从描述中识别）：
        brand/series/model      品牌车系车型
        model_year              年款（4位年份）
        mileage                 里程（万公里，注意单位换算）
        color                   车身颜色
        transfer_count          过户次数
        category                燃油车 / 新能源 / 插混
        inspection_score        检测报告分数（0~100）
        inspection_grade        检测评级（A/B/C/D）
        refurbish_cost          整备预估费用（万元，无则填0）
        mortgage_deduction      抵押抵扣价格（万元，无则填0）

    不需要从描述中提取（由系统/业务填入）：
        purchase_price / sale_price   历史参考价（RAG检索后自动带入）
        c2b_price / b2c_price         目标输出，不是输入
    """
    prompt = f"""你是二手车验车记录解析专家。从以下验车师描述中提取结构化字段，**只输出 JSON，不要有任何其他文字**。

字段说明：
- brand: 品牌（如"丰田"）
- brand_id: 品牌ID（描述中没有则填空字符串""）
- series: 车系（如"凯美瑞"）
- series_id: 车系ID（没有则填""）
- model: 车型（如"凯美瑞2.5L"）
- model_id: 车型ID（没有则填""）
- model_year: 年款（整数，如2021）
- mileage: 里程（万公里，浮点数；如描述为"公里"需换算，如68000公里=6.8万）
- color: 车身颜色（如"白色"）
- transfer_count: 过户次数（整数，首任车主填1）
- category: 品类（"燃油车" 或 "新能源" 或 "插混"）
- acquisition_type: 收车类型（默认"C2B收车"）
- acquisition_type_id: 收车类型ID（没有则填""）
- inspection_score: 检测报告分数（0~100的浮点数，没有明确分数则根据评级估算：A=95,B=82,C=68,D=55）
- inspection_grade: 检测评级（"A"/"B"/"C"/"D"，没有明确评级则根据分数判断：>=90=A,75-90=B,60-75=C,<60=D）
- purchase_price: 历史采购参考价（万元，描述中没有则填0）
- sale_price: 历史销售参考价（万元，描述中没有则填0）
- refurbish_cost: 整备预估费用（万元，没有则填0）
- mortgage_deduction: 抵押抵扣价格（万元，没有则填0）

参考示例：
{_EXTRACTION_EXAMPLES}

待解析的验车描述：
\"\"\"{description}\"\"\"

只输出 JSON 对象，不要有任何说明："""

    raw = _call_llm(prompt, temperature=0.0, max_tokens=600)

    if not raw:
        print("  [属性提取] LLM不可用，使用规则引擎兜底")
        fields = _fallback_extract(description)
    else:
        try:
            clean = re.sub(r'```json|```', '', raw).strip()
            m = re.search(r'\{.*\}', clean, re.DOTALL)
            fields = json.loads(m.group(0) if m else clean)
            print(f"  [属性提取] 成功提取 {len(fields)} 个字段")
        except Exception:
            print(f"  [属性提取] JSON解析失败，使用规则兜底\n  原始输出: {raw[:80]}")
            fields = _fallback_extract(description)

    # 类型安全转换
    def _s(k, d=""): return str(fields.get(k, d)).strip()
    def _f(k, d=0.0):
        try: return float(fields.get(k, d))
        except: return d
    def _i(k, d=0):
        try: return int(fields.get(k, d))
        except: return d

    car = RealCarListing(
        brand=_s("brand", "未知"),
        brand_id=_s("brand_id"),
        series=_s("series", "未知"),
        series_id=_s("series_id"),
        model=_s("model", "未知"),
        model_id=_s("model_id"),
        model_year=_i("model_year", 2020),
        mileage=_f("mileage"),
        color=_s("color", "未知"),
        transfer_count=_i("transfer_count", 1),
        category=_s("category", "燃油车"),
        acquisition_type=_s("acquisition_type", "C2B收车"),
        acquisition_type_id=_s("acquisition_type_id"),
        inspection_score=_f("inspection_score", 80.0),
        inspection_grade=_s("inspection_grade", "B"),
        purchase_price=_f("purchase_price"),
        sale_price=_f("sale_price"),
        refurbish_cost=_f("refurbish_cost"),
        mortgage_deduction=_f("mortgage_deduction"),
    )

    print(f"  [属性提取] {car}")
    return car


def price_from_description(
    description: str,
    retriever: "RealCarRAGRetriever",
    n_paths: int = 3,
) -> "DualPricingResult":
    """
    【最终对外接口】验车师输入文字 → 直接返回 C2B + B2C + 定价理由

    完整链路：
      文字描述
        → extract_from_description()   属性提取
        → RealCarListing               结构化字段
        → RealCarRAGRetriever          检索最相似5条历史成交
        → multi_path_pricing()         LLM 3路径推理
        → DualPricingResult            C2B + B2C + 定价理由
    """
    print(f"\n  [输入] {description[:60]}{'...' if len(description)>60 else ''}")
    car = extract_from_description(description)
    return price_car(car, retriever, n_paths=n_paths, verbose=True)


# ─────────────────────────────────────────────────────
#  RAG 检索器（适配真实数据，全结构化，无文本向量）
# ─────────────────────────────────────────────────────
def _real_numeric_vector(car: RealCarListing) -> List[float]:
    """
    数值特征向量（7维），用于相似车检索。
    新增了检测评级维度，去掉了文本相似度（全结构化数据不需要）
    """
    grade_map = {"A": 0.0, "B": 0.33, "C": 0.66, "D": 1.0}
    category_map = {"燃油车": 0.0, "插混": 0.5, "新能源": 1.0}
    return [
        (car.model_year - 2018) / 7,                          # 年款
        min(car.mileage / 20.0, 1.0),                          # 里程
        car.inspection_score / 100.0,                          # 检测分数
        grade_map.get(car.inspection_grade, 0.5),              # 检测评级
        min(car.transfer_count / 3.0, 1.0),                    # 过户次数
        category_map.get(car.category, 0.0),                   # 品类
        min(car.mortgage_deduction / 5.0, 1.0),               # 抵押情况
    ]


def _vec_cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x ** 2 for x in a))
    nb = math.sqrt(sum(x ** 2 for x in b))
    return dot / (na * nb) if na and nb else 0.0


class RealCarRAGRetriever:
    """
    真实数据版 RAG 检索器。
    检索逻辑：同品牌+同车系优先 → 数值特征相似度排序 → 优先使用最近数据

    REPLACE-2: 替换数据库时只需修改 __init__ 中的数据加载逻辑
    """

    def __init__(self, database: List[RealCarListing], min_months: int = 0, max_months: int = 6):
        """
        初始化 RAG 检索器。
        
        Args:
            database: 车辆数据列表
            min_months: 最小时间范围（月），0 表示不限制
            max_months: 最大时间范围（月），默认 6 个月
        """
        from datetime import datetime, timedelta
        
        # 先过滤有有效价格的记录
        valid_cars = [car for car in database if car.c2b_price and car.b2c_price]
        
        # 按时间范围过滤
        now = datetime.now()
        filtered_cars = []
        
        for car in valid_cars:
            if car.created_at:
                try:
                    # 解析创建时间
                    car_time = datetime.strptime(str(car.created_at)[:19], '%Y-%m-%d %H:%M:%S')
                    months_diff = (now.year - car_time.year) * 12 + (now.month - car_time.month)
                    
                    # 检查是否在时间范围内
                    if min_months == 0 or months_diff >= min_months:
                        if max_months == 0 or months_diff <= max_months:
                            filtered_cars.append(car)
                except:
                    # 如果时间解析失败，也保留这条记录
                    filtered_cars.append(car)
            else:
                # 如果没有创建时间，也保留这条记录
                filtered_cars.append(car)
        
        # 按创建时间降序排序（最近的在前）
        def get_created_time(car):
            if car.created_at:
                try:
                    return datetime.strptime(str(car.created_at)[:19], '%Y-%m-%d %H:%M:%S')
                except:
                    pass
            return datetime.min
        
        self.db = sorted(filtered_cars, key=get_created_time, reverse=True)
        self._vecs = [_real_numeric_vector(c) for c in self.db]
        
        print(f"[RAG] 加载 {len(self.db)} 条有效参考记录（C2B和B2C均有效）")
        if min_months > 0 or max_months < 120:
            print(f"[RAG] 时间范围: {min_months if min_months > 0 else '不限'} ~ {max_months if max_months > 0 else '不限'} 个月")

    def retrieve(
        self,
        query: RealCarListing,
        top_k: int = 5,
        same_series_bonus: float = 0.3,    # 同品牌同车系额外加分
        same_brand_bonus: float = 0.1,     # 同品牌加分
    ) -> List[Tuple[RealCarListing, float]]:
        """
        检索最相似的历史成交车辆。
        排序优先级：
        1. 同车系同年款（车源创建时间由近及远）
        2. 同车系不同年款（车源创建时间由近及远）
        3. 同品牌不同车系（车源创建时间由近及远）
        4. 不同品牌同车系（车源创建时间由近及远）
        5. 其他（按相似度排序）
        """
        q_vec = _real_numeric_vector(query)
        scored = []

        for i, car in enumerate(self.db):
            # 跳过自身（如果是从历史库里取的）
            # 使用多个字段组合判断，避免误判
            is_same_car = False
            
            # 策略1: 如果有 ID 字段，优先使用 ID 判断
            if (car.brand_id and query.brand_id and 
                car.series_id and query.series_id and 
                car.model_id and query.model_id):
                if (car.brand_id == query.brand_id and 
                    car.series_id == query.series_id and 
                    car.model_id == query.model_id and
                    car.model_year == query.model_year and
                    abs(car.mileage - query.mileage) < 0.1):
                    is_same_car = True
            
            # 策略2: 如果没有完整 ID，使用业务字段组合判断
            if not is_same_car:
                if (car.brand == query.brand and 
                    car.series == query.series and 
                    car.model == query.model and
                    car.model_year == query.model_year and
                    abs(car.mileage - query.mileage) < 0.1 and
                    car.color == query.color and
                    car.transfer_count == query.transfer_count):
                    is_same_car = True
            
            if is_same_car:
                continue

            sim = _vec_cosine(q_vec, self._vecs[i])

            # 同系列加分
            if car.brand == query.brand and car.series == query.series:
                sim += same_series_bonus
            elif car.brand == query.brand:
                sim += same_brand_bonus

            scored.append((car, round(sim, 4)))

        # 计算优先级分数并排序
        def get_priority_key(item):
            car, sim = item
            same_brand = car.brand == query.brand
            same_series = car.series == query.series
            same_year = car.model_year == query.model_year
            same_model = car.model == query.model

            # 优先级从高到低：
            # 1. 同品牌同车系同车型（不管年款）→ 优先级 5
            # 2. 同品牌同车系同年款 → 优先级 4
            # 3. 同品牌同车系不同年款 → 优先级 3
            # 4. 同品牌不同车系 → 优先级 2
            # 5. 不同品牌同车系 → 优先级 1
            # 6. 其他 → 优先级 0
            if same_brand and same_series and same_model:
                priority = 5
            elif same_brand and same_series and same_year:
                priority = 4
            elif same_brand and same_series:
                priority = 3
            elif same_brand:
                priority = 2
            elif same_series:
                priority = 1
            else:
                priority = 0

            # 处理车源创建时间，由近及远排序
            # 将创建时间转换为可比较的数值，时间越新数值越大
            created_at_score = 0
            if hasattr(car, 'created_at') and car.created_at:
                try:
                    from datetime import datetime
                    dt = datetime.strptime(str(car.created_at)[:19], '%Y-%m-%d %H:%M:%S')
                    created_at_score = dt.timestamp()
                except:
                    pass

            # 返回元组：(-priority, -created_at_score, -sim)
            # 负号是为了让 sort 按降序排列（优先级高→创建时间新→相似度高）
            return (-priority, -created_at_score, -sim)

        scored.sort(key=get_priority_key)
        return scored[:top_k]


# ─────────────────────────────────────────────────────
#  检测评级折扣系数（从真实数据拟合，此处为初始值）
# ─────────────────────────────────────────────────────
GRADE_DISCOUNT = {"A": 0.00, "B": -0.03, "C": -0.08, "D": -0.18}
MILEAGE_RATE   = 0.032    # 每超出参考均值1万km，C2B折价比例
TRANSFER_DEDUCT = 0.30    # 每次额外过户扣减（万元）
MIN_GROSS_MARGIN = 0.08   # B2C毛利率保护下限（8%）
TARGET_GROSS_MARGIN = 0.15  # 目标毛利率（15%）

# 颜色溢价/折价系数（相对标准色）
COLOR_ADJ = {
    "白色": 0.0, "黑色": 0.0, "银色": 0.0, "灰色": 0.0,
    "红色": -0.02, "蓝色": -0.02, "橙色": -0.04,
    "黄色": -0.05, "绿色": -0.03, "棕色": -0.04,
}

# 品类参数（新能源/插混折旧规律不同）
CATEGORY_PARAMS = {
    "燃油车":  {"mileage_rate": 0.032, "base_depreciation": 0.10},
    "插混":    {"mileage_rate": 0.025, "base_depreciation": 0.12},
    "新能源":  {"mileage_rate": 0.020, "base_depreciation": 0.15},
}


# ─────────────────────────────────────────────────────
#  LLM 四步 CoT 推理 Prompt（双价格版）
# ─────────────────────────────────────────────────────
_COT_SYSTEM = """你是资深二手车定价专家，需要同时给出C2B（收购价）和B2C（销售价）两个价格。

核心定价原则：
1. C2B = 市场参考价 - 车况折扣 - 里程修正 - 过户折价 - 抵押抵扣 - 颜色折价
2. B2C = C2B + 整备费用 + 目标利润（毛利率不低于8%，目标15%）
3. B2C 必须严格大于 C2B
4. 检测评级：A级无折扣，B级-3%，C级-8%，D级-18%
5. 里程每超出参考均值1万公里，折价约参考价的3.2%
6. 每次额外过户扣减0.3万元
7. 只输出合法JSON，不要有任何额外说明"""


def _build_dual_price_prompt(
    car: RealCarListing,
    similar: List[Tuple[RealCarListing, float]],
    hint: str = ""
) -> str:
    """构建双价格 CoT 推理 prompt"""

    # 组织参考车信息
    ref_lines = []
    c2b_prices, b2c_prices = [], []
    for ref, score in similar:
        if ref.c2b_price and ref.b2c_price:
            c2b_prices.append(ref.c2b_price)
            b2c_prices.append(ref.b2c_price)
            ref_lines.append(
                f"  · {ref.model_year}款{ref.brand}{ref.series} "
                f"里程{ref.mileage}万km "
                f"检测{ref.inspection_grade}级({ref.inspection_score:.0f}分) "
                f"过户{ref.transfer_count}次 "
                f"{'新能源' if ref.category == '新能源' else ref.category} "
                f"整备{ref.refurbish_cost}万 "
                f"→ C2B={ref.c2b_price}万 B2C={ref.b2c_price}万 "
                f"(相似度{score:.2f})"
            )

    ref_text = "\n".join(ref_lines) if ref_lines else "  （暂无历史参考数据，请基于采购和销售价格参考估算）"
    c2b_range = f"{min(c2b_prices):.1f}~{max(c2b_prices):.1f}" if c2b_prices else "未知"
    b2c_range = f"{min(b2c_prices):.1f}~{max(b2c_prices):.1f}" if b2c_prices else "未知"
    c2b_median = statistics.median(c2b_prices) if c2b_prices else 0
    b2c_median = statistics.median(b2c_prices) if b2c_prices else 0

    return f"""请对以下二手车进行双价格定价推理。{hint}

【待估车辆信息】
品牌车系：{car.brand} {car.series} {car.model}
年款/里程：{car.model_year}年款，{car.mileage}万公里
车身颜色：{car.color}
过户次数：{car.transfer_count}次
品类：{car.category}
收车类型：{car.acquisition_type}
检测评分：{car.inspection_score}分，评级：{car.inspection_grade}级
整备预估费用：{car.refurbish_cost}万元
抵押抵扣价格：{car.mortgage_deduction}万元
历史采购参考价：{car.purchase_price}万元
历史销售参考价：{car.sale_price}万元

【历史相似成交参考（Top-{len(similar)}）】
{ref_text}
C2B参考区间：{c2b_range}万，中位数：{c2b_median:.2f}万
B2C参考区间：{b2c_range}万，中位数：{b2c_median:.2f}万

【请严格按以下JSON格式输出，不要有任何额外文字】
{{
  "step0_baseline": {{
    "reasoning": "说明如何从参考记录确定基准价，考虑年款/品类差异",
    "c2b_base": C2B基准中位价（数字），
    "b2c_base": B2C基准中位价（数字）
  }},
  "step1_vehicle_adj": {{
    "grade_discount_pct": 检测评级折扣百分比（如-3表示-3%）,
    "grade_adj": 检测评级对C2B的修正金额（负数为折价）,
    "mileage_diff": 本车里程与参考均值的差（万km）,
    "mileage_adj": 里程修正金额（负数为折价）,
    "transfer_adj": 过户次数修正金额（首次过户为0）,
    "color_adj": 颜色修正金额（主流色为0）,
    "mortgage_adj": 抵押抵扣金额（直接取mortgage_deduction的负值）,
    "c2b_mid": 特征修正后C2B中间价
  }},
  "step2_cost_and_market": {{
    "refurbish_cost": 整备费用（直接取refurbish_cost字段），
    "target_margin_pct": 目标毛利率百分比（建议10~20）,
    "profit_amount": 目标利润金额,
    "b2c_cost_floor": B2C成本底线（=c2b_mid + 整备 + 最低8%毛利）,
    "market_premium": 市场溢价修正（参考B2C基准与成本底线的差异）,
    "b2c_mid": 市场因子修正后B2C中间价
  }},
  "step3_final": {{
    "c2b_price": 最终C2B收购价（万元，2位小数）,
    "c2b_low": C2B置信区间下限,
    "c2b_high": C2B置信区间上限,
    "b2c_price": 最终B2C销售价（万元，2位小数，必须>c2b_price）,
    "b2c_low": B2C置信区间下限,
    "b2c_high": B2C置信区间上限,
    "gross_margin_pct": 预计毛利率百分比（(b2c-c2b-整备)/c2b*100）,
    "gross_profit": 预计毛利金额（万元）,
    "confidence": "high" 或 "medium" 或 "low",
    "risk_notes": ["风险点列表，无则空数组"],
    "pricing_reason": "100字以内的定价理由说明，将写入数据库"
  }}
}}"""


# ─────────────────────────────────────────────────────
#  规则引擎兜底（LLM 不可用时）
# ─────────────────────────────────────────────────────
def _rule_based_pricing(
    car: RealCarListing,
    similar: List[Tuple[RealCarListing, float]]
) -> Dict[str, Any]:
    """当 LLM 不可用时，用规则引擎生成兜底定价"""
    c2b_refs = [c.c2b_price for c, _ in similar if c.c2b_price]
    b2c_refs = [c.b2c_price for c, _ in similar if c.b2c_price]

    c2b_base = statistics.median(c2b_refs) if c2b_refs else car.purchase_price
    b2c_base = statistics.median(b2c_refs) if b2c_refs else car.sale_price

    # 里程修正
    ref_mileages = [c.mileage for c, _ in similar]
    ref_avg_mileage = sum(ref_mileages) / len(ref_mileages) if ref_mileages else car.mileage
    mileage_adj = -(car.mileage - ref_avg_mileage) * MILEAGE_RATE * c2b_base

    # 检测评级折扣
    grade_adj = GRADE_DISCOUNT.get(car.inspection_grade, -0.03) * c2b_base

    # 过户折价
    transfer_adj = -(max(car.transfer_count - 1, 0)) * TRANSFER_DEDUCT

    # 颜色折价
    color_adj = COLOR_ADJ.get(car.color, -0.02) * c2b_base

    # 抵押抵扣
    mortgage_adj = -car.mortgage_deduction

    c2b_mid = c2b_base + mileage_adj + grade_adj + transfer_adj + color_adj + mortgage_adj
    c2b_mid = max(c2b_mid, c2b_base * 0.4)  # 安全下限

    # B2C = C2B + 整备 + 毛利
    b2c_floor = c2b_mid * (1 + MIN_GROSS_MARGIN) + car.refurbish_cost
    b2c_target = c2b_mid * (1 + TARGET_GROSS_MARGIN) + car.refurbish_cost
    b2c_mid = max(b2c_floor, min(b2c_target, b2c_base * 1.05))

    gross_margin = (b2c_mid - c2b_mid - car.refurbish_cost) / c2b_mid

    # 计算 MAPE（Mean Absolute Percentage Error）
    c2b_mape = 0.0
    b2c_mape = 0.0
    if c2b_refs:
        c2b_errors = [abs(c2b_mid - ref) / ref for ref in c2b_refs if ref > 0]
        c2b_mape = sum(c2b_errors) / len(c2b_errors) * 100 if c2b_errors else 0.0
    if b2c_refs:
        b2c_errors = [abs(b2c_mid - ref) / ref for ref in b2c_refs if ref > 0]
        b2c_mape = sum(b2c_errors) / len(b2c_errors) * 100 if b2c_errors else 0.0

    return {
        "step0_baseline": {"c2b_base": round(c2b_base, 2), "b2c_base": round(b2c_base, 2),
                           "reasoning": "规则引擎兜底：取参考中位价"},
        "step1_vehicle_adj": {
            "grade_adj": round(grade_adj, 2), "mileage_adj": round(mileage_adj, 2),
            "transfer_adj": round(transfer_adj, 2), "color_adj": round(color_adj, 2),
            "mortgage_adj": round(mortgage_adj, 2),
            "c2b_mid": round(c2b_mid, 2),
            "grade_discount_pct": GRADE_DISCOUNT.get(car.inspection_grade, -0.03) * 100,
            "mileage_diff": round(car.mileage - ref_avg_mileage, 2),
        },
        "step2_cost_and_market": {
            "refurbish_cost": car.refurbish_cost,
            "b2c_cost_floor": round(b2c_floor, 2),
            "b2c_mid": round(b2c_mid, 2),
            "target_margin_pct": TARGET_GROSS_MARGIN * 100,
            "profit_amount": round(b2c_mid - c2b_mid - car.refurbish_cost, 2),
            "market_premium": 0,
        },
        "step3_final": {
            "c2b_price": round(c2b_mid, 2),
            "c2b_low":   round(c2b_mid * 0.96, 2),
            "c2b_high":  round(c2b_mid * 1.04, 2),
            "b2c_price": round(b2c_mid, 2),
            "b2c_low":   round(b2c_mid * 0.97, 2),
            "b2c_high":  round(b2c_mid * 1.03, 2),
            "gross_margin_pct": round(gross_margin * 100, 1),
            "gross_profit":     round(b2c_mid - c2b_mid - car.refurbish_cost, 2),
            "c2b_mape": round(c2b_mape, 2),
            "b2c_mape": round(b2c_mape, 2),
            "confidence": "low",
            "risk_notes": ["规则引擎兜底，建议人工复核"],
            "pricing_reason": f"参考{len(similar)}辆同类成交，C2B中位{c2b_base:.2f}万，修正后{c2b_mid:.2f}万。",
        }
    }


# ─────────────────────────────────────────────────────
#  结果数据类
# ─────────────────────────────────────────────────────
@dataclass
class DualPricingResult:
    """C2B + B2C 双价格定价结果"""
    # C2B
    c2b_price: float
    c2b_low: float
    c2b_high: float

    # B2C
    b2c_price: float
    b2c_low: float
    b2c_high: float

    # 毛利
    gross_margin_pct: float
    gross_profit: float

    # 推理过程
    pricing_reason: str
    confidence: str
    risk_notes: List[str]

    # 精度指标
    c2b_mape: float = 0.0
    b2c_mape: float = 0.0
    
    # 预测价格与相似车型价格的偏差
    c2b_deviation: float = 0.0  # C2B 预测价格与相似车型平均价格的偏差百分比
    b2c_deviation: float = 0.0  # B2C 预测价格与相似车型平均价格的偏差百分比

    # 中间步骤（调试用）
    step0_c2b_base: float = 0.0
    step0_b2c_base: float = 0.0
    step1_c2b_mid: float = 0.0
    step2_b2c_mid: float = 0.0
    raw_steps: Dict = field(default_factory=dict)

    # 评估指标（有真实价格时填入）
    r_c2b: float = 0.0
    r_b2c: float = 0.0
    r_consist: float = 0.0
    r_margin: float = 0.0
    r_total: float = 0.0


# ─────────────────────────────────────────────────────
#  解析 LLM 返回的 JSON
# ─────────────────────────────────────────────────────
def _parse_response(raw: str, fallback: Dict) -> Dict:
    try:
        clean = re.sub(r'```json|```', '', raw).strip()
        m = re.search(r'\{.*\}', clean, re.DOTALL)
        return json.loads(m.group(0) if m else clean)
    except Exception:
        return fallback


def _safe_float(d: dict, key: str, default: float) -> float:
    try:
        return float(d.get(key, default))
    except (TypeError, ValueError):
        return default


def _dict_to_result(data: Dict, car: RealCarListing) -> DualPricingResult:
    """将解析后的 JSON 转换为 DualPricingResult"""
    s0 = data.get("step0_baseline", {})
    s1 = data.get("step1_vehicle_adj", {})
    s2 = data.get("step2_cost_and_market", {})
    s3 = data.get("step3_final", {})

    c2b = _safe_float(s3, "c2b_price", car.purchase_price)
    b2c = _safe_float(s3, "b2c_price", car.sale_price)

    # 安全校验：B2C 必须大于 C2B
    min_b2c = c2b * (1 + MIN_GROSS_MARGIN) + car.refurbish_cost
    if b2c <= c2b:
        b2c = round(min_b2c, 2)

    gross_profit = round(b2c - c2b - car.refurbish_cost, 2)
    gross_margin_pct = round(gross_profit / c2b * 100, 1) if c2b > 0 else 0

    return DualPricingResult(
        c2b_price=round(c2b, 2),
        c2b_low=round(_safe_float(s3, "c2b_low", c2b * 0.96), 2),
        c2b_high=round(_safe_float(s3, "c2b_high", c2b * 1.04), 2),
        b2c_price=round(b2c, 2),
        b2c_low=round(_safe_float(s3, "b2c_low", b2c * 0.97), 2),
        b2c_high=round(_safe_float(s3, "b2c_high", b2c * 1.03), 2),
        gross_margin_pct=gross_margin_pct,
        gross_profit=gross_profit,
        c2b_mape=_safe_float(s3, "c2b_mape", 0),
        b2c_mape=_safe_float(s3, "b2c_mape", 0),
        pricing_reason=str(s3.get("pricing_reason", "")),
        confidence=str(s3.get("confidence", "medium")),
        risk_notes=s3.get("risk_notes", []),
        step0_c2b_base=_safe_float(s0, "c2b_base", 0),
        step0_b2c_base=_safe_float(s0, "b2c_base", 0),
        step1_c2b_mid=_safe_float(s1, "c2b_mid", 0),
        step2_b2c_mid=_safe_float(s2, "b2c_mid", 0),
        raw_steps=data,
    )


# ─────────────────────────────────────────────────────
#  单次 LLM 定价推理
# ─────────────────────────────────────────────────────
def reason_once(
    car: RealCarListing,
    similar: List[Tuple[RealCarListing, float]],
    temperature: float = 0.0,
    hint: str = ""
) -> DualPricingResult:
    prompt = _build_dual_price_prompt(car, similar, hint)
    raw = _call_llm(prompt, temperature=temperature)

    if not raw:
        fallback_data = _rule_based_pricing(car, similar)
        return _dict_to_result(fallback_data, car)

    fallback_data = _rule_based_pricing(car, similar)
    data = _parse_response(raw, fallback_data)
    return _dict_to_result(data, car)


# ─────────────────────────────────────────────────────
#  多路径采样聚合（简化树搜索）
# ─────────────────────────────────────────────────────
SAMPLING_CONFIGS = [
    {"temperature": 0.0, "hint": ""},
    {"temperature": 0.4, "hint": "请稍微偏向市场上行方向考虑，"},
    {"temperature": 0.4, "hint": "请偏向风险保守方向考虑，"},
]


def multi_path_pricing(
    car: RealCarListing,
    similar: List[Tuple[RealCarListing, float]],
    n_paths: int = 3,
) -> Tuple[DualPricingResult, List[DualPricingResult]]:
    """3条路径采样，中位数聚合"""
    paths = []
    configs = SAMPLING_CONFIGS[:n_paths]

    print(f"\n  [多路径] 采样 {len(configs)} 条推理路径...")
    for i, cfg in enumerate(configs):
        print(f"    Path-{i} temperature={cfg['temperature']} ...", end=" ")
        result = reason_once(car, similar, cfg["temperature"], cfg["hint"])
        print(f"C2B={result.c2b_price} B2C={result.b2c_price} 置信={result.confidence}")
        paths.append(result)

    # 聚合：C2B 和 B2C 分别取中位数
    c2b_median = statistics.median(p.c2b_price for p in paths)
    b2c_median = statistics.median(p.b2c_price for p in paths)
    c2b_std = statistics.stdev([p.c2b_price for p in paths]) if len(paths) > 1 else 0
    b2c_std = statistics.stdev([p.b2c_price for p in paths]) if len(paths) > 1 else 0

    # 取最接近中位数的路径作为代表
    best = min(paths, key=lambda p: abs(p.c2b_price - c2b_median))
    best.c2b_price = round(c2b_median, 2)
    best.b2c_price = round(b2c_median, 2)
    best.c2b_low   = round(min(p.c2b_low  for p in paths), 2)
    best.c2b_high  = round(max(p.c2b_high for p in paths), 2)
    best.b2c_low   = round(min(p.b2c_low  for p in paths), 2)
    best.b2c_high  = round(max(p.b2c_high for p in paths), 2)

    # 毛利重新计算
    best.gross_profit = round(b2c_median - c2b_median - car.refurbish_cost, 2)
    best.gross_margin_pct = round(best.gross_profit / c2b_median * 100, 1) if c2b_median > 0 else 0

    # 合并所有风险提示
    all_risks = []
    for p in paths:
        for r in p.risk_notes:
            if r and r not in all_risks:
                all_risks.append(r)
    best.risk_notes = all_risks

    # 分歧大时降低置信度
    if c2b_std > 1.0 or b2c_std > 1.5:
        best.confidence = "low"
        best.risk_notes.insert(0,
            f"⚠ 多路径定价分歧较大（C2B标准差{c2b_std:.2f}万，B2C标准差{b2c_std:.2f}万），建议人工复核"
        )
    elif c2b_std > 0.5 and best.confidence == "high":
        best.confidence = "medium"

    print(f"\n  [聚合] C2B中位={c2b_median:.2f}万(σ={c2b_std:.2f}) "
          f"B2C中位={b2c_median:.2f}万(σ={b2c_std:.2f}) "
          f"毛利率={best.gross_margin_pct:.1f}% 置信={best.confidence}")
    return best, paths


# ─────────────────────────────────────────────────────
#  奖励评估（有真实价格时调用）
# ─────────────────────────────────────────────────────
def compute_rewards(result: DualPricingResult, car: RealCarListing,
                    similar_c2b: List[float], similar_b2c: List[float],
                    weights: Optional[Dict] = None) -> DualPricingResult:
    """计算四维奖励指标"""
    w = weights or {"r_c2b": 0.35, "r_b2c": 0.35, "r_consist": 0.20, "r_margin": 0.10}

    def r_price(pred, actual):
        return math.exp(-abs(pred - actual) / actual * 8) if actual > 0 else 0.5

    def r_consist(pred, refs):
        if not refs:
            return 0.5
        mean = sum(refs) / len(refs)
        return math.exp(-abs(pred - mean) / mean * 5)

    def r_margin(margin_pct):
        if margin_pct >= MIN_GROSS_MARGIN * 100:
            return 1.0
        return math.exp(-(MIN_GROSS_MARGIN * 100 - margin_pct) * 0.5)

    result.r_c2b    = round(r_price(result.c2b_price, car.c2b_price), 4) if car.c2b_price else 0
    result.r_b2c    = round(r_price(result.b2c_price, car.b2c_price), 4) if car.b2c_price else 0
    result.r_consist = round((r_consist(result.c2b_price, similar_c2b)
                              + r_consist(result.b2c_price, similar_b2c)) / 2, 4)
    result.r_margin  = round(r_margin(result.gross_margin_pct), 4)
    result.r_total   = round(
        w["r_c2b"]    * result.r_c2b
        + w["r_b2c"]    * result.r_b2c
        + w["r_consist"] * result.r_consist
        + w["r_margin"]  * result.r_margin, 4
    )
    return result


# ─────────────────────────────────────────────────────
#  核心对外接口
# ─────────────────────────────────────────────────────
def price_car(
    car: RealCarListing,
    retriever: RealCarRAGRetriever,
    n_paths: int = 3,
    verbose: bool = True,
) -> DualPricingResult:
    """
    完整定价流程：RAG检索 → 多路径LLM推理 → 聚合 → 奖励评估

    REPLACE-2: retriever 的数据库来源是唯一需要替换的地方
    """
    similar = retriever.retrieve(car, top_k=5)
    similar_c2b = [c.c2b_price for c, _ in similar if c.c2b_price]
    similar_b2c = [c.b2c_price for c, _ in similar if c.b2c_price]

    if verbose:
        print(f"\n  [RAG] 找到 {len(similar)} 辆相似车")
        for ref, score in similar[:3]:
            print(f"    · {ref.model_year}款{ref.brand}{ref.series} "
                  f"C2B={ref.c2b_price}万 B2C={ref.b2c_price}万 相似度={score:.3f}")

    result, _ = multi_path_pricing(car, similar, n_paths)

    # 有真实价格时计算评估指标
    if car.c2b_price and car.b2c_price:
        result = compute_rewards(result, car, similar_c2b, similar_b2c)

    return result


# ─────────────────────────────────────────────────────
#  置信度路由（接入业务审核队列）
# ─────────────────────────────────────────────────────
def route_by_confidence(result: DualPricingResult, car_id: str = "") -> str:
    """
    根据置信度决定处理方式。
    REPLACE-5: 替换 print 为真实的业务系统调用
    """
    if result.confidence == "high":
        action = "自动通过"
        # auto_approve(car_id, result.c2b_price, result.b2c_price)
    elif result.confidence == "medium":
        action = "推入普通复核队列"
        # push_review_queue(car_id, priority="normal")
    else:
        action = "推入紧急复核队列 + 通知运营"
        # push_review_queue(car_id, priority="urgent")
        # alert_ops(car_id, result.risk_notes)
    print(f"  [路由] 置信度={result.confidence} → {action}")
    return action


# ─────────────────────────────────────────────────────
#  打印结果工具
# ─────────────────────────────────────────────────────
def _print_result(car: RealCarListing, result: DualPricingResult):
    print(f"""
  ┌── 定价报告 {'─'*42}
  │  车辆：{car}
  │
  │  C2B 收购价：{result.c2b_price} 万元  [{result.c2b_low}, {result.c2b_high}]
  │  B2C 销售价：{result.b2c_price} 万元  [{result.b2c_low}, {result.b2c_high}]
  │
  │  预计毛利：{result.gross_profit:.2f} 万元（毛利率 {result.gross_margin_pct:.1f}%）
  │  置信度：{result.confidence}
  │""")
    if result.risk_notes:
        print(f"  │  风险提示：")
        for r in result.risk_notes[:3]:
            print(f"  │    · {r}")
    print(f"  │")
    print(f"  │  推理链：")
    print(f"  │    Step0 基准  C2B={result.step0_c2b_base:.2f}万  B2C={result.step0_b2c_base:.2f}万")
    print(f"  │    Step1 车况  C2B修正→{result.step1_c2b_mid:.2f}万")
    print(f"  │    Step2 成本  B2C修正→{result.step2_b2c_mid:.2f}万")
    print(f"  │    Step3 终价  C2B={result.c2b_price:.2f}万  B2C={result.b2c_price:.2f}万")
    print(f"  │")
    print(f"  │  定价理由：{result.pricing_reason}")
    if car.c2b_price and car.b2c_price:
        err_c2b = abs(result.c2b_price - car.c2b_price) / car.c2b_price
        err_b2c = abs(result.b2c_price - car.b2c_price) / car.b2c_price
        flag_c2b = "✓" if err_c2b < 0.10 else ("~" if err_c2b < 0.15 else "✗")
        flag_b2c = "✓" if err_b2c < 0.10 else ("~" if err_b2c < 0.15 else "✗")
        print(f"  │")
        print(f"  │  对比真实价格：")
        print(f"  │    C2B 实际={car.c2b_price}万  误差={err_c2b:.1%} {flag_c2b}")
        print(f"  │    B2C 实际={car.b2c_price}万  误差={err_b2c:.1%} {flag_b2c}")
        if result.r_total:
            print(f"  │    R_c2b={result.r_c2b:.3f}  R_b2c={result.r_b2c:.3f}  "
                  f"R_consist={result.r_consist:.3f}  R_margin={result.r_margin:.3f}  "
                  f"R_total={result.r_total:.3f}")
    print(f"  └{'─'*49}")


def _sep(title: str = ""):
    print("\n" + "="*60)
    if title:
        print(f"  {title}")
        print("="*60)


# ─────────────────────────────────────────────────────
#  Demo 0: 验车师文字描述输入（核心场景）
# ─────────────────────────────────────────────────────
def demo_from_description(retriever: RealCarRAGRetriever):
    """
    Demo 0: 验车师输入文字 → 直接定价
    这是真实业务场景的完整链路演示。
    """
    _sep("Demo 0: 验车师文字描述 → C2B + B2C 定价（完整链路）")

    test_cases = [
        # 普通工况
        ("普通工况",
         "2021年款丰田凯美瑞2.5L豪华版，白色，行驶6.8万公里，车况良好。"
         "有一次轻微追尾已修复无明显痕迹，过户1次，非营运车辆。"
         "检测报告85分B级，整备费用预估0.15万，无抵押。"),

        # 高风险
        ("高风险车（营运+事故+多次过户）",
         "2019年本田雅阁2.0L标准版，红色，里程13万公里，车况一般。"
         "有中等碰撞记录右前叶子板更换过，过户3次，曾用于网约车运营。"
         "检测评分65分C级，整备费0.6万，存在抵押抵扣1.5万。"),

        # 新能源
        ("新能源车",
         "22年比亚迪汉EV荣耀版，黑色，纯电，行驶5.5万公里，全车无事故。"
         "首任车主非营运，检测93分A级，整备约0.05万，无抵押。"),
    ]

    for label, desc in test_cases:
        print(f"\n  ── 案例：{label} {'─'*30}")
        result = price_from_description(desc, retriever, n_paths=1)
        print(f"\n  ┌── 定价结果")
        print(f"  │  C2B 收购价：{result.c2b_price} 万元  [{result.c2b_low}, {result.c2b_high}]")
        print(f"  │  B2C 销售价：{result.b2c_price} 万元  [{result.b2c_low}, {result.b2c_high}]")
        print(f"  │  预计毛利：{result.gross_profit:.2f}万（{result.gross_margin_pct:.1f}%）")
        print(f"  │  置信度：{result.confidence}")
        if result.risk_notes:
            print(f"  │  风险：{result.risk_notes[0]}")
        print(f"  │  定价理由：{result.pricing_reason}")
        print(f"  └{'─'*45}")
        route_by_confidence(result)


# ─────────────────────────────────────────────────────
#  Demo 演示（结构化字段输入）
# ─────────────────────────────────────────────────────
def demo_single_normal(retriever: RealCarRAGRetriever):
    """Demo 1: 普通工况双价格定价"""
    _sep("Demo 1: 普通工况 — 燃油车B级检测")
    car = RealCarListing(
        brand="丰田", brand_id="B001",
        series="凯美瑞", series_id="S001",
        model="凯美瑞2.5L", model_id="M001",
        model_year=2021, mileage=6.8, color="白色",
        transfer_count=1, category="燃油车",
        acquisition_type="C2B收车", acquisition_type_id="T1",
        inspection_score=85.0, inspection_grade="B",
        purchase_price=17.5, sale_price=19.8,
        refurbish_cost=0.15, mortgage_deduction=0.0,
        c2b_price=17.1, b2c_price=19.5,
    )
    print(f"  待估：{car}")
    result = price_car(car, retriever)
    _print_result(car, result)
    route_by_confidence(result)


def demo_single_high_risk(retriever: RealCarRAGRetriever):
    """Demo 2: 高风险车（低评级 + 高过户 + 高抵押）"""
    _sep("Demo 2: 高风险车 — C级检测+3次过户+抵押")
    car = RealCarListing(
        brand="本田", brand_id="B003",
        series="雅阁", series_id="S003",
        model="雅阁2.0L", model_id="M003",
        model_year=2019, mileage=12.5, color="红色",
        transfer_count=3, category="燃油车",
        acquisition_type="置换收车", acquisition_type_id="T2",
        inspection_score=65.0, inspection_grade="C",
        purchase_price=12.0, sale_price=14.5,
        refurbish_cost=0.60, mortgage_deduction=1.5,
        c2b_price=10.2, b2c_price=12.8,
    )
    print(f"  待估：{car}")
    print(f"  注意：C级检测 + 3次过户 + 1.5万抵押抵扣 + 非主流颜色")
    result = price_car(car, retriever)
    _print_result(car, result)
    route_by_confidence(result)


def demo_new_energy(retriever: RealCarRAGRetriever):
    """Demo 3: 新能源车（折旧规律不同）"""
    _sep("Demo 3: 新能源车 — A级检测首任车主")
    car = RealCarListing(
        brand="比亚迪", brand_id="B005",
        series="汉", series_id="S005",
        model="汉EV", model_id="M005",
        model_year=2022, mileage=5.5, color="黑色",
        transfer_count=1, category="新能源",
        acquisition_type="C2B收车", acquisition_type_id="T1",
        inspection_score=93.0, inspection_grade="A",
        purchase_price=19.5, sale_price=22.0,
        refurbish_cost=0.05, mortgage_deduction=0.0,
        c2b_price=18.5, b2c_price=21.0,
    )
    print(f"  待估：{car}")
    result = price_car(car, retriever)
    _print_result(car, result)
    route_by_confidence(result)


def demo_batch_eval(retriever: RealCarRAGRetriever, listings: List[RealCarListing]):
    """Demo 4: 批量回测评估（从真实/模拟数据中取样）"""
    _sep("Demo 4: 批量定价回测")

    # 取前 8 条有完整标签的数据
    test_cases = [c for c in listings if c.c2b_price and c.b2c_price][:8]
    if not test_cases:
        print("  无可用测试数据")
        return

    print(f"\n  {'车辆':<22} {'C2B预测':>7} {'C2B实际':>7} {'C2B误差':>7} "
          f"{'B2C预测':>7} {'B2C实际':>7} {'B2C误差':>7} {'毛利率':>7}  R_total")
    print(f"  {'─'*90}")

    c2b_errors, b2c_errors, r_totals = [], [], []

    for car in test_cases:
        result = price_car(car, retriever, n_paths=1, verbose=False)
        if not (car.c2b_price and car.b2c_price):
            continue

        err_c2b = abs(result.c2b_price - car.c2b_price) / car.c2b_price
        err_b2c = abs(result.b2c_price - car.b2c_price) / car.b2c_price
        c2b_errors.append(err_c2b)
        b2c_errors.append(err_b2c)
        r_totals.append(result.r_total)

        flag = "✓" if err_c2b < 0.10 and err_b2c < 0.10 else ("~" if err_c2b < 0.15 else "✗")
        label = f"{car.brand}{car.series}{car.model_year}"[:20]
        print(f"  {label:<22} {result.c2b_price:>7.2f} {car.c2b_price:>7.2f} {err_c2b:>7.1%} "
              f"{result.b2c_price:>7.2f} {car.b2c_price:>7.2f} {err_b2c:>7.1%} "
              f"{result.gross_margin_pct:>6.1f}% {result.r_total:>7.4f}  {flag}")

    print(f"\n  {'─'*90}")
    if c2b_errors:
        print(f"  C2B 准确率(误差<10%)：{sum(1 for e in c2b_errors if e<0.10)/len(c2b_errors):.0%}  "
              f"平均误差：{sum(c2b_errors)/len(c2b_errors):.1%}")
        print(f"  B2C 准确率(误差<10%)：{sum(1 for e in b2c_errors if e<0.10)/len(b2c_errors):.0%}  "
              f"平均误差：{sum(b2c_errors)/len(b2c_errors):.1%}")
        print(f"  平均 R_total：{sum(r_totals)/len(r_totals):.4f}")

    # REPLACE-5: 此处写入监控系统
    # monitoring.gauge("car_pricing.c2b_mape", sum(c2b_errors)/len(c2b_errors))
    # monitoring.gauge("car_pricing.b2c_mape", sum(b2c_errors)/len(b2c_errors))
    print(f"\n  [REPLACE-5] 此处将评估结果写入监控/日志系统")


# ─────────────────────────────────────────────────────
#  主程序
# ─────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="二手车双价格定价系统（LLM版）")
    parser.add_argument("--data",   type=str, help="清洗后的数据文件路径（.csv）")
    parser.add_argument("--sheet",  type=str, default="0")
    parser.add_argument("--paths",  type=int, default=3, help="多路径采样数量")
    parser.add_argument("--description", "--desc", type=str, help="验车师输入的文本描述")
    args = parser.parse_args()

    _sep("二手车双价格定价系统（LLM版）")
    print(f"""
  架构：
    ┌──────────────────────────────────────────────────┐
    │  RealCarListing（真实字段结构）                   │
    │       ↓                                          │
    │  [REPLACE-2] RealCarRAGRetriever                 │
    │       ↓  同品牌同车系优先 + 数值特征相似度         │
    │  [REPLACE-4] LLM 四步 CoT 双价格推理              │
    │       ↓  × {args.paths}条路径（不同temperature）          │
    │  中位数聚合 → C2B价格 + B2C价格 + 定价理由         │
    │       ↓                                          │
    │  置信度路由 → 自动通过 / 人工复核                  │
    └──────────────────────────────────────────────────┘
    
  LLM状态：{"✅ 已连接" if LLM_AVAILABLE else "⚠️  未配置API Key，将使用规则引擎兜底"}
""")

    # 加载历史成交数据（知识库）
    if args.data and os.path.exists(args.data):
        print(f"[知识库] 从文件加载：{args.data}")
        import pandas as pd
        df = pd.read_csv(args.data, encoding="utf-8-sig")
        listings = df_to_listings(df)
    else:
        print("[知识库] 使用模拟数据（真实场景请传入 --data 参数）")
        df_raw = generate_mock_data(150)
        from data_processor import DataCleaner
        cleaner = DataCleaner(verbose=False)
        df_raw = cleaner.normalize_columns(df_raw)
        df_clean = cleaner.drop_invalid_prices(df_raw)
        listings = df_to_listings(df_clean)

    # 构建 RAG 检索器
    retriever = RealCarRAGRetriever(listings)

    # 处理验车师输入的文本描述
    if args.description:
        _sep("验车师文本描述定价")
        print(f"\n  [输入] {args.description[:60]}{'...' if len(args.description)>60 else ''}")
        result = price_from_description(args.description, retriever, n_paths=args.paths)
        print(f"\n  ┌── 定价结果")
        print(f"  │  C2B 收购价：{result.c2b_price} 万元  [{result.c2b_low}, {result.c2b_high}]")
        print(f"  │  B2C 销售价：{result.b2c_price} 万元  [{result.b2c_low}, {result.b2c_high}]")
        print(f"  │  预计毛利：{result.gross_profit:.2f}万（{result.gross_margin_pct:.1f}%）")
        print(f"  │  置信度：{result.confidence}")
        if result.risk_notes:
            print(f"  │  风险：{result.risk_notes[0]}")
        print(f"  │  定价理由：{result.pricing_reason}")
        print(f"  └{'─'*45}")
        route_by_confidence(result)
        _sep("定价完成")
    else:
        # Demo 0：验车师文字描述场景（核心业务场景，优先运行）
        demo_from_description(retriever)

        # Demo 1-4：结构化字段输入场景
        demo_single_normal(retriever)
        demo_single_high_risk(retriever)
        demo_new_energy(retriever)
        demo_batch_eval(retriever, listings)

        _sep("演示完成")
        print("""
  接入真实数据的步骤：
    1. 清洗历史数据：python data_processor.py --input your_data.xlsx --output cleaned.csv
    2. 启动定价系统：python demo_llm_real.py --data cleaned.csv
    3. 配置LLM：    export ANTHROPIC_API_KEY="sk-ant-..."

  验车师输入方式（命令行）：
    python demo_llm_real.py --description "2021年凯美瑞2.5L，白色，行驶6.8万公里..."

  验车师输入方式（代码调用）：
    from demo_llm_real import price_from_description, RealCarRAGRetriever
    result = price_from_description("2021年凯美瑞...", retriever)
    print(result.c2b_price, result.b2c_price, result.pricing_reason)
""")


if __name__ == "__main__":
    main()
