from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Tuple

from .geo_resolver import resolve_city

BUY_CAR_INTENT = "BUY_CAR_INTENT"
SELL_CAR_VALUATION_INTENT = "SELL_CAR_VALUATION_INTENT"
VEHICLE_INFO_ADD = "VEHICLE_INFO_ADD"
VEHICLE_INFO_UPDATE = "VEHICLE_INFO_UPDATE"
VEHICLE_CONFIRM = "VEHICLE_CONFIRM"
PRICE_QUOTE_REQUEST = "PRICE_QUOTE_REQUEST"
PRICE_EXPLANATION_REQUEST = "PRICE_EXPLANATION_REQUEST"
PRICE_FEEDBACK_CLARIFICATION = "PRICE_FEEDBACK_CLARIFICATION"
CANDIDATE_EVIDENCE_REQUEST = "CANDIDATE_EVIDENCE_REQUEST"
WHY_LOW_CONFIDENCE = "WHY_LOW_CONFIDENCE"
HISTORY_QUOTE_REFERENCE = "HISTORY_QUOTE_REFERENCE"
PRICE_ADJUSTMENT_INTENT = "PRICE_ADJUSTMENT_INTENT"
DAILY_REPORT_READ_INTENT = "DAILY_REPORT_READ_INTENT"
REPORT_DETAIL_QUESTION = "REPORT_DETAIL_QUESTION"
RESET_VEHICLE = "RESET_VEHICLE"
OUT_OF_SCOPE = "OUT_OF_SCOPE"
UNKNOWN_OR_INCOMPLETE = "UNKNOWN_OR_INCOMPLETE"

VALUATION_INTENTS = {SELL_CAR_VALUATION_INTENT, VEHICLE_INFO_ADD, VEHICLE_INFO_UPDATE, VEHICLE_CONFIRM, PRICE_QUOTE_REQUEST}
NON_VALUATION_INTENTS = {BUY_CAR_INTENT, PRICE_ADJUSTMENT_INTENT, DAILY_REPORT_READ_INTENT, REPORT_DETAIL_QUESTION, RESET_VEHICLE, OUT_OF_SCOPE}
EXPLANATION_INTENTS = {
    PRICE_EXPLANATION_REQUEST,
    PRICE_FEEDBACK_CLARIFICATION,
    CANDIDATE_EVIDENCE_REQUEST,
    WHY_LOW_CONFIDENCE,
    HISTORY_QUOTE_REFERENCE,
    "FEEDBACK_INACCURATE",
    "FEEDBACK_PRICE_TOO_HIGH",
    "FEEDBACK_PRICE_TOO_LOW",
}

KNOWN_BRANDS = [
    "小米", "问界", "宝马", "奔驰", "奥迪", "大众", "丰田", "本田", "比亚迪", "特斯拉", "理想", "蔚来", "小鹏", "保时捷", "路虎", "日产", "别克", "吉利", "长安", "奇瑞", "哈弗", "红旗", "雷克萨斯", "沃尔沃", "五菱", "极氪", "AITO",
]
COMMON_CITIES = [
    "北京", "上海", "广州", "深圳", "重庆", "成都", "杭州", "苏州", "南京", "武汉", "西安", "郑州", "天津", "长沙", "青岛", "宁波", "合肥", "佛山", "东莞", "厦门", "昆明", "济南", "沈阳", "大连", "无锡", "温州", "南通", "常州", "太原", "洛阳", "台州", "唐山", "长春", "哈尔滨", "石家庄", "南昌", "福州", "南宁", "贵阳", "兰州", "乌鲁木齐", "呼和浩特", "海口", "银川", "西宁", "拉萨", "徐州", "泉州", "绍兴", "嘉兴", "金华", "烟台", "潍坊", "临沂", "南阳", "宜昌", "襄阳", "珠海", "中山", "惠州", "江门", "保定", "廊坊", "邯郸", "芜湖", "赣州", "绵阳", "全国",
]
COLOR_MAP = {
    "珍珠白": "白色", "白外": "白色", "白色": "白色", "白": "白色",
    "黑色": "黑色", "黑外": "黑色", "黑": "黑色",
    "灰色": "灰色", "深灰": "灰色", "银灰": "银色", "银色": "银色",
    "红色": "红色", "蓝色": "蓝色", "绿色": "绿色", "棕色": "棕色", "黄色": "黄色", "紫色": "紫色", "香槟": "香槟色",
}
SERIES_PATTERNS = [
    r"宝马\s*(?:宝马)?\s*(?:[1357]系|X\d|x\d|i\d|I\d)",
    r"奔驰\s*(?:奔驰)?\s*(?:[ACEGS]级|A\d{3}L?|C\d{3}L?|E\d{3}L?|GL[ACEBKS]?|S\d{3}L?)",
    r"奥迪\s*(?:奥迪)?\s*(?:A\dL?|Q\dL?|Q\d|RS\d|S\d)",
    r"大众\s*(?:速腾|迈腾|朗逸|高尔夫|途观L?|帕萨特|探岳)",
    r"丰田\s*(?:凯美瑞|卡罗拉|亚洲龙|汉兰达|皇冠|RAV4荣放)",
    r"本田\s*(?:雅阁|思域|CR-V|皓影|飞度)",
    r"别克\s*(?:GL8|英朗|君威|君越)",
    r"哈弗\s*(?:H6|大狗|猛龙)",
    r"红旗\s*(?:H5|H6|HS5|HS7)",
    r"沃尔沃\s*(?:XC40|XC60|XC90|S60|S90)",
    r"五菱\s*(?:宏光MINIEV|缤果|星光)",
    r"特斯拉\s*(?:Model\s*[3YXS]|毛豆\s*[3Y])",
    r"问界\s*M\d",
    r"小米\s*SU7",
    r"凯美瑞|卡罗拉|雅阁|朗逸|轩逸|速腾|高尔夫|哈弗H6|红旗H5|沃尔沃XC60|GL8|英朗|君威|宝马3系|宝马5系|奔驰C级|奔驰E级|奥迪Q5L|宝马X3|五菱宏光MINIEV",
]

FIELD_ALIASES = {
    "mileage_wan_km": "里程",
    "city": "城市",
    "transfer_count": "过户次数",
    "color": "颜色",
    "trim": "具体款型/配置",
    "model_year": "年款",
    "series": "车系",
    "brand": "品牌",
}


def normalize_text(text: str) -> str:
    text = str(text or "")
    replacements = {
        "奔弛": "奔驰", "奔驰车": "奔驰", "宝妈": "宝马", "宝馬": "宝马", "宝马车": "宝马",
        "奥帝": "奥迪", "奥笛": "奥迪", "小眯": "小米", "小 米": "小米", "问届": "问界",
        "凌志": "雷克萨斯", "路虎揽胜": "路虎 揽胜", "毛豆": "Model",
        "3糸": "3系", "5糸": "5系", "7糸": "7系", "三系": "3系", "五系": "5系", "七系": "7系",
        "li": "Li", "LI": "Li", "m运动": "M运动", "M 运动": "M运动",
        "，": ",", "。": ",", "、": ","
    }
    for wrong, right in replacements.items():
        text = text.replace(wrong, right)
    text = re.sub(r"^\s*(?:改成|换成|改为|修改为|更正为|纠正为|车型改成|车系改成)\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


def compact_text(text: str) -> str:
    return re.sub(r"[\s,，。._/()（）·・\-]+", "", str(text or "")).lower()


def chinese_to_number(text: str) -> float | None:
    if not text:
        return None
    text = str(text).replace("两", "二").strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    number_map = {ch: i for i, ch in enumerate("零一二三四五六七八九")}
    if "点" in text:
        left, right = text.split("点", 1)
        base = chinese_to_number(left) or 0
        digits = "".join(str(number_map.get(ch, "")) for ch in right)
        return float(f"{int(base)}.{digits or '0'}")
    if text == "十":
        return 10.0
    if "十" in text:
        left, right = text.split("十", 1)
        tens = number_map.get(left, 1) if left else 1
        ones = number_map.get(right, 0) if right else 0
        return float(tens * 10 + ones)
    if len(text) == 1 and text in number_map:
        return float(number_map[text])
    return None


def _slot(value: Any, confidence: float = 1.0, raw: str | None = None, source: str = "system_rule") -> Dict[str, Any]:
    return {"value": value, "confidence": round(float(confidence), 4), "raw": raw, "source": source}


def _clean_series(raw: str, brand: str | None) -> str:
    value = re.sub(r"\s+", "", str(raw or ""))
    if brand and value.startswith(brand):
        value = value[len(brand):]
    if brand == "宝马" and re.fullmatch(r"[1357]系", value):
        return f"宝马{value}"
    if brand == "奔驰" and re.fullmatch(r"[ACEGS]级", value, flags=re.I):
        return f"奔驰{value.upper()}"
    if brand == "奥迪" and re.fullmatch(r"[AQRS]\dL?", value, flags=re.I):
        return f"奥迪{value.upper()}"
    if brand and not value.startswith(brand) and value in {"X3", "X5", "X7"}:
        return f"{brand}{value}"
    return value


def extract_series(text: str, brand: str | None) -> Tuple[str | None, str | None]:
    for pattern in SERIES_PATTERNS:
        m = re.search(pattern, text, flags=re.I)
        if m:
            raw = m.group(0)
            detected_brand = brand or next((b for b in KNOWN_BRANDS if raw.startswith(b)), None)
            return _clean_series(raw, detected_brand), raw
    return None, None


def extract_trim(text: str, brand: str | None, series: str | None, model_year: int | None) -> Tuple[str | None, float]:
    if not text or not series:
        return None, 0.0
    work = normalize_text(text)
    # Remove non-trim facts first.
    work = re.split(r"(?:\d+(?:\.\d+)?\s*万?\s*(?:公里|km)|[一二两三四五六七八九十点]+万?\s*公里|北京|上海|广州|深圳|重庆|成都|杭州|苏州|南京|武汉|一次过户|二次过户|三次过户|过户|白色|黑色|灰色|银色|红色|蓝色|绿色)", work, maxsplit=1)[0]
    if model_year:
        work = re.sub(rf"{model_year}\s*(?:款)?", "", work)
    if brand:
        work = re.sub(re.escape(brand), "", work, count=2)
    series_variants = {series, series.replace(str(brand or ""), "")}
    for sv in sorted(series_variants, key=len, reverse=True):
        if sv:
            work = re.sub(re.escape(sv), "", work, count=1)
    work = re.sub(r"^[,，、\s]+|[,，、\s]+$", "", work)
    work = re.sub(r"\s+", " ", work).strip()
    work = re.sub(r"^(?:(?:19|20)\d{2}|[12]\d)\s*(?:款)?\s*", "", work)
    if not work:
        return None, 0.0
    trim_tokens = ["改款", "二次改款", "Li", "i", "M运动", "曜夜", "豪华", "尊享", "领先", "运动", "时尚", "TFSI", "xDrive", "双擎", "DM", "EV", "km", "续航", "版", "型", "套装", "GVP", "HG", "HS"]
    has_trim_token = any(token.lower() in work.lower() for token in trim_tokens) or bool(re.search(r"\d{2,3}\s*(?:Li|i|L|TFSI|km|KM)", work, flags=re.I))
    if has_trim_token and len(compact_text(work)) >= 3:
        return work, 0.94
    return None, 0.0


def parse_vehicle_slots(message: str) -> Dict[str, Dict[str, Any]]:
    text = normalize_text(message)
    slots: Dict[str, Dict[str, Any]] = {}
    brand = next((b for b in KNOWN_BRANDS if b and b in text), None)
    if brand:
        slots["brand"] = _slot("问界" if brand == "AITO" else brand, 0.96, brand)
    series, raw_series = extract_series(text, slots.get("brand", {}).get("value") if slots.get("brand") else brand)
    if series:
        slots["series"] = _slot(series, 0.94, raw_series)
        if not slots.get("brand"):
            derived = next((b for b in KNOWN_BRANDS if series.startswith(b)), None)
            if derived:
                slots["brand"] = _slot(derived, 0.92, derived)
    ym = re.search(r"((?:19|20)\d{2}|[12]\d)\s*款", text)
    model_year = None
    if ym:
        raw = ym.group(1)
        model_year = int(raw) if len(raw) == 4 else 2000 + int(raw)
        slots["model_year"] = _slot(model_year, 0.96, ym.group(0))
    trim, trim_conf = extract_trim(text, slots.get("brand", {}).get("value"), slots.get("series", {}).get("value"), model_year)
    if trim:
        slots["trim"] = _slot(trim, trim_conf, trim)
        slots["vehicle_confirmed"] = _slot(True, 0.9, trim)
        slots["raw_vehicle_text"] = _slot(text, 0.9, text)
    mm = re.search(r"([0-9]+(?:\.[0-9]+)?|[零一二两三四五六七八九十点]+)\s*(万|w)?\s*(公里|km)", text, flags=re.I)
    if mm:
        value = chinese_to_number(mm.group(1))
        if value is not None:
            wan = value if mm.group(2) else value / 10000.0 if value >= 1000 else value
            slots["mileage_wan_km"] = _slot(round(float(wan), 2), 0.96, mm.group(0))
    elif re.search(r"(?:里程|跑了|行驶|开了)\s*([0-9]+(?:\.[0-9]+)?|[零一二两三四五六七八九十点]+)\s*万?", text):
        m = re.search(r"(?:里程|跑了|行驶|开了)\s*([0-9]+(?:\.[0-9]+)?|[零一二两三四五六七八九十点]+)\s*万?", text)
        value = chinese_to_number(m.group(1)) if m else None
        if value is not None:
            slots["mileage_wan_km"] = _slot(round(float(value), 2), 0.9, m.group(0))
    if re.search(r"(一手车|没过户|无过户|0次过户|零次过户)", text):
        slots["transfer_count"] = _slot(0, 0.96, "无过户")
    else:
        tm = re.search(r"([0-9零一二两三四五六七八九十]+)\s*次?\s*(?:过户|转手)|(?:过户|转手)(?:了)?\s*([0-9零一二两三四五六七八九十]+)\s*次?", text)
        if tm:
            raw = tm.group(1) or tm.group(2)
            value = chinese_to_number(raw)
            if value is not None:
                slots["transfer_count"] = _slot(int(value), 0.96, tm.group(0))
    for raw, color in COLOR_MAP.items():
        if raw in text:
            slots["color"] = _slot(color, 0.92, raw)
            break
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
        slots["city"] = _slot(geo.city, geo.confidence, geo.matched_text)
    if re.search(r"纯电|BEV|EV|电动", text, flags=re.I):
        slots["energy_type"] = _slot("BEV", 0.8, "新能源词")
    elif re.search(r"插混|PHEV|DM-i|DMp", text, flags=re.I):
        slots["energy_type"] = _slot("PHEV", 0.8, "插混词")
    elif re.search(r"增程|EREV", text, flags=re.I):
        slots["energy_type"] = _slot("EREV", 0.8, "增程词")
    elif re.search(r"双擎|油电混动|HEV", text, flags=re.I):
        slots["energy_type"] = _slot("HEV", 0.76, "混动词")
    elif slots.get("brand") and re.search(r"宝马|奔驰|奥迪|大众|丰田|本田|别克", str(slots.get("brand", {}).get("value"))):
        slots.setdefault("energy_type", _slot("ICE", 0.58, "brand_default_fuel"))
    return slots


def flat_slot_value(slots: Dict[str, Any], key: str) -> Any:
    value = (slots or {}).get(key)
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def _has_any_slot(slots: Dict[str, Any], keys: Iterable[str]) -> bool:
    return any(flat_slot_value(slots, key) not in (None, "") for key in keys)


def validate_vehicle_slots(slots: Dict[str, Any], *, require_trim: bool = True, task: str = "C2B") -> List[str]:
    missing: List[str] = []
    for field in ["brand", "series", "model_year"]:
        if flat_slot_value(slots, field) in (None, ""):
            missing.append(field)
    if require_trim and flat_slot_value(slots, "trim") in (None, ""):
        missing.append("trim")
    for field in ["mileage_wan_km", "city", "transfer_count", "color"]:
        if flat_slot_value(slots, field) in (None, ""):
            missing.append(field)
    return missing


def classify_intent(message: str, slots: Dict[str, Any] | None = None, state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    text = normalize_text(message)
    slots = slots or parse_vehicle_slots(text)
    state = state or {}
    has_vehicle_hint = _has_any_slot(slots, ["brand", "series", "model_year", "trim", "mileage_wan_km", "city", "transfer_count", "color"])
    has_quote = bool(state.get("active_quote_id") or state.get("current_pricing_result") or state.get("last_price_result"))
    has_report_context = bool(state.get("last_daily_report_context") or state.get("last_daily_report_id"))

    if re.search(r"重新开始|换一辆车|清空刚才|不估这辆|重置", text):
        return _intent(RESET_VEHICLE, "NONE", 0.98, "用户要求重置当前车辆")
    if re.search(r"日报|行情日报|今天行情|这周.*行情|昨天.*波动|价格波动最大", text):
        return _intent(DAILY_REPORT_READ_INTENT, "REPORT", 0.96, "日报/行情报告阅读")
    if has_report_context and re.search(r"这个|原因|哪些|影响|和昨天比|趋势|持续|跌幅|涨幅", text):
        return _intent(REPORT_DETAIL_QUESTION, "REPORT", 0.9, "日报上下文追问")
    if re.search(r"调价|展板价|上架价|挂牌价改|降价|涨价|下调|上调|库存.*调|哪些库存", text):
        return _intent(PRICE_ADJUSTMENT_INTENT, "ADJUSTMENT", 0.94, "定价/调价业务")
    if re.search(r"上一辆|上一个|前一辆|第一辆|第二辆|第三辆|第[一二三四五六七八九0-9]+个报告|刚才那辆|之前那辆|前面那辆", text):
        return _intent(HISTORY_QUOTE_REFERENCE, "EXPLANATION", 0.93, "用户引用历史报价对象")
    if re.search(r"候选车|参考了哪些车|哪些相似|相似成交|可比车|证据", text):
        return _intent(CANDIDATE_EVIDENCE_REQUEST, "EXPLANATION", 0.94, "候选/证据追问")
    if re.search(r"为什么低置信|为什么不建议自动|为什么只能人工|低置信", text):
        return _intent(WHY_LOW_CONFIDENCE, "EXPLANATION", 0.94, "低置信原因追问")
    if re.search(r"为什么|为啥|怎么来的|怎么算|价格逻辑|依据|这个价|这个区间|为什么.*价|价.*为什么", text):
        return _intent(PRICE_EXPLANATION_REQUEST, "EXPLANATION", 0.92 if has_quote else 0.78, "价格解释追问")
    if re.search(r"我要买|想买|买一辆|买一台|买个|找车|推荐.*车|预算|二手.*推荐|看车", text):
        return _intent(BUY_CAR_INTENT, "BUY", 0.96, "买车/选车咨询，不触发C2B估价")
    if re.search(r"不是|改成|修改|更正|纠正|应该是|换成", text) and has_vehicle_hint:
        return _intent(VEHICLE_INFO_UPDATE, "C2B", 0.94, "用户修改车辆字段")
    if re.search(r"就这个|选第\s*[一二三四五六七八九0-9]+|确认|是这个", text):
        return _intent(VEHICLE_CONFIRM, "C2B", 0.92, "用户确认车型")
    if re.search(r"开始估价|现在可以报价|帮我算一下|立即估价|重新估价", text):
        return _intent(PRICE_QUOTE_REQUEST, "C2B", 0.9, "用户请求报价")
    if re.search(r"我要收|想收|收一个|收一辆|收一台|车商收|我要卖|想卖|卖一辆|卖一台|卖车|能卖多少钱|收车价|收多少钱|残值|帮我估|估一下|估个价|报价|值多少", text):
        return _intent(SELL_CAR_VALUATION_INTENT, "C2B", 0.94, "卖车/收车估价请求")
    if has_vehicle_hint:
        complete = not validate_vehicle_slots(slots)
        return _intent(SELL_CAR_VALUATION_INTENT if complete else VEHICLE_INFO_ADD, "C2B", 0.88 if complete else 0.82, "用户提供车辆七要素")
    if re.search(r"宝马|奔驰|奥迪|大众|丰田|本田|车|车型|品牌|公里|过户|颜色|城市", text):
        return _intent(UNKNOWN_OR_INCOMPLETE, "UNKNOWN", 0.5, "车辆信息不足")
    return _intent(OUT_OF_SCOPE, "NONE", 0.9, "非当前业务范围")


def _intent(intent_type: str, task: str, confidence: float, reason: str) -> Dict[str, Any]:
    return {"type": intent_type, "task": task, "confidence": confidence, "source": "deterministic_state_machine", "reason": reason}


def build_vehicle_state(slots: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "brand": flat_slot_value(slots, "brand") or "",
        "series": flat_slot_value(slots, "series") or "",
        "model_year": flat_slot_value(slots, "model_year") or "",
        "first_license_date": flat_slot_value(slots, "first_license_date") or "",
        "first_license_year": flat_slot_value(slots, "first_license_year") or "",
        "first_license_month": flat_slot_value(slots, "first_license_month") or "",
        "trim": flat_slot_value(slots, "trim") or "",
        "trim_normalized": compact_text(flat_slot_value(slots, "trim") or ""),
        "powertrain": flat_slot_value(slots, "energy_type") or "UNKNOWN",
        "mileage_km": int(round(float(flat_slot_value(slots, "mileage_wan_km") or 0) * 10000)) if flat_slot_value(slots, "mileage_wan_km") not in (None, "") else None,
        "city": flat_slot_value(slots, "city") or "",
        "transfer_count": flat_slot_value(slots, "transfer_count"),
        "color": flat_slot_value(slots, "color") or "",
        "condition_grade": flat_slot_value(slots, "condition_group") or "SYSTEM_DEFAULT_GOOD_CONDITION",
        "vehicle_confirmed": bool(flat_slot_value(slots, "vehicle_confirmed") or flat_slot_value(slots, "trim")),
    }


def vehicle_state_hash(vehicle_state: Dict[str, Any]) -> str:
    payload = json.dumps(vehicle_state or {}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def evidence_card_guard(*, evidence_card: Dict[str, Any], active_quote_id: str | None, active_vehicle_state_hash: str | None, quote_status: str, active_task_type: str) -> Dict[str, Any]:
    reasons: List[str] = []
    if not evidence_card:
        reasons.append("NO_EVIDENCE_CARD")
    if evidence_card.get("quote_id") and active_quote_id and str(evidence_card.get("quote_id")) != str(active_quote_id):
        reasons.append("QUOTE_ID_MISMATCH")
    if evidence_card.get("vehicle_state_hash") and active_vehicle_state_hash and str(evidence_card.get("vehicle_state_hash")) != str(active_vehicle_state_hash):
        reasons.append("VEHICLE_STATE_HASH_MISMATCH")
    if quote_status != "COMPLETED":
        reasons.append("QUOTE_NOT_COMPLETED")
    if active_task_type != SELL_CAR_VALUATION_INTENT:
        reasons.append("TASK_NOT_VALUATION")
    return {"allowed": not reasons, "reasons": reasons}


def legacy_intent_name(intent_type: str) -> str:
    if intent_type in VALUATION_INTENTS:
        return "valuation"
    if intent_type == PRICE_ADJUSTMENT_INTENT:
        return "adjust"
    if intent_type in {BUY_CAR_INTENT, PRICE_EXPLANATION_REQUEST, CANDIDATE_EVIDENCE_REQUEST, WHY_LOW_CONFIDENCE, HISTORY_QUOTE_REFERENCE, DAILY_REPORT_READ_INTENT, REPORT_DETAIL_QUESTION}:
        return "chat"
    return "fallback"


def missing_field_labels(missing: Iterable[str]) -> List[str]:
    return [FIELD_ALIASES.get(field, field) for field in missing]
