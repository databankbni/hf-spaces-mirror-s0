"""Auditable appraiser decision record for one exact seven-element quote."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from .v195_internal_dcd_appraiser import AppraiserAnchor


def _number(value: Any) -> float | None:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed) or not np.isfinite(float(parsed)):
        return None
    return float(parsed)


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _yuan(value: Any) -> str:
    number = _number(value)
    return f"{number / 10_000:.2f}万" if number is not None else "无"


def _target_elements(payload: dict[str, Any]) -> dict[str, Any]:
    mileage = _number(payload.get("mileage_wan_km") or payload.get("mileage"))
    if mileage is None:
        mileage_km = _number(payload.get("mileage_km"))
        mileage = mileage_km / 10_000.0 if mileage_km is not None else None
    return {
        "standard_vehicle": payload.get("trim")
        or payload.get("standard_vehicle")
        or payload.get("standardVehicle")
        or payload.get("model_name"),
        "model_year": _number(payload.get("model_year") or payload.get("modelYear")),
        "registration_date": payload.get("registration_date")
        or payload.get("first_registration_date")
        or payload.get("regDate"),
        "mileage_wan_km": mileage,
        "city": payload.get("city") or payload.get("city_name"),
        "transfer_count": _number(
            payload.get("transfer_count")
            if payload.get("transfer_count") is not None
            else payload.get("transfer")
        ),
        "color": payload.get("color") or payload.get("color_raw"),
        "condition_grade": payload.get("condition_grade")
        or payload.get("inspection_grade")
        or payload.get("condition")
        or "A",
    }


def _source_parts(source_refs: dict[str, Any]) -> list[dict[str, Any]]:
    external = source_refs.get("external") or {}
    rows: list[dict[str, Any]] = []
    for source in external.get("sources") or []:
        rows.append(
            {
                "source": source.get("source"),
                "asking_price_median_yuan": _number(source.get("price_median_yuan")),
                "matched_count": int(_number(source.get("matched_count")) or 0),
                "match_level": source.get("match_level"),
                "same_year": source.get("same_year"),
                "role": "ASKING_PRICE_EVIDENCE_NOT_TRANSACTION_TRUTH",
            }
        )
    return rows


def build_appraiser_decision_record(
    *,
    payload: dict[str, Any],
    target_side: str,
    result: dict[str, Any],
    catalog_anchor: AppraiserAnchor | None,
) -> dict[str, Any]:
    """Explain exactly how evidence became the listing/B2C/C2B ladder."""

    elements = _target_elements(payload)
    source_refs = _json(result.get("source_evidence_refs"))
    comparable_adjustment = _json(result.get("comparable_adjustment"))
    residual = _json(result.get("residual_correction"))
    costs = result.get("business_cost_inputs") or {}
    b2c = _number(result.get("expected_b2c_transaction_price"))
    c2b = _number(result.get("expected_final_c2b_price"))
    listing = _number(result.get("recommended_listing_price"))
    external_listing = _number(result.get("listing_price_yuan"))
    external_proxy = _number(result.get("external_b2c_proxy_yuan"))
    asking_discount = (
        1.0 - external_proxy / external_listing
        if external_listing and external_proxy is not None
        else None
    )

    identity = dict((catalog_anchor.identity if catalog_anchor else {}) or {})
    identity.update(
        {
            "requested_model_id": payload.get("model_id") or payload.get("modelId"),
            "match_granularity": "BRAND_SERIES_TRIM_MODEL_YEAR",
            "strict_same_trim_same_model_year": catalog_anchor is not None,
            "configuration_confusion_guard": "型号数字和配置词必须兼容；525不会召回530",
        }
    )
    b2c_evidence = dict((catalog_anchor.b2c_evidence if catalog_anchor else {}) or {})
    c2b_evidence = dict((catalog_anchor.c2b_evidence if catalog_anchor else {}) or {})
    derivation = dict((catalog_anchor.derivation if catalog_anchor else {}) or {})
    pricing_only = bool(derivation.get("pricing_is_independent_from_selection"))
    if pricing_only:
        # Pricing explains market value only.  Profit ceilings and acquire/do
        # not acquire decisions belong to the selection module.
        for key in (
            "profitable_c2b_ceiling_yuan",
            "profitability_clamp_used",
            "selection_profit_gap_yuan",
        ):
            derivation.pop(key, None)

    seven_element_ledger = [
        {
            "element": "标准车型/年款",
            "input": f"{elements.get('model_year') or '-'} {elements.get('standard_vehicle') or '-'}",
            "treatment": "只允许同款同年作为内部价格主锚；相似车系不继承价格",
            "status": "STRICT_MATCH" if catalog_anchor else "NO_STRICT_INTERNAL_ANCHOR",
        },
        {
            "element": "上牌时间",
            "input": elements.get("registration_date"),
            "treatment": "按目标与每条可比车上牌月份差逐月修正",
            "factor": comparable_adjustment.get("registration_factor"),
            "status": "PRICED_IN_COMPARABLE_ADJUSTMENT",
        },
        {
            "element": "里程",
            "input": elements.get("mileage_wan_km"),
            "treatment": "相对可比车里程逐车修正，不使用车系统一里程价",
            "factor": comparable_adjustment.get("mileage_factor"),
            "status": "PRICED_IN_COMPARABLE_ADJUSTMENT",
        },
        {
            "element": "城市",
            "input": elements.get("city"),
            "treatment": "同城证据优先；跨城证据降权，三方挂牌同时按城市过滤",
            "status": "MATCH_WEIGHT_AND_EXTERNAL_FILTER",
        },
        {
            "element": "过户次数",
            "input": elements.get("transfer_count"),
            "treatment": "按与可比车过户次数差修正",
            "factor": comparable_adjustment.get("transfer_factor"),
            "status": "PRICED_IN_COMPARABLE_ADJUSTMENT",
        },
        {
            "element": "颜色",
            "input": elements.get("color"),
            "treatment": "用于当前三方车源过滤和证据匹配；证据不足时不虚构固定颜色金额",
            "status": "EXTERNAL_FILTER_NO_FABRICATED_FIXED_COEFFICIENT",
        },
        {
            "element": "车况",
            "input": elements.get("condition_grade"),
            "treatment": (
                "按检测等级修正当前市场可成交价格"
                if pricing_only
                else "按检测等级修正可比价格，并计入整备费和风险准备金"
            ),
            "factor": comparable_adjustment.get("condition_factor"),
            "status": (
                "MARKET_PRICE_CONDITION_ADJUSTMENT"
                if pricing_only
                else "PRICE_AND_COST_ADJUSTMENT"
            ),
        },
    ]

    score = 20 if catalog_anchor else 0
    b2c_support = int((catalog_anchor.b2c_support if catalog_anchor else 0) or 0)
    c2b_support = int((catalog_anchor.c2b_support if catalog_anchor else 0) or 0)
    b2c_recency = _number(catalog_anchor.b2c_recency_days if catalog_anchor else None)
    c2b_recency = _number(catalog_anchor.c2b_recency_days if catalog_anchor else None)
    if b2c_support >= 5 and b2c_recency is not None and b2c_recency <= 180:
        score += 25
    elif b2c_support > 0:
        score += 12
    if c2b_support >= 5 and c2b_recency is not None and c2b_recency <= 120:
        score += 20
    elif c2b_support > 0:
        score += 10
    source_count = int(_number(result.get("external_source_count")) or 0)
    same_year_source_count = int(_number(result.get("external_same_year_source_count")) or 0)
    dispersion = _number(result.get("external_source_dispersion"))
    if source_count >= 2 and same_year_source_count >= 2 and (dispersion or 0) <= 0.18:
        score += 20
    elif source_count > 0:
        score += 8
    if all(elements.get(key) not in (None, "") for key in elements):
        score += 15
    score = min(score, 100)
    decision = "AUTO_QUOTE" if score >= 80 else "QUOTE_WITH_REVIEW" if score >= 60 else "MANUAL_REVIEW"

    why = [
        f"车型身份锁定为{identity.get('model_year') or elements.get('model_year')}款"
        f"{identity.get('series') or ''} {identity.get('trim') or elements.get('standard_vehicle') or ''}，"
        "没有使用same_series_year主锚。",
        f"B2C内部同款同年有效样本{b2c_support}条，最近证据{b2c_recency if b2c_recency is not None else '-'}天，"
        f"七要素和时效修正后的中枢为{_yuan((catalog_anchor.b2c_yuan if catalog_anchor else None))}。",
        f"三方当前挂牌中枢为{_yuan(external_listing)}，校准谈价和挂牌偏高后成交代理为{_yuan(external_proxy)}"
        + (f"，折扣约{asking_discount:.1%}。" if asking_discount is not None else "。"),
        f"最终B2C成交价取{_yuan(b2c)}；挂牌价取{_yuan(listing)}，保留谈价空间但不把挂牌价当成交价。",
        (
            f"C2B内部同款同年有效样本{c2b_support}条，结合当前收车成交与本车七要素修正后，"
            f"实际收车价为{_yuan(c2b)}，市场最高收车价为{_yuan(result.get('max_c2b_acquisition_price'))}。"
            if pricing_only
            else f"C2B内部同款同年有效样本{c2b_support}条，结合B2C可售价格、整备/物流/资金/销售/风险和最低利润后，"
            f"实际收车价为{_yuan(c2b)}，最高可收不超过{_yuan(result.get('max_c2b_acquisition_price'))}。"
        ),
    ]

    rejected = [
        {
            "evidence": "官方指导价",
            "reason": "新车指导价与当前二手车流通价偏离，禁止作为价格锚",
        },
        {
            "evidence": "same_series_year",
            "reason": "同车系配置价差过大，仅可用于身份排错，禁止作为价格主锚",
        },
        {
            "evidence": "三方挂牌价直接当成交价",
            "reason": "挂牌包含议价空间，必须先学习成交折扣并做七要素修正",
        },
        {
            "evidence": "过时内部成交原价",
            "reason": "历史成交必须经过报价时点之前的时间衰减，不能原价照搬",
        },
    ]

    return {
        "format_version": "v195_appraiser_decision_record_v1",
        "review_mode": "APPRAISER_PRICE_BOOK",
        "target_side": str(target_side).upper(),
        "identity": identity,
        "seven_elements": elements,
        "final_price_ladder_yuan": {
            "recommended_listing": listing,
            "expected_b2c_transaction": b2c,
            "b2c_range": [
                _number(result.get("expected_b2c_transaction_price_low")),
                _number(result.get("expected_b2c_transaction_price_high")),
            ],
            "expected_c2b": c2b,
            "c2b_range": [
                _number(result.get("expected_final_c2b_price_low")),
                _number(result.get("expected_final_c2b_price_high")),
            ],
            "first_c2b_offer": _number(result.get("recommended_first_offer")),
            "max_c2b": _number(result.get("max_c2b_acquisition_price")),
        },
        "evidence": {
            "internal_b2c": b2c_evidence,
            "internal_c2b": c2b_evidence,
            "catalog_derivation": derivation,
            "external_asking_market": {
                "asking_price_yuan": external_listing,
                "transaction_proxy_yuan": external_proxy,
                "asking_to_transaction_discount_ratio": asking_discount,
                "source_count": source_count,
                "same_year_source_count": same_year_source_count,
                "cross_source_dispersion_ratio": dispersion,
                "sources": _source_parts(source_refs),
            },
            "tminus1_residual_review": residual,
        },
        "seven_element_adjustment_ledger": seven_element_ledger,
        "selection_boundary": {
            "owner": "SELECTION_MODULE" if pricing_only else "LEGACY_COMBINED_POLICY",
            "used_to_change_pricing_quote": (
                False
                if pricing_only
                else bool(result.get("c2b_profitability_clamp_used"))
            ),
        },
        "rejected_anchors": rejected,
        "confidence": {
            "evidence_score": score,
            "decision": decision,
            "runtime_confidence": result.get("knowledge_confidence"),
            "manual_review_required": decision == "MANUAL_REVIEW",
            "boundary": "价格可信不等于证据无限；低样本、来源分歧或非标准车况必须明确转人工。",
        },
        "why_this_price": why,
        "one_sentence": "".join(why),
        "invariants": {
            "b2c_not_below_c2b": bool(b2c is not None and c2b is not None and b2c >= c2b),
            "same_series_year_primary_anchor": False,
            "official_guide_price_used": False,
            "external_asking_price_used_as_transaction_truth": False,
        },
    }
