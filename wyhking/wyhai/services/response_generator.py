from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .llm_client import Qwen3LocalClient, extract_json_object, load_prompt, strip_think
from .intent_system import (
    BUY_CAR_INTENT, CANDIDATE_EVIDENCE_REQUEST, DAILY_REPORT_READ_INTENT,
    HISTORY_QUOTE_REFERENCE, PRICE_ADJUSTMENT_INTENT, PRICE_EXPLANATION_REQUEST, REPORT_DETAIL_QUESTION,
    RESET_VEHICLE, WHY_LOW_CONFIDENCE,
)


ROOT = Path(__file__).resolve().parents[1]
FINETUNE_DIR = ROOT / "data" / "finetune"


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _wan(value: Any) -> str:
    try:
        return f"{float(value) / 10000:.1f}万"
    except Exception:
        return ""


def _price_text(value: Any, *, value_is_wan: bool = False) -> str:
    try:
        number = float(value)
    except Exception:
        return ""
    if value_is_wan or abs(number) < 1000:
        return f"{number:.2f}万"
    return f"{number / 10000:.2f}万"


def _first_value(payload: Dict[str, Any], paths: List[List[str]]) -> Any:
    for path in paths:
        cur: Any = payload
        ok = True
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                ok = False
                break
            cur = cur.get(key)
        if ok and cur not in (None, ""):
            return cur
    return None


class ResponseGenerator:
    def __init__(self, llm_client: Qwen3LocalClient | None = None) -> None:
        self.llm_client = llm_client or Qwen3LocalClient()
        self.rewrite_prompt = load_prompt("prompts/grounded_response_rewrite_qwen3.md")

    def generate(
        self,
        *,
        user_message: str,
        intent: Dict[str, Any],
        slots: Dict[str, Any],
        vehicle_match: Dict[str, Any],
        missing_fields: List[str],
        quick_tags: List[Dict[str, Any]],
        pricing: Dict[str, Any],
        warnings: List[str],
        fallback_used: bool,
        fallback_reason: str,
    ) -> Dict[str, Any]:
        style = "ask_missing_fields"
        text = ""
        cards: List[Dict[str, Any]] = []
        intent_type = intent.get("type")

        if intent_type == BUY_CAR_INTENT:
            style = "buy_car_consult"
            text = "你这是买车咨询，我不会直接生成收车报价。可以告诉我预算、城市、用途、偏好的品牌/车系和年份，我帮你做选车建议；如果你要给自己的车估收车价，请直接发完整车辆六要素。"
        elif intent_type == "BUSINESS_INTENT_CLARIFICATION":
            style = "business_intent_clarification"
            recognized = self._recognized_summary(slots, vehicle_match)
            prefix = f"我先识别到：{recognized}。" if recognized else ""
            text = (
                f"{prefix}“买/想要一辆”在内部业务里可能表示收车估价、售车估价或查找车源。"
                "请选择下面的业务动作，我会保留已经识别到的车辆信息继续处理。"
            )
        elif intent_type == PRICE_ADJUSTMENT_INTENT:
            style = "price_adjustment"
            scope = " ".join(str(x) for x in [slots.get("brand") or "", slots.get("series") or ""] if x).strip()
            scope_text = f"（范围：{scope}）" if scope else ""
            text = (
                f"这是库存/车源调价任务{scope_text}，不会复用上一辆车的估价卡。"
                "如果你要看工单，我可以按品牌/车系/门店/库存天数筛选；如果你要执行调价，请补充目标动作"
                "（上调、下调、批量预览）、调价原因和必要时的车源号或筛选范围。"
            )
        elif intent_type in {DAILY_REPORT_READ_INTENT, REPORT_DETAIL_QUESTION}:
            style = "daily_report"
            text = "这是行情日报/报告查询任务。请告诉我要看全国、城市、品牌、车系，还是具体价格波动榜单；不会生成车辆估价报告。"
        elif intent_type == RESET_VEHICLE:
            style = "reset_vehicle"
            text = "已清空当前车辆和旧报价上下文。你可以重新输入一辆车的完整信息。"
        elif intent_type == "OUT_OF_SCOPE":
            style = "smalltalk"
            text = "我主要负责二手车估价、买车咨询、库存调价、行情日报和报价解释。你可以直接告诉我完整车辆信息，或说明要做哪类业务。"
        elif intent_type in {"EXPLAIN_PRICE", PRICE_EXPLANATION_REQUEST, CANDIDATE_EVIDENCE_REQUEST, WHY_LOW_CONFIDENCE, HISTORY_QUOTE_REFERENCE, "FEEDBACK_INACCURATE", "FEEDBACK_PRICE_TOO_HIGH", "FEEDBACK_PRICE_TOO_LOW"}:
            style = "explain_price"
            text = self._explain_price(user_message, intent, slots, pricing, vehicle_match, warnings)
        elif (
            pricing.get("called_price")
            and pricing.get("price_result")
            and str(pricing["price_result"].get("quote_decision") or "").upper()
            == "NO_DEAL"
        ):
            style = "no_deal"
            price_result = pricing["price_result"]
            text = str(price_result.get("frontline_answer") or "").strip()
            if not text:
                text = (
                    "这台车暂不建议收：当前能收下来的价格已经超过可盈利上限。"
                    "除非有已锁定买家或专项审批，否则不要跟价。"
                )
            cards.append({"type": "pricing_no_deal", "data": price_result})
        elif (
            pricing.get("called_price")
            and pricing.get("price_result")
            and (
                pricing["price_result"].get("success") is False
                or str(pricing["price_result"].get("quote_decision") or "").upper()
                == "NO_QUOTE"
            )
        ):
            style = "confirm_vehicle"
            title = self._vehicle_title({}, slots)
            match = vehicle_match or {}
            if not match.get("model_id") or match.get("catalog_coverage_level") in {
                "series_or_custom_text_only",
                "user_confirmed_custom_model",
            }:
                text = (
                    f"这台{title}暂时不能直接出价：当前车型库没有确认到与输入年款和配置完全一致的车款。"
                    "请先核对车型年款和完整配置名称；确认后我再给建议挂牌价、预计成交价、收车价和最高收车价。"
                )
            else:
                text = (
                    f"这台{title}本次暂时不能直接出价：现有内部成交和已完成的市场数据不足以支持可靠报价。"
                    "请先复核车款ID、车型年款和完整配置，仍确认无误则转人工定价师审核，不能用相近车型价格代替。"
                )
        elif pricing.get("price_result") and (
            pricing.get("called_price") or pricing.get("price_state") == "predicted"
        ):
            style = "show_price"
            price_result = pricing["price_result"]
            point = (
                ((price_result.get("price") or {}).get("point"))
                or price_result.get("final_price")
                or ((price_result.get("price_result") or {}).get("final_price"))
            )
            standard = price_result.get("standard_vehicle") or {}
            title = self._vehicle_title(standard, slots)
            if pricing.get("called_price"):
                text = f"已按这台{title}生成估价。"
            else:
                text = f"你这次确认的信息与当前报价一致，价格不变；这台{title}沿用当前有效报价。"
            if not (slots.get("condition_group") or slots.get("condition") or slots.get("inspection_grade")):
                text += " 当前按无重大事故、泡水、火烧、调表等常规可交易车况估算，最终价格需结合实车检测确认。"
            catalog_warning = str(
                price_result.get("catalog_resolution_warning")
                or (price_result.get("normalized_query") or {}).get(
                    "catalog_resolution_warning"
                )
                or ""
            ).strip()
            if catalog_warning:
                text += f" {catalog_warning}"
            ladder = price_result.get("price_ladder") or ((price_result.get("appraiser_decision_record") or {}).get("final_price_ladder_yuan")) or {}
            listing = ladder.get("recommended_listing_yuan") or ladder.get("recommended_listing")
            listing_range = ladder.get("recommended_listing_range_yuan") or price_result.get("recommended_listing_range_yuan")
            b2c = ladder.get("expected_b2c_transaction_yuan") or ladder.get("expected_b2c_transaction")
            b2c_range = ladder.get("b2c_transaction_range_yuan") or ladder.get("b2c_range")
            c2b = ladder.get("expected_c2b_yuan") or ladder.get("expected_c2b")
            c2b_range = ladder.get("c2b_range_yuan") or ladder.get("c2b_range")
            max_c2b = ladder.get("max_c2b_yuan") or ladder.get("max_c2b") or price_result.get("max_c2b_price_yuan")
            if all(value not in (None, "") for value in (listing, b2c, c2b, max_c2b)):
                text += (
                    f" 建议挂牌价{_price_text(listing)}{self._range_text(listing_range)}；"
                    f"预计实际售车价{_price_text(b2c)}{self._range_text(b2c_range)}；"
                    f"预计实际收车价{_price_text(c2b)}{self._range_text(c2b_range)}；"
                    f"最高收车价{_price_text(max_c2b)}。"
                )
            else:
                c2b_price = price_result.get("c2bPrice") or price_result.get("c2b_price") or price_result.get("purchase_price")
                b2c_price = price_result.get("b2cPrice") or price_result.get("b2c_price") or price_result.get("sale_price")
                if c2b_price and b2c_price:
                    text += f" 建议收车价约 {_price_text(c2b_price, value_is_wan=True)}，建议售车价约 {_price_text(b2c_price, value_is_wan=True)}。"
                if point:
                    text += f" 参考点价约 {_price_text(point)}。"
            review_required = (
                (price_result.get("review") or {}).get("required")
                or str(price_result.get("quote_decision") or "").upper() == "MANUAL_REVIEW"
            )
            if review_required:
                warning = next(
                    (
                        str(value)
                        for value in (price_result.get("risk_warnings") or [])
                        if value and str(value).strip() != catalog_warning
                    ),
                    "",
                )
                warning = warning.replace("七要素", "这台车的具体信息").replace(
                    "严格同款证据有限", "近期完全同款成交较少"
                )
                if warning and warning not in text:
                    text += f" {warning}"
                elif not catalog_warning:
                    text += " 近期完全同款成交较少，验车后再确认最终收车价。"
            cards.append({"type": "pricing_result", "data": price_result})
        elif missing_fields:
            style = "confirm_vehicle" if "vehicle_confirm" in missing_fields or not vehicle_match.get("matched") else "ask_missing_fields"
            text = self._ask_missing(intent, slots, vehicle_match, missing_fields)
        elif pricing.get("price_state") == "stale":
            style = "ask_missing_fields"
            text = "你刚刚改了会影响价格的字段，当前报价已过期。需要重新估价后，我再给你新的结果。"
        else:
            style = "ask_missing_fields"
            text = "我已经记录了一部分车辆信息，还需要确认车型、上牌时间、里程、城市、颜色和过户次数后才能估价。"

        if style not in {"buy_car_consult", "price_adjustment", "daily_report", "reset_vehicle", "confirm_vehicle", "ask_missing_fields", "show_price", "explain_price"}:
            rewrite = self._rewrite(user_message, intent, slots, vehicle_match, pricing, warnings, text, quick_tags)
            if rewrite.get("reply"):
                text = rewrite["reply"]

        return {"text": text, "style": style, "cards": cards}

    @staticmethod
    def _range_text(value: Any) -> str:
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            return ""
        low = _price_text(value[0])
        high = _price_text(value[1])
        return f"（{low}-{high}）" if low and high else ""

    def _vehicle_title(self, standard: Dict[str, Any], slots: Dict[str, Any]) -> str:
        brand = str(standard.get("brand_name") or slots.get("brand") or "").strip()
        series = str(standard.get("series_name") or slots.get("series") or "").strip()
        vehicle_parts = [series] if brand and series.startswith(brand) else [brand, series]
        parts = [
            standard.get("model_year") or slots.get("model_year") or "",
            *vehicle_parts,
            standard.get("model_name") or slots.get("trim") or "",
        ]
        title = " ".join(str(p) for p in parts if p)
        return title or "车"

    def _ask_missing(self, intent: Dict[str, Any], slots: Dict[str, Any], vehicle_match: Dict[str, Any], missing: List[str]) -> str:
        brand = slots.get("brand") or vehicle_match.get("brand_name")
        recognized = self._recognized_summary(slots, vehicle_match)
        prefix = f"已识别：{recognized}。" if recognized else ""
        if brand and "vehicle_confirm" in missing and not slots.get("trim"):
            candidates = [item.get("label") or item.get("series") for item in vehicle_match.get("candidates", []) if item.get("label") or item.get("series")]
            if candidates:
                return f"{prefix}还需要确认具体款型：{ ' / '.join(candidates[:4]) }。也可以手动输入完整款型。"
            return f"{prefix}还需要确认具体车系或具体配置，比如是哪一款、哪一年款。"
        if brand and "series" in missing:
            return f"{prefix}还需要确认具体车系/车型。"
        field_names = {
            "series": "车系/车型",
            "brand": "品牌",
            "model_year": "车型年款",
            "first_license_date": "上牌时间",
            "first_license_year": "上牌时间",
            "first_license_month": "上牌月份",
            "year_disambiguation": "确认“20年”是车型年款还是上牌时间",
            "city": "城市",
            "mileage_wan_km": "公里数",
            "transfer_count": "过户次数",
            "color": "颜色",
            "trim": "具体款型/配置",
            "vehicle_confirm": "具体款型/配置",
            "task": "要收车价还是销售价",
        }
        readable = [field_names.get(f, f) for f in missing if f != "vehicle_confirm"]
        return f"{prefix}还差：{'、'.join(readable[:4])}。补齐后我再调用估价模型。"

    def _recognized_summary(self, slots: Dict[str, Any], vehicle_match: Dict[str, Any]) -> str:
        brand = slots.get("brand") or vehicle_match.get("brand_name")
        series = slots.get("series") or vehicle_match.get("series_name")
        if brand and series and str(series).startswith(str(brand)):
            vehicle = str(series)
        else:
            vehicle = " ".join(str(x) for x in (brand, series) if x)
        parts = []
        if vehicle:
            parts.append(vehicle)
        if slots.get("model_year"):
            parts.append(f"{slots['model_year']}款")
        license_value = self._first_license_value(slots)
        if license_value:
            parts.append(f"{license_value}上牌")
        if slots.get("trim"):
            parts.append(str(slots["trim"]))
        if slots.get("mileage_wan_km") not in (None, ""):
            parts.append(f"{slots['mileage_wan_km']}万公里")
        if slots.get("city"):
            parts.append(str(slots["city"]))
        if slots.get("transfer_count") not in (None, ""):
            parts.append(f"{slots['transfer_count']}次过户")
        if slots.get("color"):
            parts.append(str(slots["color"]))
        return "、".join(parts)

    @staticmethod
    def _first_license_value(slots: Dict[str, Any]) -> str:
        raw_date = str(slots.get("first_license_date") or slots.get("reg_date") or "").strip()
        year = slots.get("first_license_year")
        month = slots.get("first_license_month")
        if raw_date:
            parts = raw_date.replace("/", "-").split("-")
            if not year and parts and parts[0].isdigit():
                year = int(parts[0])
            if not month and len(parts) > 1 and parts[1].isdigit():
                month = int(parts[1])
        if year in (None, ""):
            return ""
        if month not in (None, ""):
            try:
                return f"{int(year)}-{max(1, min(12, int(month))):02d}"
            except Exception:
                pass
        return str(year)

    def _extract_comparables(self, price_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        candidates: Any = (
            price_result.get("selected_comparables")
            or price_result.get("ref_cars")
            or price_result.get("top_candidates")
            or ((price_result.get("evidence_card") or {}).get("top_candidates"))
            or ((price_result.get("evidence_card") or {}).get("selected_comparables"))
            or ((price_result.get("business_explanation") or {}).get("evidence_details"))
        )
        if not candidates and isinstance(price_result.get("price_result"), dict):
            nested = price_result["price_result"]
            candidates = nested.get("selected_comparables") or nested.get("ref_cars")
        if isinstance(candidates, dict):
            candidates = list(candidates.values())
        if not isinstance(candidates, list):
            return []
        return [item for item in candidates if isinstance(item, dict)]

    def _candidate_vehicle_text(self, item: Dict[str, Any]) -> str:
        vehicle = (
            item.get("vehicle")
            or item.get("candidate_vehicle")
            or item.get("vehicle_name")
            or item.get("title")
            or item.get("model_name")
        )
        if vehicle:
            return str(vehicle)
        parts = [
            item.get("candidate_brand") or item.get("brand"),
            item.get("candidate_series") or item.get("series"),
            item.get("model_year"),
            item.get("candidate_model") or item.get("model"),
            item.get("candidate_trim") or item.get("trim"),
        ]
        return " ".join(str(part) for part in parts if part not in (None, "")).strip() or "未命名候选"

    def _candidate_price_text(self, item: Dict[str, Any]) -> str:
        for key in ("c2b_converted_price_wan", "price_wan", "candidate_price_wan"):
            if item.get(key) not in (None, ""):
                return _price_text(item.get(key), value_is_wan=True)
        for key in ("candidate_price", "price", "raw_price", "final_price", "listing_price"):
            if item.get(key) not in (None, ""):
                return _price_text(item.get(key), value_is_wan=False)
        return "价格未记录"

    def _candidate_line(self, index: int, item: Dict[str, Any]) -> str:
        vehicle = self._candidate_vehicle_text(item)
        price_text = self._candidate_price_text(item)
        level = item.get("retrieval_level") or item.get("semantic_tier") or item.get("match_level") or item.get("level") or "-"
        city = item.get("city") or item.get("candidate_city") or "-"
        event_time = item.get("event_time") or item.get("transaction_time") or item.get("candidate_date") or item.get("date") or "-"
        source = item.get("source_family") or item.get("source") or item.get("price_role") or "-"
        relation = {
            "L1": "同款同年",
            "L2": "同款相近年份",
            "L3": "同车系相近配置",
            "L4": "相近车型",
        }.get(str(level).upper(), "相近车源")
        source_text = {
            "internal_c2b_purchase": "内部实际收车记录",
            "internal_b2c_sale": "内部实际售车记录",
            "internal_listing": "内部在售记录",
            "dongchedi": "已保存的懂车帝车源",
            "autohome": "已保存的汽车之家车源",
            "che168": "已保存的二手车之家车源",
        }.get(str(source), "已保存的市场或内部记录")
        return (
            f"{index}. {vehicle}，{price_text}，{relation}，"
            f"{source_text}，{city}，{event_time}"
        )

    def _reference_price_and_interval(self, price_result: Dict[str, Any], conclusion: Dict[str, Any], nested_price: Dict[str, Any]) -> tuple[str, str]:
        reference_wan = conclusion.get("reference_price_wan")
        reference_text = ""
        if reference_wan not in (None, ""):
            reference_text = _price_text(reference_wan, value_is_wan=True)
        if not reference_text:
            final_price = _first_value(
                price_result,
                [
                    ["final_price"],
                    ["price", "point"],
                    ["price_result", "final_price"],
                    ["price_result", "price", "point"],
                ],
            )
            reference_text = _price_text(final_price, value_is_wan=False) if final_price not in (None, "") else "-"
        interval = conclusion.get("interval_wan")
        if isinstance(interval, list) and len(interval) >= 2:
            interval_text = f"{_price_text(interval[0], value_is_wan=True)}到{_price_text(interval[1], value_is_wan=True)}"
        else:
            low = (
                nested_price.get("price_low")
                or nested_price.get("lower")
                or (price_result.get("interval") or {}).get("low")
                or (price_result.get("price") or {}).get("lower")
            )
            high = (
                nested_price.get("price_high")
                or nested_price.get("upper")
                or (price_result.get("interval") or {}).get("high")
                or (price_result.get("price") or {}).get("upper")
            )
            interval_text = f"{_price_text(low, value_is_wan=False)}到{_price_text(high, value_is_wan=False)}" if low not in (None, "") and high not in (None, "") else "-"
        return reference_text, interval_text

    def _explain_price(
        self,
        user_message: str,
        intent: Dict[str, Any],
        slots: Dict[str, Any],
        pricing: Dict[str, Any],
        vehicle_match: Dict[str, Any],
        warnings: List[str],
    ) -> str:
        price_result = pricing.get("price_result") or pricing.get("current_pricing_result") or {}
        if not price_result:
            return "可以解释，但我现在还没有这台车的有效报价结果。你先发车型、上牌时间、里程、城市、颜色和过户次数，我生成报价后再按真实结果拆给你看。"
        nested_price = price_result.get("price_result") or {}
        business = price_result.get("business_explanation") or (price_result.get("evidence_card") or {}).get("business_explanation") or {}
        conclusion = business.get("conclusion") or {}
        components = business.get("why_this_price") or []
        low_reasons = business.get("why_low_confidence") or []
        evidence_summary = price_result.get("evidence_summary") or {}
        trace = price_result.get("price_trace") or {}
        quoted_standard = price_result.get("standard_vehicle") or {}
        if isinstance(quoted_standard, dict) and quoted_standard:
            vehicle_title = self._vehicle_title(quoted_standard, slots)
        elif slots.get("standard_vehicle"):
            vehicle_title = str(slots.get("standard_vehicle")).strip()
        else:
            vehicle_title = self._vehicle_title(vehicle_match or {}, slots)
        subject = f"历史车辆“{vehicle_title}”" if intent.get("type") == HISTORY_QUOTE_REFERENCE else f"当前车辆“{vehicle_title}”"
        ladder = price_result.get("price_ladder") or (
            (price_result.get("appraiser_decision_record") or {}).get(
                "final_price_ladder_yuan"
            )
        ) or {}
        listing = ladder.get("recommended_listing_yuan")
        listing_range = ladder.get("recommended_listing_range_yuan")
        b2c = ladder.get("expected_b2c_transaction_yuan")
        b2c_range = ladder.get("b2c_transaction_range_yuan")
        c2b = ladder.get("expected_c2b_yuan")
        c2b_range = ladder.get("c2b_range_yuan")
        max_c2b = ladder.get("max_c2b_yuan")
        first_offer = ladder.get("first_c2b_offer_yuan")
        # Keep every follow-up on the same four-price semantics as the report.
        # Older payloads may omit ``price_ladder`` but still carry the values
        # at top level; never collapse purchase and sale into one ambiguous
        # “current quote”.
        listing = listing or price_result.get("recommended_listing_price_yuan") or price_result.get("listing_price_yuan")
        b2c = b2c or price_result.get("b2cPrice") or price_result.get("sale_price_yuan")
        c2b = c2b or price_result.get("c2bPrice") or price_result.get("final_price") or (price_result.get("price") or {}).get("point")
        max_c2b = max_c2b or price_result.get("max_c2b_price_yuan") or (price_result.get("price") or {}).get("upper")
        message = str(user_message or "")

        if str(intent.get("type") or "").startswith("FEEDBACK"):
            role = (
                "收车价" if re.search(r"收车价|收价|收进来|收上来|可以收|能不能收|能收", message)
                else "收车价" if re.search(r"(?:其他机构|别家|同行).*(?:报价|给价|出价|给(?:了)?我?\s*\d)", message)
                else "预计售车价" if re.search(r"售车价|卖车价|成交价|卖出去", message)
                else "建议挂牌价" if re.search(r"挂牌价|网上挂价|上架价", message)
                else "预计售车价" if re.search(r"网上|瓜子|懂车帝|汽车之家|人人车|优信|车商|市场|同款", message)
                else ""
            )
            direction = (
                "偏低" if re.search(r"偏低|太低|低了|(?:网上|瓜子|懂车帝|汽车之家|人人车|优信|车商|市场).*(?:更高|卖|挂|成交|报价)|别人.*(?:卖|成交)|同款.*(?:比你|更)高|市场.*高", message)
                else "偏低" if re.search(r"(?:其他机构|别家|同行).*(?:报价|给价|出价|给(?:了)?我?\s*\d)", message)
                else "偏高" if re.search(r"偏高|太高|高了|贵了|收进来.*亏|肯定亏|同款.*(?:比你|更)低", message)
                else ""
            )
            if not role and not direction:
                role_text = []
                if c2b not in (None, ""):
                    role_text.append(f"建议收车价{_price_text(c2b)}{self._range_text(c2b_range)}")
                if max_c2b not in (None, ""):
                    role_text.append(f"最高收车价{_price_text(max_c2b)}")
                if b2c not in (None, ""):
                    role_text.append(f"预计实际售车价{_price_text(b2c)}{self._range_text(b2c_range)}")
                current_text = "当前结果分别是：" + "，".join(role_text) + "。" if role_text else ""
                return (
                    f"可以，先不默认系统一定正确。{current_text}"
                    "请先指出是建议收车价、最高收车价还是预计实际售车价不符合你的判断，以及偏高还是偏低。"
                    "如果你有真实成交、同款车源或实车检测结果，也可以直接发来；我会对照当前这三个价格定位差异，"
                    "不会再用一个含糊的‘当前报价’把收车价和售车价混在一起。"
                )
            focus = f"{role or '当前报价'}{direction}" if direction else (role or "当前报价")
            support = int(trace.get("catalog_appraiser_b2c_support") or trace.get("catalog_appraiser_c2b_support") or 0)
            selected_comparables = [item for item in (price_result.get("selected_comparables") or []) if isinstance(item, dict)]
            evidence_count = max(support, len(selected_comparables))
            known_vehicle_bits = [
                str(slots.get("first_license_date") or slots.get("first_license_year") or ""),
                f"{slots.get('mileage_wan_km')}万公里" if slots.get("mileage_wan_km") not in (None, "") else "",
                str(slots.get("city") or ""),
                f"{slots.get('transfer_count')}次过户" if slots.get("transfer_count") not in (None, "") else "",
                str(slots.get("color") or ""),
            ]
            vehicle_detail = "、".join(item for item in known_vehicle_bits if item)
            price_roles = []
            if c2b not in (None, ""):
                price_roles.append(f"建议收车价{_price_text(c2b)}{self._range_text(c2b_range)}")
            if max_c2b not in (None, ""):
                price_roles.append(f"最高收车价{_price_text(max_c2b)}")
            if b2c not in (None, ""):
                price_roles.append(f"预计实际售车价{_price_text(b2c)}{self._range_text(b2c_range)}")
            evidence_sentence = (
                f"本轮可核对的高相关证据约{evidence_count}条；"
                + ("样本仍偏少，只能校验价格方向，不能单独证明报价一定准确。" if evidence_count <= 2 else "样本用于核对价格方向和边界。")
                if evidence_count
                else "当前严格同条件证据有限，因此不能把这版报价说成绝对准确。"
            )
            competitor_note = ""
            competitor_price = slots.get("user_given_price_yuan")
            if competitor_price not in (None, "") and re.search(r"(?:其他机构|别家|同行)", message):
                try:
                    competitor_value = float(competitor_price)
                    delta = competitor_value - float(max_c2b or c2b or 0)
                    competitor_note = (
                        f"\n价差定位：对方的{_price_text(competitor_value)}如果也是同车、同条件、验车后的确定收车价，"
                        f"比本次最高收车价高{_price_text(abs(delta)) if delta else '0元'}。"
                        + (
                            "这已经超过当前价格边界，不能只靠压缩利润直接跟价；需要先核对对方报价是否含附加条件、是否已验车，以及对应车辆配置和车况。"
                            if delta > 0
                            else "该报价没有超过当前价格边界，可以结合验车结果在现有区间内继续谈。"
                        )
                    )
                except (TypeError, ValueError):
                    competitor_note = ""
            purchase_script = (
                f"这台{vehicle_title}我按{vehicle_detail or '当前车辆信息'}重新核过，"
                f"目前建议先围绕{_price_text(c2b) if c2b not in (None, '') else '当前建议价'}沟通"
                f"{self._range_text(c2b_range)}，最高不超过{_price_text(max_c2b) if max_c2b not in (None, '') else '当前上限'}。"
                "如果有同款同配置、相近里程且已经验车的确定收车价，把报价条件发来，我们可以逐项对齐；"
                "条件没有对齐前，不能只因为一个更高数字就直接追价。"
            )
            sale_script = (
                f"这台{vehicle_title}按当前条件，预计实际售车价围绕"
                f"{_price_text(b2c) if b2c not in (None, '') else '当前建议价'}{self._range_text(b2c_range)}，"
                f"建议挂牌价为{_price_text(listing) if listing not in (None, '') else '以报告为准'}{self._range_text(listing_range)}。"
                "网上挂牌价不等于最终成交价；如果有同款同配置、相近里程且成交口径明确的车源，"
                "可以发来逐项核对，再判断当前售车价是否需要调整。"
            )
            frontline_script = sale_script if role in {"预计售车价", "建议挂牌价"} else purchase_script
            boundary_judgement = ""
            if competitor_price not in (None, "") and role == "收车价":
                try:
                    proposed = float(competitor_price)
                    if max_c2b not in (None, "") and proposed > float(max_c2b):
                        boundary_judgement = (
                            f"你提出的{_price_text(proposed)}比最高收车价{_price_text(max_c2b)}高"
                            f"{_price_text(proposed - float(max_c2b))}，按当前证据不建议直接收；"
                            "只有车辆参数或真实同条件成交证据发生变化，才应重新估价。"
                        )
                    elif c2b not in (None, ""):
                        boundary_judgement = (
                            f"你提出的{_price_text(proposed)}仍在当前可执行边界内，可结合验车结果和目标利润继续谈。"
                        )
                except (TypeError, ValueError):
                    boundary_judgement = ""
            return (
                f"可直接对客户这样说：{frontline_script}"
                f"\n\n内部判断：本轮质疑定位为{focus}。同一版报价为{'；'.join(price_roles)}，"
                "收车价、最高收车价和售车价使用不同业务口径，不会混成一个数字。"
                f"{boundary_judgement}"
                f"{evidence_sentence}"
                f"当前按{vehicle_detail or '已确认的车型与车辆信息'}估算；实车尚未检测，事故、泡水、火烧、调表或实际整备差异仍会改变执行价格。"
                f"{competitor_note}"
                "如需调整，请补充同车型年款配置、相近里程且价格口径明确的真实成交/在售车源，或实车检测结果；"
                "只有出现新证据或车辆参数变化时才重新估价，并展示原价、新价和变化原因。"
            )

        if re.search(
            r"(?:车况.*(?:很好|非常好|特别好).*(?:精品|高价)|按精品车(?:报|算|估)|"
            r"精品车.*(?:报|算|估))",
            message,
        ):
            return (
                "不能只凭一句‘车况很好’就按精品车抬价。当前报价仍按默认良好车况，"
                f"建议收车价{_price_text(c2b) if c2b not in (None, '') else '暂缺'}"
                f"{self._range_text(c2b_range)}，最高收车价"
                f"{_price_text(max_c2b) if max_c2b not in (None, '') else '暂缺'}。"
                "只有现场检测确认无事故、无泡水火烧、无调表，且外观内饰和机械状态达到精品标准后，"
                "才能把车况改为A级并重新估价；在检测前不能先按精品车价格收。"
            )

        if re.search(r"收车价还是售车价|这个价格.*(?:收|售)|分别是什么|四个价", message):
            if all(value not in (None, "") for value in (listing, b2c, c2b, max_c2b)):
                return (
                    f"这次不是只给一个价：建议挂牌价{_price_text(listing)}{self._range_text(listing_range)}，"
                    f"是对外展示和留议价空间的价格；预计实际售车价{_price_text(b2c)}{self._range_text(b2c_range)}，"
                    f"是更可能真正卖出的价格；预计实际收车价{_price_text(c2b)}{self._range_text(c2b_range)}，"
                    f"是正常车况下建议谈成的价格；最高收车价{_price_text(max_c2b)}，超过它利润和价格波动风险就不合适。"
                )

        if re.search(r"最高.*(?:追|收)|追到多少|收车上限|最多能收", message):
            if max_c2b not in (None, ""):
                return (
                    f"这台车最高收车价是{_price_text(max_c2b)}。"
                    f"正常目标仍是{_price_text(c2b)}{self._range_text(c2b_range)}；"
                    "只有验车结果与描述一致、手续无异常时才考虑接近上限，超过上限不建议追。"
                )

        if re.search(r"客户.*(?:嫌低|怎么说)|怎么跟客户说|客户话术", message):
            if c2b not in (None, ""):
                return (
                    "可以直接这样和客户说：‘我们不是按网上挂牌价倒推，而是按这台车当前真正能卖出的价格，"
                    f"再扣除整备、资金占用和价格波动风险来收。正常车况建议收车价约{_price_text(c2b)}，"
                    f"合理区间{self._range_text(c2b_range).strip('（）')}，最高只能到{_price_text(max_c2b)}。"
                    "验车结果好可以往区间上沿谈；如果有事故、泡水、火烧或调表，还要重新核价。’"
                )

        if re.search(r"颜色.*(?:影响|差多少)|黑色.*白色|白色.*黑色", message):
            current_color = str(slots.get("color") or "当前颜色")
            current_text = (
                f"当前按{current_color}计算的建议收车价是{_price_text(c2b)}。"
                if c2b not in (None, "")
                else ""
            )
            return (
                f"{current_text}颜色只有在同款买家偏好和实际成交里形成稳定差异时才会影响价格，"
                "而且不同车系差异不同。当前报价没有同时计算黑色和白色两个结果，所以我不能编一个差价；"
                "要看准确差额，应保留其他信息不变，分别重算两次。"
            )

        if re.search(r"里程.*(?:改|从).*(?:降|影响|少多少|差多少)", message):
            return (
                f"当前报价按{slots.get('mileage_wan_km') or '-'}万公里计算，建议收车价是"
                f"{_price_text(c2b) if c2b not in (None, '') else '暂缺'}。"
                "里程从5万变成10万的准确降幅必须在车型、上牌、城市、颜色、过户和车况都不变时重算；"
                "当前结果没有第二个里程场景，我不能用固定比例编一个差价。"
            )

        if re.search(r"置信度|你确定吗|把握", message):
            confidence = str(
                price_result.get("confidence")
                or nested_price.get("confidence")
                or "LOW"
            ).upper()
            confidence_text = {"HIGH": "较高", "MEDIUM": "中等", "LOW": "偏低"}.get(
                confidence, "需要复核"
            )
            support = int(trace.get("catalog_appraiser_b2c_support") or 0)
            external_count = int(trace.get("external_source_count") or 0)
            evidence = []
            if support:
                evidence.append(f"近期同款同年内部售车证据{support}条")
            if external_count:
                evidence.append(f"已完成市场快照覆盖{external_count}个平台来源")
            evidence_text = "、".join(evidence) if evidence else "近期完全同款成交较少"
            return (
                f"这次报价的把握程度{confidence_text}，主要因为{evidence_text}。"
                f"当前建议收车价{_price_text(c2b) if c2b not in (None, '') else '暂缺'}"
                f"{self._range_text(c2b_range)}。如果把握程度偏低，就按区间下沿谈，并在验车后人工复核；"
                "不能为了显得确定而缩窄区间。"
            )

        if re.search(r"收车价.*售车价|售车价.*收车价|收.*为什么.*低|为什么.*收.*低|价差|利润空间|毛利", str(user_message or "")):
            spread_text = ""
            if c2b not in (None, "") and b2c not in (None, ""):
                try:
                    spread_text = (
                        f"当前预计实际收车价{_price_text(c2b)}、预计实际售车价{_price_text(b2c)}，"
                        f"表面价差约{_price_text(float(b2c) - float(c2b))}。"
                    )
                except Exception:
                    spread_text = ""
            return (
                f"{spread_text}页面这里展示的是收售价差，不预设每家门店的整备费、运营费和风险缓冲。"
                "它还不是最终净利润；请在报告里的利润计算器填入你自己的成本，系统再按同一版收车价和售车价计算净毛利与毛利率。"
            )
        if re.search(r"依据|怎么来的|为什么(?:是|定|会是|给|报)?这个价格|为什么.*(?:低|高)|为何.*价格|网上.*低|内部解释", message) and any(
            value not in (None, "") for value in (listing, b2c, c2b, max_c2b)
        ):
            support_b2c = int(trace.get("catalog_appraiser_b2c_support") or 0)
            support_c2b = int(trace.get("catalog_appraiser_c2b_support") or 0)
            external_count = int(trace.get("external_source_count") or 0)
            evidence_parts = []
            if support_b2c:
                evidence_parts.append(f"同款同年内部售车证据{support_b2c}条")
            if support_c2b:
                evidence_parts.append(f"同款同年内部收车证据{support_c2b}条")
            if external_count:
                evidence_parts.append(f"已完成市场快照{external_count}个平台来源")
            selected_comparables = price_result.get("selected_comparables") or []
            if not evidence_parts and selected_comparables:
                source_names = list(
                    dict.fromkeys(
                        str(item.get("source") or "").strip()
                        for item in selected_comparables
                        if isinstance(item, dict) and str(item.get("source") or "").strip()
                    )
                )
                evidence_parts.append(
                    f"当前市场参考{len(selected_comparables)}条"
                    + (f"（{'、'.join(source_names[:3])}）" if source_names else "")
                )
            evidence_text = "、".join(evidence_parts) or "现有同款同年成交和已完成市场快照"
            online_text = ""
            if listing not in (None, "") and b2c not in (None, ""):
                online_text = (
                    f"建议挂牌价{_price_text(listing)}高于预计实际售车价{_price_text(b2c)}，"
                    "因为挂牌要留议价空间，不能把网上挂价当成真实成交价。"
                )
            # The upstream trace contains engineering labels such as
            # ``model_id_miss_*`` and internal method codes.  They are useful
            # for audit logs but must never be shown to frontline users.
            adjustment_parts = []
            matched_year = trace.get("matched_model_year") or slots.get("model_year")
            matched_trim = trace.get("matched_trim") or slots.get("trim")
            if matched_trim:
                adjustment_parts.append(
                    f"车型已按{str(matched_year) + '款' if matched_year else ''}{matched_trim}核对"
                )
            local_factor = trace.get("local_adjustment_factor")
            try:
                factor_delta = (float(local_factor) - 1.0) * 100
            except (TypeError, ValueError):
                factor_delta = 0.0
            if local_factor not in (None, ""):
                direction = "上调" if factor_delta > 0 else "下调" if factor_delta < 0 else "保持中性"
                adjustment_parts.append(
                    f"七要素综合修正{direction}{abs(factor_delta):.1f}%" if factor_delta else "七要素综合修正保持中性"
                )
            element_trace = trace.get("element_adjustment_trace") or {}
            for field, label in (("city_log_adjustment", "城市"), ("color_log_adjustment", "颜色")):
                value = element_trace.get(field)
                try:
                    percent = float(value) * 100
                except (TypeError, ValueError):
                    continue
                if abs(percent) >= 0.05:
                    adjustment_parts.append(f"{label}影响{'上调' if percent > 0 else '下调'}{abs(percent):.1f}%")
            if adjustment_parts:
                adjustment_text = "；当前主要核对结果是" + "、".join(adjustment_parts[:4]) + "。"
            else:
                known = [
                    f"上牌{slots.get('first_license_date') or slots.get('first_license_year')}" if slots.get("first_license_date") or slots.get("first_license_year") else "",
                    f"里程{slots.get('mileage_wan_km')}万公里" if slots.get("mileage_wan_km") not in (None, "") else "",
                    str(slots.get("city") or ""),
                    f"过户{slots.get('transfer_count')}次" if slots.get("transfer_count") not in (None, "") else "",
                    str(slots.get("color") or ""),
                ]
                known_text = "、".join(item for item in known if item)
                adjustment_text = (
                    f"；当前已按{known_text}核对车辆条件，但本次结果没有下发逐项金额，不能编造每一项加减价。"
                    if known_text else "；本次结果没有下发逐项调整金额，不能编造每一项加减价。"
                )
            cost_inputs = price_result.get("business_cost_inputs") or {}
            total_cost = sum(
                float(cost_inputs.get(key) or 0)
                for key in ("reconditioning_cost", "channel_cost", "holding_cost", "risk_buffer")
            )
            target_profit = float(cost_inputs.get("minimum_profit") or cost_inputs.get("target_profit") or 0)
            bridge = ""
            if b2c not in (None, ""):
                bridge = f"预计实际售车价约{_price_text(b2c)}是售车端市场判断。"
            if total_cost > 0:
                bridge += f"商业校验另外计入约{_price_text(total_cost)}的整备、运营和风险成本"
                bridge += f"，并保留约{_price_text(target_profit)}的最低利润要求" if target_profit > 0 else ""
                bridge += "。"
            sample_note = ""
            if selected_comparables:
                sample_prices = []
                for item in selected_comparables:
                    if not isinstance(item, dict):
                        continue
                    value = item.get("c2b_price") or item.get("converted_c2b_price") or item.get("price_yuan") or item.get("price")
                    try:
                        sample_prices.append(float(value))
                    except (TypeError, ValueError):
                        pass
                if sample_prices:
                    sample_note = f"可比车价格跨度约{_price_text(min(sample_prices))}至{_price_text(max(sample_prices))}；"
                if len(selected_comparables) <= 2:
                    sample_note += "严格可比样本偏少，只能校验方向，不能单独支撑高置信决策。"
            return (
                f"结论：{subject}的建议收车价是{_price_text(c2b) if c2b not in (None, '') else '暂缺'}"
                f"{self._range_text(c2b_range)}，最高收车价{_price_text(max_c2b) if max_c2b not in (None, '') else '暂缺'}；"
                f"预计实际售车价是{_price_text(b2c) if b2c not in (None, '') else '暂缺'}，这几个价格角色不能混用。"
                f"\n依据：{bridge}本次核对了{evidence_text}。{sample_note}{adjustment_text.lstrip('；')}"
                f"\n怎么执行：先围绕建议收车价谈，实车检测未确认前不要按精品车加价；超过最高收车价不建议继续追。"
                f"{online_text}本轮解释的是同一版有效报价，没有重新估价。"
            )
        if re.search(r"候选|证据|参考了哪些|可比车|相似成交", str(user_message or "")):
            comparables = self._extract_comparables(price_result)
            if not comparables:
                trace = price_result.get("price_trace") or {}
                count = (
                    evidence_summary.get("baseline_candidate_count")
                    or evidence_summary.get("candidate_count")
                    or trace.get("baseline_candidate_count")
                    or 0
                )
                return (
                    f"{subject}的原报价仍然保留，但当前结果没有下发可展示的候选车明细/逐车候选明细；"
                    f"可见的候选/证据计数为 {count}。这属于证据卡字段缺失，不会重新估价。"
                )
            rows = [self._candidate_line(index, item) for index, item in enumerate(comparables[:8], start=1)]
            return (
                f"{subject}原报价使用的候选证据仍然保留。前 {len(rows)} 条真实候选为："
                + "；".join(rows)
                + "。这些候选只用于解释原报价，本次没有重新估价，也没有改变当前车辆。"
            )
        if conclusion or nested_price:
            reference_text, interval_text = self._reference_price_and_interval(price_result, conclusion, nested_price)
            comparables = self._extract_comparables(price_result)
            candidate_count = evidence_summary.get("baseline_candidate_count") or trace.get("baseline_candidate_count") or evidence_summary.get("candidate_count") or len(comparables)
            confidence = str(
                nested_price.get("confidence")
                or price_result.get("confidence")
                or conclusion.get("confidence")
                or "LOW"
            ).upper()
            confidence_text = {"HIGH": "较高", "MEDIUM": "中等", "LOW": "偏低"}.get(
                confidence, "需要复核"
            )
            comp_text = ""
            if components:
                comp_text = "；".join(
                    f"{item.get('label') or '因素'}={item.get('display_value') or (str(item.get('amount_wan')) + '万' if item.get('amount_wan') is not None else '-')}"
                    for item in components[:4]
                )
            low_text = f" 需要复核的原因：{'、'.join(str(x) for x in low_reasons[:3])}。" if low_reasons else ""
            evidence_text = f"可核对的相近记录约{candidate_count}条" if candidate_count else "近期完全同款记录较少"
            return (
                f"{subject}这次的参考价约{reference_text}，合理区间约{interval_text}，"
                f"报价把握程度{confidence_text}；{evidence_text}。"
                f"{(' 主要影响：' + comp_text + '。') if comp_text else ''}"
                f"{low_text}"
                "这里解释的是已经生成的报价，没有偷偷重算或改价。"
            )
        price = price_result.get("price") or {}
        rag = price_result.get("rag") or {}
        review = price_result.get("review") or {}
        title = vehicle_title
        point = _wan(price.get("point"))
        lower = _wan(price.get("lower"))
        upper = _wan(price.get("upper"))
        evidence_text = ""
        if rag:
            evidence_text = f"当前可核对的相近记录有{rag.get('comparable_count') or 0}条。"
            top5 = (rag.get("topk_summary") or {}).get("top5_median_price")
            if top5:
                evidence_text += f"其中最接近的几条价格中间值约{_wan(top5)}。"
        review_text = ""
        if review.get("required"):
            review_text = "这次还需要验车后人工复核，不能只看系统价格直接收车。"
        return (
            f"{subject}这次的参考价是{point or '暂缺'}，合理区间约{lower or '-'}到{upper or '-'}。"
            "定价时核对了具体车型、上牌时间、里程、城市、过户次数、颜色和已有相近车记录。"
            f"{evidence_text}{review_text}"
            "如果觉得偏高或偏低，请补充实际车况、配置差异或一条同款车源；也可以直接改城市或里程，我会按新信息重新估。"
        )

    def _rewrite(
        self,
        user_message: str,
        intent: Dict[str, Any],
        slots: Dict[str, Any],
        vehicle_match: Dict[str, Any],
        pricing: Dict[str, Any],
        warnings: List[str],
        deterministic_reply: str,
        quick_tags: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        facts = {
            "user_message": user_message,
            "intent": intent,
            "slots": slots,
            "vehicle_match": vehicle_match,
            "pricing_result": pricing.get("price_result") or pricing.get("current_pricing_result") or {},
            "rag": ((pricing.get("price_result") or {}).get("rag") or {}),
            "review": ((pricing.get("price_result") or {}).get("review") or {}),
            "grounded_points": [deterministic_reply],
            "allowed_actions": [tag.get("type") for tag in quick_tags],
        }
        result = self.llm_client.rewrite_reply(self.rewrite_prompt, facts)
        if not result.ok:
            _append_jsonl(
                FINETUNE_DIR / "response_rewrite_sft_candidates.jsonl",
                {
                    "user_message": user_message,
                    "conversation_state": facts,
                    "llm_output": {},
                    "validated_output": {"reply": deterministic_reply},
                    "final_action": "deterministic_reply",
                    "human_correction": {},
                    "error_type": result.fallback_reason,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
            return {}
        parsed = extract_json_object(result.content)
        reply = ""
        if isinstance(parsed, dict):
            reply = str(parsed.get("reply") or "").strip()
        else:
            reply = strip_think(result.content)
        if not reply or any(bad in reply for bad in ["保证成交", "一定准确", "精准无误"]):
            return {}
        _append_jsonl(
            FINETUNE_DIR / "response_rewrite_sft_candidates.jsonl",
            {
                "user_message": user_message,
                "conversation_state": facts,
                "llm_output": parsed or {"reply": result.content},
                "validated_output": {"reply": reply},
                "final_action": "rewrite_reply",
                "human_correction": {},
                "error_type": "",
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
        )
        return {"reply": reply}
