from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .llm_client import Qwen3LocalClient, extract_json_object, load_prompt
from .geo_resolver import resolve_city
from .intent_system import parse_vehicle_slots


ROOT = Path(__file__).resolve().parents[1]
FINETUNE_DIR = ROOT / "data" / "finetune"


BRAND_ALIASES = {
    "小眯": "小米",
    "小 米": "小米",
    "问届": "问界",
    "AITO": "问界",
    "aito": "问界",
    "奔弛": "奔驰",
    "奔驰车": "奔驰",
    "宝妈": "宝马",
    "宝馬": "宝马",
    "宝马车": "宝马",
    "奥帝": "奥迪",
    "奥笛": "奥迪",
    "大重": "大众",
    "保时节": "保时捷",
    "毛豆": "特斯拉",
}

KNOWN_BRANDS = [
    "小米",
    "问界",
    "宝马",
    "奔驰",
    "奥迪",
    "大众",
    "丰田",
    "本田",
    "比亚迪",
    "特斯拉",
    "理想",
    "蔚来",
    "小鹏",
    "保时捷",
    "路虎",
    "捷豹",
    "林肯",
    "凯迪拉克",
    "英菲尼迪",
    "讴歌",
    "马自达",
    "福特",
    "雪佛兰",
    "雪铁龙",
    "标致",
    "起亚",
    "现代",
    "斯柯达",
    "MINI",
    "smart",
    "玛莎拉蒂",
    "宾利",
    "劳斯莱斯",
    "日产",
    "别克",
    "吉利",
    "领克",
    "极氪",
    "坦克",
    "捷途",
    "荣威",
    "名爵",
    "五菱",
    "宝骏",
    "长安",
    "奇瑞",
    "哈弗",
    "长城",
    "广汽传祺",
    "传祺",
    "埃安",
    "深蓝",
    "零跑",
    "阿维塔",
    "哪吒",
    "红旗",
    "雷克萨斯",
    "沃尔沃",
    "阿尔法罗密欧",
    "DS",
]

SERIES_ALIASES = {
    "毛豆3": "Model 3",
    "model3": "Model 3",
    "model 3": "Model 3",
    "modely": "Model Y",
    "model y": "Model Y",
    "su 7": "SU7",
    "s u7": "SU7",
    "su7": "SU7",
    "x 七": "X7",
    "x7": "X7",
    "奔驰c260l": "C级",
    "c260l": "C级",
    "ds7": "DS 7",
}

COLOR_MAP = {
    "珍珠白": "白色",
    "白外": "白色",
    "白色": "白色",
    "黑色": "黑色",
    "黑外": "黑色",
    "灰色": "灰色",
    "深灰": "灰色",
    "银灰": "银色",
    "银灰色": "银色",
    "银色": "银色",
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

COMMON_CITIES = [
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
]


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _slot(value: Any = None, confidence: float = 0.0, raw: Optional[str] = None, source: str = "rule") -> Dict[str, Any]:
    return {"value": value, "confidence": round(float(confidence), 4), "raw": raw, "source": source}


def chinese_to_number(text: str) -> Optional[float]:
    if not text:
        return None
    text = str(text).replace("两", "二").strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    if text.lower().endswith("w"):
        return float(text[:-1])
    if "点" in text:
        integer, decimal = text.split("点", 1)
        base = chinese_to_number(integer) or 0
        digits = "".join(str("零一二三四五六七八九".find(ch)) for ch in decimal if ch in "零一二三四五六七八九")
        return float(f"{int(base)}.{digits or '0'}")
    number_map = {ch: i for i, ch in enumerate("零一二三四五六七八九")}
    if text == "十":
        return 10
    if "十" in text:
        left, right = text.split("十", 1)
        tens = number_map.get(left, 1) if left else 1
        ones = number_map.get(right, 0) if right else 0
        return float(tens * 10 + ones)
    if len(text) == 1 and text in number_map:
        return float(number_map[text])
    return None


def _mileage_to_wan(raw: str, wan_unit: bool = False, km_unit: bool = False) -> Optional[float]:
    value = chinese_to_number(raw)
    if value is None:
        return None
    if wan_unit:
        return value
    if km_unit or value >= 1000:
        return value / 10000.0
    return value


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


class SlotExtractor:
    def __init__(self, llm_client: Optional[Qwen3LocalClient] = None) -> None:
        self.llm_client = llm_client or Qwen3LocalClient()
        self.prompt = load_prompt("prompts/intent_slot_extraction_qwen3.md")

    def _normalize_text(self, text: str) -> str:
        text = text or ""
        for wrong, right in BRAND_ALIASES.items():
            text = text.replace(wrong, right)
        for wrong, right in {"3糸": "3系", "5糸": "5系", "7糸": "7系", "三系": "3系", "五系": "5系", "七系": "7系", "M 运动": "M运动"}.items():
            text = text.replace(wrong, right)
        text = re.sub(r"^\s*(?:改成|换成|改为|修改为|更正为|纠正为|车型改成|车系改成)\s*", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def rule_extract(self, message: str, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        text = self._normalize_text(message)
        slots: Dict[str, Dict[str, Any]] = {
            key: _slot(None, 0.0, None, "rule")
            for key in [
                "brand",
                "series",
                "model_year",
                "first_license_year",
                "first_license_month",
                "city",
                "color",
                "mileage_wan_km",
                "transfer_count",
                "energy_type",
                "condition_group",
                "trim",
                "raw_vehicle_text",
                "vehicle_confirmed",
            ]
        }
        ambiguity: list[str] = []

        for brand in KNOWN_BRANDS:
            if brand in text:
                slots["brand"] = _slot(brand, 0.96, brand, "rule")
                break

        compact = text.lower().replace(" ", "")
        for alias, series in SERIES_ALIASES.items():
            if alias.lower().replace(" ", "") in compact:
                slots["series"] = _slot(series, 0.88, alias, "rule")
                if series.startswith("Model"):
                    slots["brand"] = _slot("特斯拉", 0.92, alias, "rule")
                elif series.startswith("SU7"):
                    slots["brand"] = _slot("小米", 0.92, alias, "rule")
                elif series == "C级":
                    slots["brand"] = _slot("奔驰", 0.92, alias, "rule")
                elif series == "DS 7":
                    slots["brand"] = _slot("DS", 0.92, alias, "rule")
                break

        # Common Chinese series patterns.
        series_patterns = [
            r"(宝马\s*[1357]系|宝马X\d|宝马i\d|宝马I\d)",
            r"(奔驰\s*[ACEGS]级|奔驰E\d{3}L?|奔驰C\d{3}L?)",
            r"(大众速腾|大众迈腾|大众朗逸|大众高尔夫|大众途观|大众帕萨特)",
            r"(凯美瑞|雅阁|秦PLUS|秦 plus|宋PLUS|宋 plus|问界M\d|问界 m\d|小米SU7|小米 su7)",
            r"(红旗H\d|红旗 h\d|沃尔沃XC\d+|沃尔沃 xc\d+)",
        ]
        if not slots["series"]["value"]:
            for pattern in series_patterns:
                m = re.search(pattern, text, flags=re.I)
                if m:
                    raw = re.sub(r"\s+", "", m.group(1))
                    value = raw.replace("小米su7", "小米SU7").replace("秦plus", "秦PLUS").replace("宋plus", "宋PLUS")
                    if (
                        value.startswith("宝马")
                        or value.startswith("奔驰")
                        or value.startswith("大众")
                        or value.startswith("问界")
                        or value.startswith("小米")
                        or value.startswith("红旗")
                        or value.startswith("沃尔沃")
                    ):
                        brand = next((b for b in KNOWN_BRANDS if value.startswith(b)), slots["brand"]["value"])
                        if brand:
                            slots["brand"] = _slot(brand, max(slots["brand"]["confidence"], 0.9), brand, "rule")
                            value = value[len(brand) :]
                    slots["series"] = _slot(value, 0.9, m.group(1), "rule")
                    break

        year_model = re.search(r"((?:19|20)\d{2}|[12]\d)\s*款", text)
        if year_model:
            raw = year_model.group(1)
            value = int(raw) if len(raw) == 4 else 2000 + int(raw)
            slots["model_year"] = _slot(value, 0.96, year_model.group(0), "rule")
            trim_match = re.search(
                r"(?:19|20)\d{2}\s*款\s*([^，,；;。]+?)"
                r"(?=(?:[，,；;。]|(?:19|20)\d{2}\s*年|\d+(?:\.\d+)?\s*万?公里|(?:北京|上海|广州|深圳|重庆|成都|杭州|武汉|南京|苏州)(?:牌|市)?|\d+\s*(?:次)?过户|$))",
                text,
                flags=re.I,
            )
            if trim_match:
                trim_value = trim_match.group(1).strip(" ，,；;。")
                for _ in range(4):
                    before = trim_value
                    for identity_prefix in (
                        str(slots["brand"]["value"] or ""),
                        f"{slots['brand']['value'] or ''}{slots['series']['value'] or ''}",
                        str(slots["series"]["value"] or ""),
                    ):
                        if not identity_prefix:
                            continue
                        prefix_pattern = r"^" + r"\s*".join(
                            re.escape(part)
                            for part in re.split(r"\s+", identity_prefix)
                            if part
                        ) + r"\s*"
                        trim_value = re.sub(
                            prefix_pattern, "", trim_value, count=1, flags=re.I
                        ).strip()
                    if trim_value == before:
                        break
                trim_value = re.sub(
                    r"(?:请)?(?:帮我|给我)?(?:估价|估个价|报价|报个价|估收车价|看看多少钱|多少钱|值多少钱|重新估价)+\s*$",
                    "",
                    trim_value,
                    flags=re.I,
                ).strip(" ，,、")
                if trim_value and not re.fullmatch(r"(?:上牌|登记|公里|过户|白色|黑色|灰色|银色|红色|蓝色|绿色)", trim_value):
                    slots["trim"] = _slot(trim_value, 0.96, trim_match.group(1), "rule")
                    brand_value = slots["brand"]["value"] or ""
                    series_value = slots["series"]["value"] or ""
                    raw_vehicle = " ".join(str(part) for part in (brand_value, series_value, f"{value}款", trim_value) if part)
                    slots["raw_vehicle_text"] = _slot(raw_vehicle, 0.95, raw_vehicle, "rule")
                    slots["vehicle_confirmed"] = _slot(True, 0.96, trim_match.group(1), "rule")

        leading_vehicle_year = re.search(
            r"^\s*((?:19|20)\d{2}|[12]\d)\s*(?=(?:款)?\s*(?:宝马|奔驰|奥迪|大众|丰田|本田|别克|特斯拉|比亚迪|问界|小米|理想|蔚来|小鹏|保时捷|路虎|五菱|哈弗|日产|吉利|长安|奇瑞|红旗|雷克萨斯|沃尔沃|AITO|凯美瑞|雅阁|朗逸|轩逸|速腾|GL8))",
            text,
            flags=re.I,
        )
        if leading_vehicle_year and not year_model:
            raw = leading_vehicle_year.group(1)
            value = int(raw) if len(raw) == 4 else 2000 + int(raw)
            slots["model_year"] = _slot(value, 0.9, raw, "rule")

        license_date = re.search(
            r"((?:19|20)\d{2}|[12]\d)\s*(?:[-/.年])\s*(\d{1,2})(?:\s*(?:[-/.月])\s*(\d{1,2})\s*(?:日|号)?)?\s*(?:月)?\s*(?:上牌|登记|落户)",
            text,
        )
        license_year = re.search(r"((?:19|20)\d{2}|[12]\d)\s*年(?:\s*\d{1,2}\s*月)?\s*(?:上牌|登记|落户)", text)
        if license_date:
            raw = license_date.group(1)
            value = int(raw) if len(raw) == 4 else 2000 + int(raw)
            month = max(1, min(12, int(license_date.group(2))))
            day_raw = license_date.group(3)
            day = max(1, min(31, int(day_raw))) if day_raw else None
            date_value = f"{value}-{month:02d}" + (f"-{day:02d}" if day else "")
            slots["first_license_year"] = _slot(value, 0.98, license_date.group(0), "rule")
            slots["first_license_month"] = _slot(month, 0.98, license_date.group(2), "rule")
            slots["first_license_date"] = _slot(date_value, 0.98, license_date.group(0), "rule")
        elif license_year:
            raw = license_year.group(1)
            value = int(raw) if len(raw) == 4 else 2000 + int(raw)
            slots["first_license_year"] = _slot(value, 0.96, license_year.group(0), "rule")
            month_match = re.search(r"年\s*(\d{1,2})\s*月", license_year.group(0))
            if month_match:
                month = max(1, min(12, int(month_match.group(1))))
                slots["first_license_month"] = _slot(month, 0.96, month_match.group(1), "rule")

        # Follow-up turns often contain only "2021年9月" after the assistant
        # asked for上牌时间. Treat a standalone yyyy年m月 as first-license date
        # when conversation state exists, instead of sending the user to generic
        # fallback chat.
        state_slots = (state or {}).get("current_slots") or {}
        has_vehicle_context = bool(state_slots or (state or {}).get("current_vehicle_match") or (state or {}).get("last_missing_fields"))
        standalone_reg_date = re.fullmatch(r"\s*((?:19|20)\d{2}|[12]\d)\s*年\s*(\d{1,2})\s*月\s*", text)
        if standalone_reg_date and not year_model and not license_year and has_vehicle_context:
            raw_year = standalone_reg_date.group(1)
            year_value = int(raw_year) if len(raw_year) == 4 else 2000 + int(raw_year)
            month_value = max(1, min(12, int(standalone_reg_date.group(2))))
            slots["first_license_year"] = _slot(year_value, 0.96, standalone_reg_date.group(0), "rule")
            slots["first_license_month"] = _slot(month_value, 0.96, standalone_reg_date.group(2), "rule")

        vague_year = re.search(r"(?<!款)((?:19|20)\d{2}|[12]\d)\s*年(?=.*(?:宝马|奔驰|大众|小米|问界|凯美瑞|雅阁|速腾|X7|5系|3系|SU7))", text)
        if vague_year and not year_model and not license_year and not leading_vehicle_year:
            raw = vague_year.group(1)
            value = int(raw) if len(raw) == 4 else 2000 + int(raw)
            slots["model_year"] = _slot(value, 0.45, raw, "rule")
            slots["first_license_year"] = _slot(value, 0.45, raw, "rule")
            ambiguity.append("YEAR_AMBIGUOUS_MODEL_OR_LICENSE")

        standalone_year = re.search(r"\b((?:19|20)\d{2})\b", text)
        if standalone_year and not year_model and not license_year and not vague_year and not leading_vehicle_year and (slots["brand"]["value"] or slots["series"]["value"]):
            value = int(standalone_year.group(1))
            slots["model_year"] = _slot(value, 0.5, standalone_year.group(1), "rule")
            slots["first_license_year"] = _slot(value, 0.5, standalone_year.group(1), "rule")
            ambiguity.append("YEAR_AMBIGUOUS_MODEL_OR_LICENSE")

        mileage_matches = list(re.finditer(r"([0-9]+(?:\.[0-9]+)?|[零一二两三四五六七八九十点]+)\s*(万|w)?\s*(公里|km)?", text, flags=re.I))
        mileage_context = bool(re.search(r"跑|里程|行驶|开了|公里数", text))
        price_context = bool(re.search(r"客户|客人|报价|还价|挂牌|挂|上架|展板|对外价|售价|卖价|能不能卖|高不高|合适", text))
        mileage_candidates = [
            item for item in mileage_matches
            if (
                "公里" in item.group(0)
                or "km" in item.group(0).lower()
                or (mileage_context and not price_context)
            )
            and not _is_range_or_version_km(text, item)
        ]
        m = mileage_candidates[-1] if mileage_candidates else None
        if m:
            wan = _mileage_to_wan(m.group(1), wan_unit=bool(m.group(2)), km_unit=bool(m.group(3)))
            if wan is not None:
                slots["mileage_wan_km"] = _slot(round(wan, 2), 0.94, m.group(0), "rule")

        if re.search(r"(一手车|没过户|无过户|0次过户|零次过户)", text):
            slots["transfer_count"] = _slot(0, 0.96, "一手/无过户", "rule")
        else:
            tm = re.search(r"(?:过了?|过户|转手)\s*([0-9零一二两三四五六七八九十]+)\s*次?|([0-9零一二两三四五六七八九十]+)\s*(?:手|次过户)", text)
            if tm:
                raw = tm.group(1) or tm.group(2)
                value = chinese_to_number(raw)
                if value is not None:
                    # "2手" usually means one transfer has happened less reliably.
                    transfer = int(value if "过户" in tm.group(0) or "次" in tm.group(0) else max(value - 1, 0))
                    slots["transfer_count"] = _slot(transfer, 0.86, tm.group(0), "rule")

        color_mentions = []
        for raw, normalized in COLOR_MAP.items():
            if raw not in text:
                continue
            if raw in {"其他", "其它"} and not re.search(
                rf"(?:颜色\s*(?:是|为|改成|换成)?\s*{raw}|{raw}\s*颜色)",
                text,
            ):
                continue
            color_mentions.append((text.rfind(raw), raw, normalized))
        if color_mentions:
            _, raw, normalized = max(color_mentions, key=lambda item: item[0])
            slots["color"] = _slot(normalized, 0.92, raw, "rule")

        condition_grade = None
        condition_raw = None
        for pattern, grade in (
            (r"E(?:级车况|级评定|级检测|评级|评)|(?:^|[，,、;；\s])E级(?!车)(?=$|[，,、。;；\s])|(?:车况|检测|评定|评级|等级)\s*[:：]?\s*E(?:级|评)?|泡水|火烧|调表", "E"),
            (r"D(?:级车况|级评定|级检测|评级|评)|(?:^|[，,、;；\s])D级(?!车)(?=$|[，,、。;；\s])|(?:车况|检测|评定|评级|等级)\s*[:：]?\s*D(?:级|评)?|重大事故|事故车|结构件事故", "D"),
            (r"C(?:级车况|级评定|级检测|评级|评)|(?:^|[，,、;；\s])C级(?!车)(?=$|[，,、。;；\s])|(?:车况|检测|评定|评级|等级)\s*[:：]?\s*C(?:级|评)?|一般车况|轻微瑕疵|多处喷漆", "C"),
            (r"A(?:级车况|级评定|级检测|评级|评)|(?:^|[，,、;；\s])A级(?!车)(?=$|[，,、。;；\s])|(?:车况|检测|评定|评级|等级)\s*[:：]?\s*A(?:级|评)?|精品车况|准新车况|优秀车况", "A"),
            (r"B(?:级车况|级评定|级检测|评级|评)|(?:^|[，,、;；\s])B级(?!车)(?=$|[，,、。;；\s])|(?:车况|检测|评定|评级|等级)\s*[:：]?\s*B(?:级|评)?|车况良好|正常车况|无事故", "B"),
        ):
            condition_match = re.search(pattern, text, flags=re.I)
            if condition_match:
                condition_grade = grade
                condition_raw = condition_match.group(0)
                break
        if condition_grade:
            slots["condition_group"] = _slot(condition_grade, 0.96, condition_raw, "rule")

        benz_c_trim = re.search(
            r"c\s*(200|260|300)\s*l\s*(皓夜运动|运动)(?:版)?(?:\s*(4matic))?",
            text,
            flags=re.I,
        )
        if slots["brand"]["value"] == "奔驰" and slots["series"]["value"] == "C级" and benz_c_trim:
            code, edition, four_wheel = benz_c_trim.groups()
            trim = f"C {code} L {edition}版" + (" 4MATIC" if four_wheel else "")
            slots["trim"] = _slot(trim, 0.98, benz_c_trim.group(0), "rule")
            slots["vehicle_confirmed"] = _slot(True, 0.98, benz_c_trim.group(0), "rule")
        if slots["brand"]["value"] == "DS" and slots["series"]["value"] == "DS 7" and "歌剧院" in text:
            slots["trim"] = _slot("45THP 歌剧院版", 0.98, "歌剧院", "rule")
            slots["vehicle_confirmed"] = _slot(True, 0.98, "歌剧院", "rule")

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
        geo = resolve_city(target_city or text, COMMON_CITIES)
        if geo:
            slots["city"] = _slot(geo.city, geo.confidence, geo.matched_text, f"geo:{geo.reason}")

        if re.search(r"(纯电|EV|电动|Model|eDrive|SU7)", text, flags=re.I):
            slots["energy_type"] = _slot("EV", 0.75, "新能源词", "rule")
        elif re.search(r"(DM-i|DMp|插混|PHEV)", text, flags=re.I):
            slots["energy_type"] = _slot("PHEV", 0.8, "插混词", "rule")
        elif "混动" in text:
            slots["energy_type"] = _slot("HEV", 0.7, "混动", "rule")

        deterministic_slots = parse_vehicle_slots(text)
        for key, det_slot in deterministic_slots.items():
            if key not in slots:
                slots[key] = det_slot
                continue
            current = slots.get(key) or {}
            current_value = current.get("value") if isinstance(current, dict) else current
            current_conf = float(current.get("confidence") or 0) if isinstance(current, dict) else 0
            det_value = det_slot.get("value") if isinstance(det_slot, dict) else det_slot
            det_conf = float(det_slot.get("confidence") or 0) if isinstance(det_slot, dict) else 0
            if key == "mileage_wan_km" and current_value not in (None, ""):
                continue
            if key == "city" and current_value not in (None, ""):
                continue
            if key == "color" and current_value not in (None, ""):
                continue
            if key in {"brand", "series"} and current_value not in (None, ""):
                continue
            if det_value not in (None, "") and (current_value in (None, "") or det_conf >= current_conf):
                slots[key] = det_slot

        return {"slots": slots, "ambiguity": ambiguity}

    def llm_extract(self, message: str, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {"user_message": message, "conversation_state": state or {}}
        result = self.llm_client.structured_extract(self.prompt, payload)
        parsed = extract_json_object(result.content) if result.ok else None
        if parsed is None:
            return {
                "llm_output": {},
                "fallback_used": True,
                "fallback_reason": result.fallback_reason or "invalid_json_or_llm_unavailable",
                "llm_model": result.model or self.llm_client.model,
            }
        return {
            "llm_output": parsed,
            "fallback_used": False,
            "fallback_reason": "",
            "llm_model": result.model,
        }

    def _merge_slots(self, rule_slots: Dict[str, Dict[str, Any]], llm_slots: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        merged = {k: dict(v) for k, v in rule_slots.items()}
        llm_slots = llm_slots or {}
        for key, llm_slot in llm_slots.items():
            if not isinstance(llm_slot, dict):
                continue
            if key not in merged:
                merged[key] = _slot(None, 0.0, None, "rule")
            llm_value = llm_slot.get("value")
            llm_conf = float(llm_slot.get("confidence") or 0)
            if merged[key].get("value") is None and llm_value is not None and llm_conf >= 0.45:
                merged[key] = {
                    "value": llm_value,
                    "confidence": round(llm_conf, 4),
                    "raw": llm_slot.get("raw"),
                    "source": "llm",
                }
            elif llm_value is not None and llm_conf > float(merged[key].get("confidence") or 0) + 0.2:
                merged[key] = {
                    "value": llm_value,
                    "confidence": round(llm_conf, 4),
                    "raw": llm_slot.get("raw"),
                    "source": "llm",
                }
        return merged

    def extract(self, message: str, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rule = self.rule_extract(message, state)
        consult_llm = self._should_consult_llm(message, rule, state or {})
        llm = self.llm_extract(message, state) if consult_llm else {
            "llm_output": {},
            "fallback_used": False,
            "fallback_reason": "adaptive_slot_llm_skipped",
            "llm_model": "",
        }
        llm_output = llm.get("llm_output") or {}
        merged = self._merge_slots(rule["slots"], llm_output.get("slots") or {})
        payload = {
            "user_message": message,
            "conversation_state": state or {},
            "llm_output": llm_output,
            "validated_output": {"slots": merged, "ambiguity": rule.get("ambiguity", [])},
            "final_action": "",
            "human_correction": {},
            "error_type": "llm_fallback" if llm.get("fallback_used") else "",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        _append_jsonl(FINETUNE_DIR / "intent_slot_sft_candidates.jsonl", payload)
        if llm.get("fallback_used"):
            _append_jsonl(FINETUNE_DIR / "hard_negative_cases.jsonl", payload)
        return {
            "slots": merged,
            "ambiguity": rule.get("ambiguity", []),
            "llm_output": llm_output,
            "fallback_used": bool(llm.get("fallback_used")),
            "fallback_reason": llm.get("fallback_reason", ""),
            "llm_model": llm.get("llm_model", ""),
            "llm_attempted": consult_llm,
        }

    @staticmethod
    def _should_consult_llm(message: str, rule: Dict[str, Any], state: Dict[str, Any]) -> bool:
        mode = os.environ.get("SLOT_LLM_MODE", "adaptive").strip().lower()
        if mode in {"always", "force", "true", "1"}:
            return True
        if mode in {"never", "off", "false", "0", "disabled"}:
            return False
        text = str(message or "").strip()
        if not text:
            return False
        explicit_pricing = bool(
            re.search(
                r"估价|估一下|估个价|估值|报价|多少钱|收车价|收多少钱|多少钱收|卖多少钱|售车价|建议售价|值多少|"
                r"上牌|里程|公里|过户|颜色|改成|换成|再算",
                text,
            )
        )
        non_slot_business_question = bool(
            re.search(
                r"选品|榜单|排名|第几|推荐名单|值得收|适合收|风险车系|机会车系|机会分|选品分|"
                r"评分|排序|算法|公式|DSI|回测|baseline|日报|政策|数据来源|证据.*选品",
                text,
                flags=re.I,
            )
        )
        if non_slot_business_question and not explicit_pricing:
            return False
        slots = rule.get("slots") or {}
        values = {
            key: (value.get("value") if isinstance(value, dict) else value)
            for key, value in slots.items()
        }
        identity_count = sum(values.get(key) not in (None, "") for key in ("brand", "series", "standard_vehicle", "trim"))
        measure_count = sum(
            values.get(key) not in (None, "")
            for key in ("first_license_date", "first_license_year", "mileage_wan_km", "city", "transfer_count", "color")
        )
        if rule.get("ambiguity"):
            return True
        if state.get("current_pricing_result") and (identity_count or measure_count or re.search(r"改成|换成|再算|重新估", text)):
            return False
        if explicit_pricing and identity_count == 0:
            return True
        if explicit_pricing and identity_count <= 1 and measure_count <= 1 and re.search(r"[A-Za-z]{2,}|\d{2,}[A-Za-z]", text):
            return True
        return False
