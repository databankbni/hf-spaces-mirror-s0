from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GeoResolution:
    city: str
    confidence: float
    matched_text: str
    reason: str


PROVINCE_CAPITALS: dict[str, str] = {
    "山东": "济南",
    "山东省": "济南",
    "河南": "郑州",
    "河南省": "郑州",
    "河北": "石家庄",
    "河北省": "石家庄",
    "山西": "太原",
    "山西省": "太原",
    "陕西": "西安",
    "陕西省": "西安",
    "江苏": "南京",
    "江苏省": "南京",
    "浙江": "杭州",
    "浙江省": "杭州",
    "安徽": "合肥",
    "安徽省": "合肥",
    "江西": "南昌",
    "江西省": "南昌",
    "福建": "福州",
    "福建省": "福州",
    "广东": "广州",
    "广东省": "广州",
    "广西": "南宁",
    "广西壮族自治区": "南宁",
    "海南": "海口",
    "海南省": "海口",
    "四川": "成都",
    "四川省": "成都",
    "贵州": "贵阳",
    "贵州省": "贵阳",
    "云南": "昆明",
    "云南省": "昆明",
    "湖北": "武汉",
    "湖北省": "武汉",
    "湖南": "长沙",
    "湖南省": "长沙",
    "辽宁": "沈阳",
    "辽宁省": "沈阳",
    "吉林": "长春",
    "吉林省": "长春",
    "黑龙江": "哈尔滨",
    "黑龙江省": "哈尔滨",
    "甘肃": "兰州",
    "甘肃省": "兰州",
    "青海": "西宁",
    "青海省": "西宁",
    "台湾": "台北",
    "台湾省": "台北",
    "内蒙古": "呼和浩特",
    "内蒙古自治区": "呼和浩特",
    "宁夏": "银川",
    "宁夏回族自治区": "银川",
    "新疆": "乌鲁木齐",
    "新疆维吾尔自治区": "乌鲁木齐",
    "西藏": "拉萨",
    "西藏自治区": "拉萨",
}

MUNICIPALITIES = {
    "北京": "北京",
    "北京市": "北京",
    "上海": "上海",
    "上海市": "上海",
    "天津": "天津",
    "天津市": "天津",
    "重庆": "重庆",
    "重庆市": "重庆",
}

CITY_ALIASES = {
    "魔都": "上海",
    "帝都": "北京",
    "羊城": "广州",
    "鹏城": "深圳",
    "山城": "重庆",
    "蓉城": "成都",
    "泉城": "济南",
    "江城": "武汉",
    "金陵": "南京",
    "杭城": "杭州",
    "冰城": "哈尔滨",
}

REGION_DEFAULT_CITY = {
    "江浙沪": "上海",
    "长三角": "上海",
    "珠三角": "广州",
    "京津冀": "北京",
    "成渝": "重庆",
}


def normalize_geo_text(text: Any) -> str:
    return re.sub(r"[\s,，。._/()（）·・\-]+", "", str(text or ""))


def resolve_city(text: Any, known_cities: list[str] | tuple[str, ...] | None = None) -> GeoResolution | None:
    raw = str(text or "")
    compact = normalize_geo_text(raw)
    if not compact:
        return None

    candidates = list(known_cities or [])
    for city in sorted(set(candidates), key=lambda value: (-len(value), value)):
        if city and normalize_geo_text(city) in compact:
            return GeoResolution(city=city, confidence=0.95, matched_text=city, reason="explicit_city")

    for alias, city in sorted(CITY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if alias in compact:
            return GeoResolution(city=city, confidence=0.88, matched_text=alias, reason="city_alias")

    province_capital_pattern = re.compile(
        r"(?P<province>[\u4e00-\u9fa5]{2,8}(?:省|自治区)?)"
        r"(?:的)?(?:省会|省城|首府|首府城市|省府)"
    )
    for match in province_capital_pattern.finditer(compact):
        province = match.group("province")
        if province in PROVINCE_CAPITALS:
            return GeoResolution(
                city=PROVINCE_CAPITALS[province],
                confidence=0.91,
                matched_text=match.group(0),
                reason="province_capital",
            )
        short = province.removesuffix("省").removesuffix("自治区")
        if short in PROVINCE_CAPITALS:
            return GeoResolution(
                city=PROVINCE_CAPITALS[short],
                confidence=0.9,
                matched_text=match.group(0),
                reason="province_capital",
            )

    for province, capital in sorted(PROVINCE_CAPITALS.items(), key=lambda item: len(item[0]), reverse=True):
        if province in compact and re.search(r"省会|省城|首府|省府", compact):
            return GeoResolution(city=capital, confidence=0.88, matched_text=province, reason="province_capital")

    for name, city in MUNICIPALITIES.items():
        if name in compact and re.search(r"直辖市|市里|城区|本地", compact):
            return GeoResolution(city=city, confidence=0.82, matched_text=name, reason="municipality_alias")

    for region, city in REGION_DEFAULT_CITY.items():
        if region in compact:
            return GeoResolution(city=city, confidence=0.7, matched_text=region, reason="region_default_city")

    return None
