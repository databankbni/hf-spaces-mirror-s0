from __future__ import annotations

import re
from typing import Any

from .business_market_workbook_loader import normalize_text


LUXURY_BRANDS = {
    "奔驰",
    "宝马",
    "奥迪",
    "雷克萨斯",
    "凯迪拉克",
    "沃尔沃",
    "林肯",
    "英菲尼迪",
    "讴歌",
    "捷豹",
    "路虎",
    "保时捷",
    "玛莎拉蒂",
    "阿尔法罗密欧",
    "宾利",
    "劳斯莱斯",
    "法拉利",
    "兰博基尼",
    "阿斯顿·马丁",
    "smart",
    "MINI",
    "DS",
    "Genesis",
}

# “豪华新能源”在一线经营里不是“传统豪华品牌 + 新能源”的机械交集。
# 它还包括已经形成高端价格/品牌心智的新势力和自主高端子品牌。把它单独
# 建模，才能让“20 万豪华新能源”和“30 万豪华新能源”在真实候选池里按
# 预算利用率产生不同结果，而不是永远只剩少数老款 BBA 新能源车。
PREMIUM_NEW_ENERGY_BRANDS = {
    "理想汽车",
    "理想",
    "蔚来",
    "极氪",
    "阿维塔",
    "问界",
    "AITO",
    "智界",
    "享界",
    "尊界",
    "鸿蒙智行",
    "智己汽车",
    "智己",
    "岚图",
    "腾势",
    "仰望",
    "高合HiPhi",
    "高合",
    "小米汽车",
    "小米",
}

INDEPENDENT_BRANDS = {
    "比亚迪",
    "吉利汽车",
    "吉利几何",
    "吉利银河",
    "长安",
    "长城",
    "哈弗",
    "魏牌",
    "坦克",
    "奇瑞",
    "星途",
    "捷途",
    "广汽传祺",
    "广汽埃安",
    "红旗",
    "奔腾",
    "荣威",
    "名爵",
    "MG",
    "五菱汽车",
    "宝骏",
    "理想汽车",
    "蔚来",
    "小鹏汽车",
    "零跑汽车",
    "哪吒汽车",
    "极氪",
    "领克",
    "深蓝汽车",
    "阿维塔",
    "问界",
    "智界",
    "享界",
    "鸿蒙智行",
    "智己汽车",
    "岚图",
    "腾势",
    "方程豹",
    "仰望",
    "小米汽车",
    "乐道",
    "启源",
    "东风风神",
    "东风风行",
    "东风奕派",
    "北京汽车",
    "北汽新能源",
    "大通",
    "江淮",
    "江铃集团新能源",
    "欧拉",
    "几何汽车",
    "极狐",
    "合创汽车",
    "创维汽车",
    "天际汽车",
    "爱驰",
    "高合HiPhi",
}

BRAND_TIER_ALIASES = {
    "自主": "自主",
    "自主燃油": "自主",
    "国产": "自主",
    "国产燃油": "自主",
    "合资": "合资",
    "合资燃油": "合资",
    "非豪华合资": "合资",
    "豪华": "豪华",
    "豪华燃油": "豪华",
    "豪华品牌": "豪华",
    "豪华新能源": "豪华新能源",
    "高端新能源": "豪华新能源",
    "新能源豪华": "豪华新能源",
}


def normalize_brand_tier(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text in {"全部", "总计", "不限"}:
        return ""
    return BRAND_TIER_ALIASES.get(text, "")


def extract_brand_tier_from_text(text: Any) -> str:
    raw = str(text or "")
    if re.search(r"(?:豪华|高端)(?:新能源|纯电|插混|混动|增程)|新能源豪华", raw):
        return "豪华新能源"
    if re.search(r"自主(?:燃油|品牌|车系|阵营)?|国产(?:燃油|品牌|车系|阵营)?", raw):
        return "自主"
    if re.search(r"合资(?:燃油|品牌|车系|阵营)?|非豪华合资", raw):
        return "合资"
    if re.search(r"豪华(?:新能源|纯电|插混|混动|增程|燃油|品牌|车系|阵营)", raw) or re.search(
        r"(?:看|筛|选|做|收|推荐|机会|值得).{0,6}豪华|豪华.{0,8}(?:机会|推荐|值得|可收|能做)",
        raw,
    ):
        return "豪华"
    return ""


def classify_brand_tier(brand: Any) -> str:
    key = normalize_text(brand)
    if not key:
        return "未知"
    luxury_keys = {normalize_text(item) for item in LUXURY_BRANDS}
    independent_keys = {normalize_text(item) for item in INDEPENDENT_BRANDS}
    if key in luxury_keys or any(key.startswith(item) or item.startswith(key) for item in luxury_keys if item):
        return "豪华"
    if key in independent_keys or any(key.startswith(item) or item.startswith(key) for item in independent_keys if item):
        return "自主"
    return "合资"


def matches_brand_tier(brand: Any, tier: Any) -> bool:
    normalized = normalize_brand_tier(tier) or str(tier or "").strip()
    if not normalized or normalized in {"全部", "总计"}:
        return True
    if normalized == "豪华新能源":
        key = normalize_text(brand)
        premium_keys = {normalize_text(item) for item in PREMIUM_NEW_ENERGY_BRANDS}
        return classify_brand_tier(brand) == "豪华" or key in premium_keys or any(
            key.startswith(item) or item.startswith(key) for item in premium_keys if item
        )
    return classify_brand_tier(brand) == normalized
