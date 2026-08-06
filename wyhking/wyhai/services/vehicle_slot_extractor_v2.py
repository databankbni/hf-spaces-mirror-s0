from __future__ import annotations

import difflib
import gzip
import json
import os
import re
from pathlib import Path
from typing import Any, Dict

from .geo_resolver import resolve_city
from .intent_schema_v2 import empty_slots
from .intent_system import parse_vehicle_slots
from .llm_client import Qwen3LocalClient, extract_json_object
from .vehicle_identity_semantics import (
    alias_match_kind,
    code_compatibility,
    distinctive_vehicle_codes,
    find_explicit_brand,
    most_specific_query_code,
)


_SPACE_RE = re.compile(r"[\s\u3000]+")
ROOT = Path(__file__).resolve().parents[1]
CATALOG_INDEX_PATH = ROOT / "data" / "runtime" / "vehicle_catalog_search_index.json.gz"
ONLINE_SERIES_INDEX_PATH = ROOT / "data" / "runtime" / "autohome_vehicle_series_catalog.json.gz"


def _is_range_or_version_km(text: str, match: re.Match[str]) -> bool:
    raw = match.group(0).lower()
    if "km" not in raw:
        return False
    before = text[max(0, match.start() - 12):match.start()].lower()
    after = text[match.end():match.end() + 8].lower()
    return bool(
        re.search(r"dm-?i|dmi|ev|phev|续航|纯电|插混|增程|版|型|plus|pro|max", before + after)
        or re.search(r"进取|领先|荣耀|冠军|豪华|尊贵|旗舰", after)
    )

BRAND_ALIASES = {
    "宝妈": "宝马",
    "宝馬": "宝马",
    "奔弛": "奔驰",
    "奥帝": "奥迪",
    "奥笛": "奥迪",
    "特死拉": "特斯拉",
    "特斯啦": "特斯拉",
    "毛豆": "特斯拉",
    "问届": "问界",
    "aito": "问界",
    "AITO": "问界",
    "保时节": "保时捷",
    "路虎揽圣": "路虎揽胜",
}

# Ordered by specificity.  The canonical series intentionally does not repeat
# the brand, which keeps the V2 API stable across catalog and free-text inputs.
SERIES_ALIASES = [
    ("捷途旅行者", "捷途", "捷途旅行者"),
    ("起亚k5凯酷", "起亚", "K5凯酷"),
    ("观致观致5", "观致", "观致5"),
    ("大众id.4crozz", "大众", "ID.4 CROZZ"),
    ("大众id4crozz", "大众", "ID.4 CROZZ"),
    ("id.4crozz", "大众", "ID.4 CROZZ"),
    ("id4crozz", "大众", "ID.4 CROZZ"),
    ("路虎揽胜极光", "路虎", "揽胜极光"),
    ("揽胜极光", "路虎", "揽胜极光"),
    ("腾势d9dm-i", "腾势", "D9 DM-i"),
    ("腾势d9dmi", "腾势", "D9 DM-i"),
    ("瑞虎8plus", "奇瑞", "瑞虎8 PLUS"),
    ("深蓝s07", "深蓝", "S07"),
    ("红旗e-hs9", "红旗", "E-HS9"),
    ("红旗ehs9", "红旗", "E-HS9"),
    ("捷尼赛思g80", "捷尼赛思", "G80"),
    ("哪吒s", "哪吒", "S"),
    ("睿蓝7", "睿蓝", "7"),
    ("威马ex5", "威马", "EX5"),
    ("几何a", "吉利几何", "吉利几何A"),
    ("五菱宏光miniev", "五菱", "宏光MINIEV"),
    ("宏光miniev", "五菱", "宏光MINIEV"),
    ("毛豆y", "特斯拉", "Model Y"),
    ("毛豆3", "特斯拉", "Model 3"),
    ("modely", "特斯拉", "Model Y"),
    ("model3", "特斯拉", "Model 3"),
    ("奔驰c级", "奔驰", "C级"),
    ("奔驰c260l", "奔驰", "C级"),
    ("c260l", "奔驰", "C级"),
    ("奔驰e级", "奔驰", "E级"),
    ("奔驰e300l", "奔驰", "E级"),
    ("奥迪a6l", "奥迪", "A6L"),
    ("奥迪a4l", "奥迪", "A4L"),
    ("奥迪a4", "奥迪", "A4L"),
    ("奥迪q5l", "奥迪", "Q5L"),
    ("宝马三系", "宝马", "3系"),
    ("宝马3系", "宝马", "3系"),
    ("3系", "宝马", "3系"),
    ("宝马325li", "宝马", "3系"),
    ("325li", "宝马", "3系"),
    ("宝马530li", "宝马", "5系"),
    ("530li", "宝马", "5系"),
    ("宝马525li", "宝马", "5系"),
    ("525li", "宝马", "5系"),
    ("宝马x7", "宝马", "X7"),
    ("宝马x5", "宝马", "X5"),
    ("宝马x3", "宝马", "X3"),
    ("宝沃bx7", "宝沃", "BX7"),
    ("纳智捷大七", "纳智捷", "大7 SUV"),
    ("纳智捷大7", "纳智捷", "大7 SUV"),
    ("dsds7", "DS", "DS 7"),
    ("ds7", "DS", "DS 7"),
    ("高合hiphix", "高合", "HiPhi X"),
    ("hiphix", "高合", "HiPhi X"),
    ("创维ht-i", "创维", "HT-i"),
    ("天际me5", "天际", "ME5"),
    ("爱驰u5", "爱驰", "U5"),
    ("魏牌蓝山", "魏牌", "蓝山DHT-PHEV"),
    ("蓝山dht-phev", "魏牌", "蓝山DHT-PHEV"),
    ("理想l8", "理想", "L8"),
    ("理想l7", "理想", "L7"),
    ("理想l6", "理想", "L6"),
    ("问界m7", "问界", "M7"),
    ("问界m5", "问界", "M5"),
    ("小米su7", "小米", "SU7"),
    ("小鹏monam03", "小鹏", "MONA M03"),
    ("小鹏mona m03", "小鹏", "MONA M03"),
    ("monam03", "小鹏", "MONA M03"),
    ("mona m03", "小鹏", "MONA M03"),
    ("小鹏g6", "小鹏", "G6"),
    ("蔚来es6", "蔚来", "ES6"),
    ("岚图free", "岚图", "FREE"),
    ("领克07em-p", "领克", "07 EM-P"),
    ("领克07emp", "领克", "07 EM-P"),
    ("领克07", "领克", "07 EM-P"),
    ("吉利icon", "吉利", "ICON"),
    ("极氪zeekr7x", "极氪", "ZEEKR 7X"),
    ("极氪7x", "极氪", "ZEEKR 7X"),
    ("zeekr7x", "极氪", "ZEEKR 7X"),
    ("宋plusdmi", "比亚迪", "宋PLUS DM-i"),
    ("宋plusdm-i", "比亚迪", "宋PLUS DM-i"),
    ("比亚迪宋plus", "比亚迪", "宋PLUS"),
    ("比亚迪汉dm-i", "比亚迪", "汉DM-i"),
    ("比亚迪汉dmi", "比亚迪", "汉DM-i"),
    ("汉dm-i", "比亚迪", "汉DM-i"),
    ("汉dmi", "比亚迪", "汉DM-i"),
    ("比亚迪汉", "比亚迪", "汉"),
    ("本田雅阁", "本田", "雅阁"),
    ("丰田凯美瑞", "丰田", "凯美瑞"),
    ("大众迈腾", "大众", "迈腾"),
    ("大众朗逸", "大众", "朗逸"),
    ("日产轩逸", "日产", "轩逸"),
    ("别克gl8", "别克", "GL8"),
    ("保时捷macan", "保时捷", "Macan"),
    ("路虎揽胜", "路虎", "揽胜"),
    ("红旗h5", "红旗", "H5"),
    ("沃尔沃xc60", "沃尔沃", "XC60"),
    ("凯美瑞", "丰田", "凯美瑞"),
    ("雅阁", "本田", "雅阁"),
    ("迈腾", "大众", "迈腾"),
    ("朗逸", "大众", "朗逸"),
    ("轩逸", "日产", "轩逸"),
    ("gl8", "别克", "GL8"),
    ("macan", "保时捷", "Macan"),
    ("揽胜", "路虎", "揽胜"),
    ("a6l", "奥迪", "A6L"),
    ("q5l", "奥迪", "Q5L"),
    ("x7", "宝马", "X7"),
]

KNOWN_BRANDS = (
    "宝马",
    "奔驰",
    "奥迪",
    "特斯拉",
    "理想",
    "问界",
    "小鹏",
    "蔚来",
    "比亚迪",
    "本田",
    "丰田",
    "大众",
    "日产",
    "别克",
    "保时捷",
    "路虎",
    "五菱",
    "红旗",
    "沃尔沃",
    "雷克萨斯",
    "纳智捷",
    "创维",
    "爱驰",
    "DS",
    "小米",
    "岚图",
    "领克",
    "吉利",
    "极氪",
)

CATALOG_BRAND_CANONICAL = {
    "理想汽车": "理想",
    "小鹏汽车": "小鹏",
    "蔚来汽车": "蔚来",
    "比亚迪汽车": "比亚迪",
    "一汽丰田": "丰田",
    "广汽丰田": "丰田",
    "东风本田": "本田",
    "广汽本田": "本田",
    "华晨宝马": "宝马",
    "北京奔驰": "奔驰",
    "一汽奥迪": "奥迪",
    "一汽-大众": "大众",
    "上汽大众": "大众",
    "上汽通用别克": "别克",
    "AITO": "问界",
    "小米汽车": "小米",
    "五菱汽车": "五菱",
    "长安汽车": "长安",
}

COMMON_CITIES = (
    "北京",
    "上海",
    "广州",
    "深圳",
    "重庆",
    "成都",
    "杭州",
    "苏州",
    "南京",
    "武汉",
    "西安",
    "郑州",
    "天津",
    "长沙",
    "青岛",
    "宁波",
    "合肥",
    "佛山",
    "东莞",
    "厦门",
    "昆明",
    "济南",
    "沈阳",
    "大连",
    "无锡",
    "温州",
    "南通",
    "常州",
    "太原",
    "台州",
    "唐山",
    "长春",
    "哈尔滨",
    "石家庄",
    "南昌",
    "福州",
    "南宁",
    "贵阳",
    "兰州",
    "乌鲁木齐",
    "呼和浩特",
    "海口",
    "银川",
    "西宁",
    "拉萨",
    "徐州",
    "泉州",
    "绍兴",
    "嘉兴",
    "金华",
    "烟台",
    "潍坊",
    "临沂",
    "洛阳",
    "南阳",
    "宜昌",
    "襄阳",
    "珠海",
    "中山",
    "惠州",
    "江门",
    "保定",
    "廊坊",
    "邯郸",
    "芜湖",
    "赣州",
    "绵阳",
    "全国",
)

PLATE_CITY_ALIASES = {
    "沪牌": "上海",
    "京牌": "北京",
    "粤牌": "广州",
    "深牌": "深圳",
    "渝牌": "重庆",
    "蓉牌": "成都",
    "浙牌": "杭州",
    "苏牌": "南京",
}

GENERIC_SCOPE_TERMS = {
    "suv", "mpv", "轿车", "家用车", "代步车", "b级车",
    "新能源", "新能源车", "纯电", "插混", "混动", "增程", "燃油", "燃油车", "油车",
}

COLOR_ALIASES = {
    "珍珠白": "白色",
    "白色": "白色",
    "黑色": "黑色",
    "灰色": "灰色",
    "银色": "银色",
    "银灰": "银色",
    "银灰色": "银色",
    "红色": "红色",
    "蓝色": "蓝色",
    "绿色": "绿色",
    "棕色": "棕色",
    "咖啡色": "棕色",
    "橙色": "橙色",
    "香槟色": "香槟色",
    "金色": "金色",
    "米色": "米色",
    "黄色": "黄色",
    "紫色": "紫色",
    "其他颜色": "其他",
    "其它颜色": "其他",
    "其他": "其他",
    "其它": "其他",
}


def _compact(text: str) -> str:
    normalized = str(text or "")
    for wrong, right in BRAND_ALIASES.items():
        normalized = normalized.replace(wrong, right)
    normalized = normalized.replace("三糸", "3系").replace("3糸", "3系").replace("三系", "3系")
    normalized = normalized.replace("ｍ", "m").replace("Ｍ", "M")
    return re.sub(r"[\s,，。._/()（）·・\-]+", "", normalized).lower()


def _flat(value: Any) -> Any:
    return value.get("value") if isinstance(value, dict) and "value" in value else value


class VehicleCatalogIntentIndex:
    _records: list[dict[str, Any]] | None = None
    _series_entries: list[dict[str, str]] | None = None

    def _load(self) -> None:
        if self.__class__._records is not None:
            return
        records: list[dict[str, Any]] = []
        if CATALOG_INDEX_PATH.exists():
            try:
                with gzip.open(CATALOG_INDEX_PATH, "rt", encoding="utf-8") as handle:
                    payload = json.load(handle)
                if isinstance(payload, list):
                    records = [row for row in payload if isinstance(row, dict)]
            except (OSError, ValueError, json.JSONDecodeError):
                records = []
        online_series: list[dict[str, Any]] = []
        if ONLINE_SERIES_INDEX_PATH.exists():
            try:
                with gzip.open(ONLINE_SERIES_INDEX_PATH, "rt", encoding="utf-8") as handle:
                    payload = json.load(handle)
                if isinstance(payload, list):
                    online_series = [row for row in payload if isinstance(row, dict)]
            except (OSError, ValueError, json.JSONDecodeError):
                online_series = []
        entries: dict[tuple[str, str], dict[str, str]] = {}
        for row in records:
            raw_brand = str(row.get("brand") or "").strip()
            brand = self._canonical_brand(raw_brand)
            raw_series = str(row.get("series") or "").strip()
            if not brand or not raw_series:
                continue
            series = raw_series
            for prefix in (raw_brand, brand):
                if prefix and series.startswith(prefix):
                    series = series[len(prefix) :]
                    break
            series = series.strip() or raw_series
            aliases = {
                _compact(raw_series),
                _compact(series),
                _compact(f"{brand}{series}"),
            }
            entry = entries.setdefault(
                (brand, series),
                {
                    "brand": brand,
                    "series": series,
                    "series_raw": raw_series,
                    "aliases": "",
                },
            )
            existing = set(filter(None, entry["aliases"].split("|")))
            existing.update(filter(None, aliases))
            entry["aliases"] = "|".join(sorted(existing, key=len, reverse=True))
        for row in online_series:
            raw_brand = str(row.get("brand") or "").strip()
            brand = self._canonical_brand(raw_brand)
            raw_series = str(row.get("series") or "").strip()
            if not brand or not raw_series:
                continue
            series = raw_series
            if series.startswith(brand):
                series = series[len(brand) :]
            series = series.strip() or raw_series
            aliases = {_compact(raw_series), _compact(series), _compact(f"{brand}{series}")}
            entry = entries.setdefault(
                (brand, series),
                {"brand": brand, "series": series, "series_raw": raw_series, "aliases": ""},
            )
            existing = set(filter(None, entry["aliases"].split("|")))
            existing.update(filter(None, aliases))
            entry["aliases"] = "|".join(sorted(existing, key=len, reverse=True))
        self.__class__._records = records
        self.__class__._series_entries = list(entries.values())

    @staticmethod
    def _canonical_brand(raw_brand: str) -> str:
        brand = CATALOG_BRAND_CANONICAL.get(raw_brand, raw_brand)
        if brand.endswith("汽车") and len(brand) > 2:
            brand = brand[:-2]
        return brand

    def known_brands(self) -> set[str]:
        self._load()
        return {entry["brand"] for entry in (self.__class__._series_entries or [])}

    def match(self, message: str, context_brand: str | None = None) -> Dict[str, Any] | None:
        self._load()
        compact = _compact(message)
        if not compact:
            return None
        entries = self.__class__._series_entries or []
        explicit_brand = find_explicit_brand(message, self.known_brands())
        constrained_brand = explicit_brand or context_brand

        exact_matches = []
        short_exact_matches = []
        for entry in entries:
            if constrained_brand and entry["brand"] != constrained_brand:
                continue
            aliases = entry["aliases"].split("|")
            matched_alias = None
            matched_kind = None
            for alias in aliases:
                if len(alias) < 2:
                    continue
                if not constrained_brand and alias.lower() in GENERIC_SCOPE_TERMS:
                    continue
                kind = alias_match_kind(alias, message)
                if not kind or (kind == "family_code" and not constrained_brand):
                    continue
                if len(alias) >= 3 or _compact(entry["brand"]) in compact:
                    matched_alias = alias
                    matched_kind = kind
                    break
                if re.fullmatch(r"[a-z]+\d+[a-z]*", alias, flags=re.I):
                    short_exact_matches.append((entry, alias))
            if matched_alias:
                kind_rank = {
                    "exact_text": 5,
                    "exact_token": 5,
                    "exact_code": 4,
                    "family_code": 2,
                }.get(str(matched_kind), 0)
                query_codes = distinctive_vehicle_codes(message)
                alias_codes = distinctive_vehicle_codes(matched_alias)
                query_primary_code = most_specific_query_code(message)
                alias_primary_code = most_specific_query_code(matched_alias)
                primary_code_exact = int(
                    bool(query_primary_code)
                    and query_primary_code == alias_primary_code
                )
                extra_code_length = max(
                    [
                        max(len(code) - len(query_code), 0)
                        for code in alias_codes
                        for query_code in query_codes
                        if code.startswith(query_code)
                    ]
                    or [0]
                )
                name_specificity = (
                    len(entry["series"])
                    if matched_kind in {"exact_text", "exact_token"}
                    else -len(entry["series"])
                )
                exact_matches.append(
                    (
                        kind_rank,
                        primary_code_exact,
                        -extra_code_length,
                        name_specificity,
                        entry,
                        matched_alias,
                        matched_kind,
                    )
                )
        if exact_matches:
            _, _, _, _, entry, alias, matched_kind = max(
                exact_matches,
                key=lambda item: item[:4],
            )
            query_code = most_specific_query_code(message)
            inferred_trim_code = None
            if query_code and code_compatibility(message, entry["series"]) is True:
                series_codes = most_specific_query_code(entry["series"])
                if not series_codes or query_code != series_codes:
                    inferred_trim_code = query_code.upper()
            return {
                "brand": entry["brand"],
                "series": entry["series"],
                "match_method": (
                    "catalog_family_code_resolution"
                    if matched_kind == "family_code"
                    else "catalog_exact_or_normalized"
                ),
                "match_score": 0.9 if matched_kind == "family_code" else 1.0,
                "matched_alias": alias,
                "inferred_trim_code": inferred_trim_code,
            }
        unique_short = {
            (entry["brand"], entry["series"]): (entry, alias)
            for entry, alias in short_exact_matches
        }
        if len(unique_short) == 1:
            entry, alias = next(iter(unique_short.values()))
            return {
                "brand": entry["brand"],
                "series": entry["series"],
                "match_method": "catalog_unique_short_series",
                "match_score": 0.96,
                "matched_alias": alias,
            }

        # Typo recovery is restricted to an explicitly recognized brand.  This
        # prevents a short generic token such as "X7" from silently becoming a
        # BMW when the user actually meant another product.
        normalized_message = str(message or "")
        for wrong, right in BRAND_ALIASES.items():
            normalized_message = normalized_message.replace(wrong, right)
        brand = find_explicit_brand(normalized_message, self.known_brands())
        brand = brand or context_brand
        if not brand:
            return None
        query_tail = compact.replace(_compact(brand), "", 1)
        if len(query_tail) < 2:
            return None
        scored = []
        for entry in entries:
            if entry["brand"] != brand:
                continue
            compatibility = code_compatibility(message, f"{entry['series_raw']} {entry['series']}")
            if compatibility is False:
                continue
            alias_scores = [
                difflib.SequenceMatcher(None, query_tail, alias).ratio()
                for alias in entry["aliases"].split("|")
                if alias
            ]
            if compatibility is True:
                alias_scores.append(0.92)
            score = max(alias_scores or [0.0])
            if score >= 0.68:
                scored.append((score, entry))
        if not scored:
            return None
        score, entry = max(scored, key=lambda item: item[0])
        return {
            "brand": entry["brand"],
            "series": entry["series"],
            "match_method": "catalog_fuzzy_typo_recovery",
            "match_score": round(score, 4),
            "matched_alias": None,
            "inferred_trim_code": (
                most_specific_query_code(message)
                if code_compatibility(message, f"{entry['series_raw']} {entry['series']}") is True
                else None
            ),
        }


class VehicleSlotExtractorV2:
    def __init__(self, llm_client: Qwen3LocalClient | None = None) -> None:
        self.llm_client = llm_client or Qwen3LocalClient()
        self.catalog_index = VehicleCatalogIntentIndex()
        self.enable_qwen_fallback = os.environ.get(
            "INTENT_V2_ENABLE_QWEN_SLOT_FALLBACK", "false"
        ).lower() in {"1", "true", "yes", "on"}

    def extract(self, message: str, client_state: Dict[str, Any] | None = None) -> Dict[str, Any]:
        text = str(message or "")
        compact = _compact(text)
        slots = empty_slots()
        metadata = {
            "source": "deterministic_catalog_alias_regex",
            "fallback_used": False,
            "fallback_reason": "",
            "catalog_match": None,
        }

        state_slots = (client_state or {}).get("current_slots") or {}
        context_brand = _flat(state_slots.get("brand"))
        alias_match = None
        for alias, brand, series in SERIES_ALIASES:
            if _compact(alias) in compact:
                alias_match = (alias, brand, series)
                break

        # A later pricing turn often contains only registration/mileage/condition
        # fields (for example ``成都，1次过户，B级车况``).  Those numbers and the
        # grade letter must never be sent through fuzzy vehicle matching: with a
        # saved BMW context, ``1次`` used to be recovered as BMW 1 Series and
        # ``B级`` could be mistaken for a trim code.  A genuine terse identity
        # update such as ``525Li`` is still allowed because it has a safe alias.
        known_brand_tokens = set(self.catalog_index.known_brands()) | set(KNOWN_BRANDS)
        known_brand_tokens.update(BRAND_ALIASES)
        has_explicit_brand = find_explicit_brand(text, known_brand_tokens) is not None
        has_safe_alias = bool(alias_match and len(_compact(alias_match[0])) >= 2)
        has_followup_fields = bool(
            re.search(
                r"上牌|登记|落户|初登|注册|公里|里程|过户|车况|检测|评级|"
                r"白色|黑色|灰色|银色|红色|蓝色|绿色|棕色|紫色|橙色|香槟色|"
                r"客户给|客户出|挂牌|挂价|卖多少钱|估收车价|最多出|重新估价",
                text,
                flags=re.I,
            )
        )
        has_identity_change_cue = bool(
            re.search(r"(?:车型|车系|款型)?\s*(?:改成|换成|改为|更正为|纠正为|不是)", text)
        )
        condition_only_followup = bool(
            context_brand
            and has_followup_fields
            and not has_explicit_brand
            and not has_safe_alias
            and not has_identity_change_cue
        )
        if condition_only_followup:
            alias_match = None
        if alias_match:
            alias, brand, series = alias_match
            slots["brand"] = brand
            slots["series"] = series
            metadata["source"] = "deterministic_alias_pre_catalog"
            metadata["catalog_match"] = {
                "brand": brand,
                "series": series,
                "match_method": "deterministic_alias_pre_catalog",
                "matched_alias": alias,
            }
        catalog_match = (
            None
            if alias_match or condition_only_followup
            else self.catalog_index.match(text, context_brand=str(context_brand or "") or None)
        )
        if catalog_match:
            slots["brand"] = catalog_match["brand"]
            slots["series"] = catalog_match["series"]
            if catalog_match.get("inferred_trim_code"):
                slots["trim"] = catalog_match["inferred_trim_code"]
            metadata["catalog_match"] = catalog_match
            metadata["source"] = catalog_match["match_method"]
        # Alias resolution identifies the series (for example 宝马325Li ->
        # 宝马3系) but must not throw away the explicit configuration code the
        # user typed.  Recover the configuration from the first vehicle clause
        # so an exact “325Li M运动” request does not fall back to a four-item
        # trim clarification card.
        if alias_match and not slots.get("trim") and not condition_only_followup:
            vehicle_clause = re.split(r"[，,；;。]", text, maxsplit=1)[0]
            explicit_trim = re.search(
                r"(?<!\d)(\d{3,4}(?:Li|Le|L|i|e)?(?:\s*(?:M运动(?:曜夜)?|运动曜夜|运动套装|豪华套装|领先型|尊享型|旗舰型))?)",
                vehicle_clause,
                flags=re.I,
            )
            if explicit_trim:
                trim_value = self._clean_trim(explicit_trim.group(1).strip())
                if re.search(r"M运动$", trim_value, flags=re.I):
                    trim_value += "套装"
                slots["trim"] = trim_value
        if not slots["brand"]:
            normalized = text
            for wrong, right in BRAND_ALIASES.items():
                normalized = normalized.replace(wrong, right)
            city_only = any(
                re.fullmatch(
                    rf"(?:看|换成|改成|城市)?{re.escape(city)}(?:看看|行情)?",
                    normalized.strip(),
                )
                for city in COMMON_CITIES
            )
            if not city_only:
                brand_search_text = normalized
                for city in COMMON_CITIES:
                    brand_search_text = brand_search_text.replace(city, "")
                slots["brand"] = next(
                    (brand for brand in self.catalog_index.known_brands() if brand in brand_search_text),
                    None,
                )
                slots["brand"] = slots["brand"] or next(
                    (brand for brand in KNOWN_BRANDS if brand in brand_search_text),
                    None,
                )

        legacy = parse_vehicle_slots(text)
        legacy_map = {
            "model_year": "model_year",
            "trim": "trim",
            "city": "city",
            "transfer_count": "transfer_count",
            "color": "color",
            "energy_type": "energy_type",
            "mileage_wan_km": "mileage_wan_km",
        }
        for old_key, new_key in legacy_map.items():
            value = _flat(legacy.get(old_key))
            if value not in (None, ""):
                if condition_only_followup and new_key in {"model_year", "trim"}:
                    continue
                if new_key == "trim":
                    value = self._clean_trim(value)
                slots[new_key] = value
        if not slots["brand"] and not condition_only_followup:
            legacy_brand = _flat(legacy.get("brand"))
            slots["brand"] = None if legacy_brand in COMMON_CITIES else legacy_brand
        if not slots["series"] and not condition_only_followup:
            series = _flat(legacy.get("series"))
            if series:
                series = str(series)
                if slots["brand"] and series.startswith(str(slots["brand"])):
                    series = series[len(str(slots["brand"])) :]
                slots["series"] = series

        loose_year_value = None
        year_match = re.search(r"((?:19|20)\d{2}|[12]\d)\s*款", text)
        if year_match:
            raw_year = year_match.group(1)
            slots["model_year"] = int(raw_year) if len(raw_year) == 4 else 2000 + int(raw_year)
            trim_match = re.search(
                r"(?:19|20)\d{2}\s*款\s*([^，,；;。]+?)"
                r"(?=(?:[，,；;。]|(?:19|20)\d{2}\s*年|\d+(?:\.\d+)?\s*万?公里|(?:北京|上海|广州|深圳|重庆|成都|杭州|武汉|南京|苏州)(?:牌|市)?|\d+\s*(?:次)?过户|$))",
                text,
                flags=re.I,
            )
            if trim_match:
                trim_value = self._clean_trim(trim_match.group(1).strip(" ，,；;。"))
                # Everything after “2021款” is not automatically a trim: users
                # commonly repeat the brand and series there.  Strip repeated
                # identity prefixes until the first real configuration token.
                for _ in range(4):
                    before = trim_value
                    for identity_prefix in (
                        str(slots.get("brand") or ""),
                        f"{slots.get('brand') or ''}{slots.get('series') or ''}",
                        str(slots.get("series") or ""),
                    ):
                        if not identity_prefix:
                            continue
                        prefix_pattern = r"^" + r"\s*".join(
                            re.escape(part) for part in re.split(r"\s+", identity_prefix) if part
                        ) + r"\s*"
                        trim_value = re.sub(prefix_pattern, "", trim_value, count=1, flags=re.I).strip()
                    if trim_value == before:
                        break
                if trim_value:
                    slots["trim"] = trim_value
                    slots["raw_vehicle_text"] = " ".join(
                        str(part)
                        for part in (slots.get("brand"), slots.get("series"), f"{slots['model_year']}款", trim_value)
                        if part
                    )
        elif slots.get("brand") or slots.get("series"):
            # Internal users often omit “款”, e.g. “2021宝马” or “21年宝马3系”.
            # Treat a leading/standalone year beside a vehicle identity as a
            # tentative model year so the global router can ask for the missing
            # vehicle fields instead of leaving the turn in the previous module.
            loose_year = re.search(r"(?<!\d)((?:19|20)\d{2}|[12]\d)(?!\d)\s*年?", text)
            if loose_year:
                raw_year = loose_year.group(1)
                loose_year_value = int(raw_year) if len(raw_year) == 4 else 2000 + int(raw_year)
                slots["model_year"] = loose_year_value
        if not slots.get("trim"):
            # Common short trim names are often spoken before a bare year,
            # e.g. “Model Y 长续航，2023年” or “宋PLUS 冠军版，2023年4月”.
            # Preserve only explicit, bounded names; the catalog normalizer
            # remains responsible for resolving them to an exact model ID.
            short_trim = re.search(
                r"(长续航(?:全轮驱动版)?|后轮驱动版|高性能全轮驱动版|"
                r"冠军版|尊贵版|豪华版|旗舰版|智驾版|标准续航版)",
                text,
                flags=re.I,
            )
            if short_trim:
                slots["trim"] = short_trim.group(1)
        compact_text = _compact(text)
        if slots.get("brand") == "比亚迪" and slots.get("series") and "宋plus" in compact_text and re.search(r"dmi|dm-i", compact_text, flags=re.I):
            slots["series"] = "宋PLUS DM-i"
        if slots.get("brand") == "比亚迪" and str(slots.get("series") or "") == "汉" and re.search(r"汉\s*ev|汉ev", text, flags=re.I):
            slots["series"] = "汉EV"
        if slots.get("brand") == "DS" and str(slots.get("series") or "").strip() in {"7", "DS7"}:
            slots["series"] = "DS 7"
        if slots.get("brand") == "奔驰":
            compact_series = _compact(slots.get("series"))
            if compact_series in {"c200l", "c260l", "c300l"}:
                slots["series"] = "C级"
            elif compact_series in {"e200l", "e260l", "e300l", "e350l"}:
                slots["series"] = "E级"

        # Frontline staff commonly say the configuration code as part of the
        # series name ("奔驰c260l运动") and omit the word “款”. Preserve the
        # code in the trim while keeping the canonical C-Class series.
        if slots.get("brand") == "奔驰" and slots.get("series") == "C级":
            benz_c_trim = re.search(
                r"c\s*(200|260|300)\s*l\s*(皓夜运动|运动)(?:版)?(?:\s*(4matic))?",
                text,
                flags=re.I,
            )
            if benz_c_trim:
                code, edition, four_wheel = benz_c_trim.groups()
                slots["trim"] = f"C {code} L {edition}版" + (" 4MATIC" if four_wheel else "")

        # “DS7歌剧院” has one exact identity in the current catalog: 2018款
        # 45THP 歌剧院版. A following bare “19年” is the registration year,
        # not permission to invent a 2019 model-year configuration.
        if slots.get("brand") == "DS" and slots.get("series") == "DS 7" and "歌剧院" in text:
            slots["trim"] = "45THP 歌剧院版"
            if not re.search(r"(?:19|20)\d{2}\s*款|[12]\d\s*款", text):
                slots["model_year"] = 2018

        license_date = None
        for pattern in (
            r"((?:19|20)\d{2}|[12]\d)\s*(?:[-/.年])\s*(\d{1,2})(?:\s*(?:[-/.月])\s*(\d{1,2})\s*(?:日|号)?)?\s*(?:月)?\s*(?:上牌|登记|落户|初登|注册)",
            r"(?:首次)?(?:上牌|登记|落户|初登|注册)(?:时间|日期)?\s*(?:=|是|为|在|：|:)?\s*((?:19|20)\d{2}|[12]\d)\s*(?:[-/.年])\s*(\d{1,2})(?:\s*(?:[-/.月])\s*(\d{1,2})\s*(?:日|号)?)?",
        ):
            license_date = re.search(pattern, text)
            if license_date:
                break
        if license_date:
            raw_year = license_date.group(1)
            year = int(raw_year) if len(raw_year) == 4 else 2000 + int(raw_year)
            month = max(1, min(12, int(license_date.group(2))))
            day_raw = license_date.group(3)
            day = max(1, min(31, int(day_raw))) if day_raw else None
            slots["first_license_year"] = year
            slots["first_license_month"] = month
            slots["first_license_date"] = f"{year}-{month:02d}" + (f"-{day:02d}" if day else "")
            slots["reg_date"] = slots["first_license_date"]
        else:
            date_candidates = []
            for match in re.finditer(
                r"(?<!款)((?:19|20)\d{2}|[12]\d)\s*(?:年|[-/.])\s*(\d{1,2})(?:\s*月)?(?:\s*(?:[-/.])\s*(\d{1,2})|\s*(\d{1,2})\s*(?:日|号))?",
                text,
            ):
                before = text[max(0, match.start() - 4):match.start()]
                after = text[match.end():match.end() + 8]
                if re.search(r"款|年款", after):
                    continue
                if re.search(r"款\s*$", before):
                    continue
                if re.match(r"\s*(?:万|万元|元)", after) or re.search(
                    r"(?:挂牌|挂价|报价|售价|卖价|收价|客户给|客户出)\s*$",
                    before,
                ):
                    continue
                date_candidates.append(match)
            if date_candidates and (
                slots.get("brand")
                or slots.get("series")
                or slots.get("model_year")
                or re.search(r"估价|报价|多少钱|收售|收车|卖车|上牌|里程|过户", text)
            ):
                match = date_candidates[-1]
                raw_year = match.group(1)
                year = int(raw_year) if len(raw_year) == 4 else 2000 + int(raw_year)
                month = max(1, min(12, int(match.group(2))))
                day_raw = match.group(3) or match.group(4)
                day = max(1, min(31, int(day_raw))) if day_raw else None
                slots["first_license_year"] = year
                slots["first_license_month"] = month
                slots["first_license_date"] = f"{year}-{month:02d}" + (f"-{day:02d}" if day else "")
                slots["reg_date"] = slots["first_license_date"]
            if not slots.get("first_license_date"):
                license_year = None
                for pattern in (
                    r"((?:19|20)\d{2}|[12]\d)\s*年?\s*(?:上牌|登记|落户|初登|注册)",
                    r"(?:首次)?(?:上牌|登记|落户|初登|注册)(?:时间|日期)?\s*(?:=|是|为|在|：|:)?\s*((?:19|20)\d{2}|[12]\d)(?!\s*款)",
                ):
                    license_year = re.search(pattern, text)
                    if license_year:
                        break
                if license_year:
                    raw_year = license_year.group(1)
                    year = int(raw_year) if len(raw_year) == 4 else 2000 + int(raw_year)
                    slots["first_license_year"] = year
                    slots["first_license_month"] = 1
                    slots["first_license_date"] = f"{year}-01"
                    slots["reg_date"] = slots["first_license_date"]
            if not slots.get("first_license_date") and loose_year_value and re.search(
                r"估价|报价|多少钱|收售|收车|卖车|公里|过户|白色|黑色|灰色|银色|红色|蓝色|绿色|棕色|紫色|橙色|香槟色",
                text,
            ):
                slots["first_license_year"] = loose_year_value
                slots["first_license_month"] = 1
                slots["first_license_date"] = f"{loose_year_value}-01"
                slots["reg_date"] = slots["first_license_date"]

        mileage_candidates = [
            item for item in re.finditer(r"(\d+(?:\.\d+)?)\s*(万)?\s*(?:公里|km)", text, flags=re.I)
            if not _is_range_or_version_km(text, item)
        ]
        if not mileage_candidates:
            mileage_candidates = [
                item for item in re.finditer(r"(\d+(?:\.\d+)?)\s*(万)(?:多)?(?=[，,、\s]*(?:公里|白色|黑色|灰色|银色|红色|蓝色|绿色|棕色|紫色|橙色|香槟色|过户|0过户|没过户|$))", text, flags=re.I)
                if not re.search(r"万(?:元|块|以内|以上|左右)", item.group(0))
            ]
        mileage = mileage_candidates[-1] if mileage_candidates else None
        if mileage:
            number = float(mileage.group(1))
            slots["mileage_km"] = int(round(number * 10000 if mileage.group(2) else number))
            slots["mileage_wan_km"] = round(slots["mileage_km"] / 10000, 4)
        elif slots["mileage_wan_km"] is not None:
            slots["mileage_km"] = int(round(float(slots["mileage_wan_km"]) * 10000))

        target_city = None
        city_change = re.search(
            r"(?:不是|并非)\s*(" + "|".join(COMMON_CITIES) + r")\s*(?:，|,)?\s*(?:是|改成|换成)\s*(" + "|".join(COMMON_CITIES) + r")",
            text,
        )
        if city_change:
            target_city = city_change.group(2)
        else:
            city_change = re.search(
                r"(?:城市|地点|车在|按)?\s*(?:改成|换成|改为|调整到|切到)\s*(" + "|".join(COMMON_CITIES) + r")",
                text,
            )
            if city_change:
                target_city = city_change.group(1)
        if not target_city:
            for alias, city in PLATE_CITY_ALIASES.items():
                if alias in text:
                    target_city = city
                    break
        geo = resolve_city(target_city or text, COMMON_CITIES)
        if geo:
            slots["city"] = geo.city
            if geo.city == "全国":
                specific_mentions = [
                    city
                    for city in COMMON_CITIES
                    if city != "全国" and city in text
                ]
                if specific_mentions:
                    slots["city"] = min(specific_mentions, key=lambda city: text.find(city))
        color_mentions = []
        for raw, normalized in COLOR_ALIASES.items():
            if raw not in text:
                continue
            # “其他不变” means keep every other field unchanged; it must not
            # overwrite the saved vehicle color with the catch-all color.
            if raw in {"其他", "其它"} and not re.search(
                rf"(?:颜色\s*(?:是|为|改成|换成)?\s*{raw}|{raw}\s*颜色)",
                text,
            ):
                continue
            color_mentions.append((text.rfind(raw), normalized))
        if color_mentions:
            slots["color"] = max(color_mentions, key=lambda item: item[0])[1]

        for pattern, grade in (
            (r"E(?:级车况|级评定|级检测|评级|评)|(?:车况|检测|评定|评级|等级)\s*[:：]?\s*E(?:级|评)?|泡水|火烧|调表", "E"),
            (r"D(?:级车况|级评定|级检测|评级|评)|(?:车况|检测|评定|评级|等级)\s*[:：]?\s*D(?:级|评)?|重大事故|事故车|结构件事故", "D"),
            (r"C(?:级车况|级评定|级检测|评级|评)|(?:车况|检测|评定|评级|等级)\s*[:：]?\s*C(?:级|评)?|一般车况|轻微瑕疵|多处喷漆", "C"),
            (r"A(?:级车况|级评定|级检测|评级|评)|(?:车况|检测|评定|评级|等级)\s*[:：]?\s*A(?:级|评)?|精品车况|准新车况|优秀车况", "A"),
            (r"B(?:级车况|级评定|级检测|评级|评)|(?:车况|检测|评定|评级|等级)\s*[:：]?\s*B(?:级|评)?|车况良好|正常车况|无事故", "B"),
        ):
            if re.search(pattern, text, flags=re.I):
                slots["condition_group"] = grade
                slots["inspection_grade"] = grade
                slots["condition"] = "high_risk" if grade in {"D", "E"} else "minor_defect" if grade == "C" else "good"
                break

        price_bucket = re.search(
            r"(\d+(?:\.\d+)?)\s*[-~—至到]\s*(\d+(?:\.\d+)?)\s*万",
            text,
        )
        if price_bucket:
            slots["price_bucket"] = f"{price_bucket.group(1)}-{price_bucket.group(2)}万"
        else:
            under = re.search(r"(\d+(?:\.\d+)?)\s*万(?:以内|以下)", text)
            above = re.search(r"(\d+(?:\.\d+)?)\s*万(?:以上|起)", text)
            if under:
                slots["price_bucket"] = f"0-{under.group(1)}万"
            elif above:
                slots["price_bucket"] = f"{above.group(1)}万以上"

        if not slots["series"] and self.enable_qwen_fallback and self._looks_like_vehicle_text(text):
            fallback = self._qwen_json_fallback(text)
            if fallback:
                for key in slots:
                    if slots[key] in (None, "") and fallback.get(key) not in (None, ""):
                        slots[key] = fallback[key]
                metadata["source"] = "deterministic_then_qwen_json"
                metadata["fallback_used"] = True
            else:
                metadata["fallback_reason"] = "qwen_json_unavailable_or_invalid"
        if (
            re.search(r"估价|报价|多少钱|收/卖|收车|卖车|给我估|给报价", text)
            and slots.get("brand")
            and slots.get("series")
            and (slots.get("model_year") or slots.get("first_license_year"))
            and slots.get("first_license_year")
            and slots.get("city")
            and slots.get("mileage_wan_km") not in (None, "")
            and slots.get("transfer_count") not in (None, "")
            and slots.get("color")
            and not (slots.get("trim") or slots.get("standard_vehicle") or slots.get("raw_vehicle_text"))
        ):
            year = slots.get("model_year") or slots.get("first_license_year")
            slots["raw_vehicle_text"] = " ".join(
                str(value)
                for value in (slots.get("brand"), slots.get("series"), f"{year}款")
                if value not in (None, "")
            )
            slots["standard_vehicle"] = slots["raw_vehicle_text"]
        return {"slots": slots, **metadata}

    @staticmethod
    def _clean_trim(value: Any) -> str:
        text = str(value or "").strip()
        text = re.sub(
            r"^(?:(?:麻烦|请|帮我|给我)?(?:我要|我想|想要|需要|打算)?"
            r"(?:收车|收|卖车|卖|买车|买|估价|估|报价|看看)?(?:一辆|一台|一个)?\s*)+",
            "",
            text,
        )
        text = re.sub(r"^(?:改成|换成|改为|修改为|更正为|纠正为|车型改成|车系改成)\s*", "", text)
        text = re.sub(r"^(?:(?:19|20)\d{2}|[12]\d)\s*(?:款)?\s*", "", text)
        text = re.sub(r"[，,、]?\s*(?:(?:19|20)\d{2}|[12]\d)\s*年(?:\s*\d{1,2}\s*月)?\s*$", "", text)
        text = re.sub(
            r"(?:请)?(?:帮我|给我)?(?:估价|估个价|报价|报个价|估收车价|看看多少钱|多少钱|值多少钱|重新估价)+\s*$",
            "",
            text,
            flags=re.I,
        )
        return text.strip(" ，,、")

    def _looks_like_vehicle_text(self, text: str) -> bool:
        return bool(
            re.search(
                r"车|款|公里|过户|宝马|奔驰|奥迪|大众|丰田|本田|特斯拉|理想|问界|小鹏|蔚来|比亚迪",
                text,
                flags=re.I,
            )
        )

    def _qwen_json_fallback(self, text: str) -> Dict[str, Any] | None:
        prompt = (
            "只输出一个JSON对象，不得输出解释或业务动作。"
            "允许字段仅为brand,series,model_year,trim,city,mileage_km,"
            "mileage_wan_km,transfer_count,color,energy_type。未知字段填null。"
        )
        result = self.llm_client.structured_extract(prompt, {"message": text})
        parsed = extract_json_object(result.content) if result.ok else None
        if not isinstance(parsed, dict):
            return None
        allowed = set(empty_slots()) - {"price_bucket"}
        if any(key not in allowed for key in parsed):
            return None
        normalized = {key: parsed.get(key) for key in allowed}
        if normalized.get("mileage_km") is not None:
            try:
                normalized["mileage_km"] = int(float(normalized["mileage_km"]))
                normalized["mileage_wan_km"] = round(normalized["mileage_km"] / 10000, 4)
            except (TypeError, ValueError):
                return None
        return normalized
