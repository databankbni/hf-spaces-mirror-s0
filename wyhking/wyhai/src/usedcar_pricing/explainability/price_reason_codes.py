#!/usr/bin/env python3
"""Central reason-code catalog for price explanations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class ReasonCodeDefinition:
    code: str
    name_zh: str
    name_en: str
    business_template: str
    frontend_visible: bool = True
    severity: str = "INFO"


class ReasonCode(str, Enum):
    ROUTE_REGULAR_MAINSTREAM = "ROUTE_REGULAR_MAINSTREAM"
    ROUTE_NEAR_NEW_CAR = "ROUTE_NEAR_NEW_CAR"
    ROUTE_LOW_PRICE_OLD_CAR = "ROUTE_LOW_PRICE_OLD_CAR"
    ROUTE_COLD_MODEL = "ROUTE_COLD_MODEL"
    ROUTE_NEW_ENERGY = "ROUTE_NEW_ENERGY"
    ROUTE_MODIFIED_CAR = "ROUTE_MODIFIED_CAR"
    ROUTE_MAJOR_ACCIDENT = "ROUTE_MAJOR_ACCIDENT"
    ROUTE_FLOOD_OR_FIRE = "ROUTE_FLOOD_OR_FIRE"
    ROUTE_MANUAL_REVIEW = "ROUTE_MANUAL_REVIEW"

    RETRIEVAL_EXACT_SAME_TRIM = "RETRIEVAL_EXACT_SAME_TRIM"
    RETRIEVAL_SAME_MODEL_YEAR = "RETRIEVAL_SAME_MODEL_YEAR"
    RETRIEVAL_SAME_CITY = "RETRIEVAL_SAME_CITY"
    RETRIEVAL_SAME_COLOR = "RETRIEVAL_SAME_COLOR"
    RETRIEVAL_SAME_CONDITION = "RETRIEVAL_SAME_CONDITION"
    RETRIEVAL_MILEAGE_WITHIN_10000_KM = "RETRIEVAL_MILEAGE_WITHIN_10000_KM"
    RETRIEVAL_AGE_WITHIN_0_5_YEAR = "RETRIEVAL_AGE_WITHIN_0_5_YEAR"
    RETRIEVAL_RECENT_TRANSACTION = "RETRIEVAL_RECENT_TRANSACTION"
    RETRIEVAL_NATIONAL_SAME_TRIM_FALLBACK = "RETRIEVAL_NATIONAL_SAME_TRIM_FALLBACK"
    RETRIEVAL_ADJACENT_TRIM_FALLBACK = "RETRIEVAL_ADJACENT_TRIM_FALLBACK"
    RETRIEVAL_PARENT_TRIM_YEAR_EVIDENCE = "RETRIEVAL_PARENT_TRIM_YEAR_EVIDENCE"

    COMPARABLE_ACCEPT_HIGHEST_QUALITY = "COMPARABLE_ACCEPT_HIGHEST_QUALITY"
    COMPARABLE_ACCEPT_EXACT_CLUSTER = "COMPARABLE_ACCEPT_EXACT_CLUSTER"
    COMPARABLE_ACCEPT_SOURCE_COMPONENT = "COMPARABLE_ACCEPT_SOURCE_COMPONENT"
    COMPARABLE_REJECT_WRONG_TRIM = "COMPARABLE_REJECT_WRONG_TRIM"
    COMPARABLE_REJECT_WRONG_MODEL_YEAR = "COMPARABLE_REJECT_WRONG_MODEL_YEAR"
    COMPARABLE_REJECT_CONDITION_CONFLICT = "COMPARABLE_REJECT_CONDITION_CONFLICT"
    COMPARABLE_REJECT_ENERGY_TYPE_CONFLICT = "COMPARABLE_REJECT_ENERGY_TYPE_CONFLICT"
    COMPARABLE_REJECT_MAJOR_ACCIDENT_CONFLICT = "COMPARABLE_REJECT_MAJOR_ACCIDENT_CONFLICT"
    COMPARABLE_REJECT_PRICE_OUTLIER_LOW = "COMPARABLE_REJECT_PRICE_OUTLIER_LOW"
    COMPARABLE_REJECT_PRICE_OUTLIER_HIGH = "COMPARABLE_REJECT_PRICE_OUTLIER_HIGH"
    COMPARABLE_REJECT_TOO_OLD = "COMPARABLE_REJECT_TOO_OLD"
    COMPARABLE_REJECT_MILEAGE_DISTANCE_TOO_LARGE = "COMPARABLE_REJECT_MILEAGE_DISTANCE_TOO_LARGE"
    COMPARABLE_REJECT_AGE_DISTANCE_TOO_LARGE = "COMPARABLE_REJECT_AGE_DISTANCE_TOO_LARGE"
    COMPARABLE_REJECT_CITY_EVIDENCE_TOO_WEAK = "COMPARABLE_REJECT_CITY_EVIDENCE_TOO_WEAK"
    COMPARABLE_REJECT_DUPLICATE_VEHICLE = "COMPARABLE_REJECT_DUPLICATE_VEHICLE"
    COMPARABLE_REJECT_DUPLICATE_LIFECYCLE = "COMPARABLE_REJECT_DUPLICATE_LIFECYCLE"
    COMPARABLE_REJECT_LOW_DATA_QUALITY = "COMPARABLE_REJECT_LOW_DATA_QUALITY"
    COMPARABLE_REJECT_LOW_RANKER_SCORE = "COMPARABLE_REJECT_LOW_RANKER_SCORE"
    COMPARABLE_REJECT_SOURCE_NOT_RELIABLE = "COMPARABLE_REJECT_SOURCE_NOT_RELIABLE"

    BASELINE_WINNER_TAKES_ALL = "BASELINE_WINNER_TAKES_ALL"
    BASELINE_ROBUST_LOG_SOURCE_BLEND = "BASELINE_ROBUST_LOG_SOURCE_BLEND"
    BASELINE_HIERARCHICAL_SHRINKAGE = "BASELINE_HIERARCHICAL_SHRINKAGE"
    BASELINE_PURCHASE_TO_SOLD_BRIDGE = "BASELINE_PURCHASE_TO_SOLD_BRIDGE"

    MODEL_ADJUSTMENT_NO_RESIDUAL_MODEL = "MODEL_ADJUSTMENT_NO_RESIDUAL_MODEL"
    MODEL_ADJUSTMENT_CLIPPED_LOW = "MODEL_ADJUSTMENT_CLIPPED_LOW"
    MODEL_ADJUSTMENT_CLIPPED_HIGH = "MODEL_ADJUSTMENT_CLIPPED_HIGH"
    MODEL_ADJUSTMENT_OTHER_FEATURES = "MODEL_ADJUSTMENT_OTHER_FEATURES"
    MODEL_ADJUSTMENT_NONLINEAR_INTERACTION_REMAINDER = "MODEL_ADJUSTMENT_NONLINEAR_INTERACTION_REMAINDER"

    INTERVAL_NARROW_MANY_EXACT_COMPARABLES = "INTERVAL_NARROW_MANY_EXACT_COMPARABLES"
    INTERVAL_NARROW_LOW_PRICE_DISPERSION = "INTERVAL_NARROW_LOW_PRICE_DISPERSION"
    INTERVAL_NARROW_RECENT_EVIDENCE = "INTERVAL_NARROW_RECENT_EVIDENCE"
    INTERVAL_WIDE_FEW_COMPARABLES = "INTERVAL_WIDE_FEW_COMPARABLES"
    INTERVAL_WIDE_PARENT_LEVEL_EVIDENCE = "INTERVAL_WIDE_PARENT_LEVEL_EVIDENCE"
    INTERVAL_WIDE_STALE_EVIDENCE = "INTERVAL_WIDE_STALE_EVIDENCE"
    INTERVAL_WIDE_HIGH_PRICE_DISPERSION = "INTERVAL_WIDE_HIGH_PRICE_DISPERSION"
    INTERVAL_WIDE_UNKNOWN_CONDITION = "INTERVAL_WIDE_UNKNOWN_CONDITION"
    INTERVAL_WIDE_GLOBAL_BRIDGE_USED = "INTERVAL_WIDE_GLOBAL_BRIDGE_USED"
    INTERVAL_WIDE_MODEL_BASELINE_DISAGREEMENT = "INTERVAL_WIDE_MODEL_BASELINE_DISAGREEMENT"
    INTERVAL_WIDE_HIGH_HISTORICAL_ERROR = "INTERVAL_WIDE_HIGH_HISTORICAL_ERROR"

    CONFIDENCE_HIGH_EXACT_STABLE_RECENT = "CONFIDENCE_HIGH_EXACT_STABLE_RECENT"
    CONFIDENCE_MEDIUM_LIMITED_EXACT_EVIDENCE = "CONFIDENCE_MEDIUM_LIMITED_EXACT_EVIDENCE"
    CONFIDENCE_LOW_WEAK_OR_WIDE_EVIDENCE = "CONFIDENCE_LOW_WEAK_OR_WIDE_EVIDENCE"
    CONFIDENCE_MANUAL_NO_RELIABLE_EVIDENCE = "CONFIDENCE_MANUAL_NO_RELIABLE_EVIDENCE"
    CONFIDENCE_RISK_MODEL_NOT_AVAILABLE = "CONFIDENCE_RISK_MODEL_NOT_AVAILABLE"

    DATA_QUALITY_MARKET_CLEAN = "DATA_QUALITY_MARKET_CLEAN"
    DATA_QUALITY_UNKNOWN_CONDITION = "DATA_QUALITY_UNKNOWN_CONDITION"
    DATA_QUALITY_MAJOR_RISK = "DATA_QUALITY_MAJOR_RISK"
    DATA_QUALITY_FUTURE_EVIDENCE_BLOCKED = "DATA_QUALITY_FUTURE_EVIDENCE_BLOCKED"
    DATA_QUALITY_CANDIDATE_TRACE_TRUNCATED = "DATA_QUALITY_CANDIDATE_TRACE_TRUNCATED"

    MANUAL_REVIEW_NO_COMPARABLE = "MANUAL_REVIEW_NO_COMPARABLE"
    MANUAL_REVIEW_MAJOR_RISK = "MANUAL_REVIEW_MAJOR_RISK"
    MANUAL_REVIEW_WIDE_PRICE_CLOUD = "MANUAL_REVIEW_WIDE_PRICE_CLOUD"
    MANUAL_REVIEW_PRODUCTION_COSTS_MISSING = "MANUAL_REVIEW_PRODUCTION_COSTS_MISSING"


def _definition(code: ReasonCode, zh: str, en: str, template: str, severity: str = "INFO") -> ReasonCodeDefinition:
    return ReasonCodeDefinition(code.value, zh, en, template, True, severity)


CATALOG = [
    _definition(ReasonCode.ROUTE_REGULAR_MAINSTREAM, "常规主流车", "Regular mainstream", "车辆未命中特殊风险或专项场景，进入常规定价链路。"),
    _definition(ReasonCode.ROUTE_NEAR_NEW_CAR, "准新车", "Near-new car", "车龄不超过{threshold}年，按准新车场景解释。"),
    _definition(ReasonCode.ROUTE_LOW_PRICE_OLD_CAR, "低价老车", "Low-price old car", "车龄或价格达到低价老车阈值。"),
    _definition(ReasonCode.ROUTE_COLD_MODEL, "冷门车型", "Cold model", "有效历史证据数量不足，进入冷门车型场景。", "WARN"),
    _definition(ReasonCode.ROUTE_NEW_ENERGY, "新能源车", "New energy vehicle", "动力或款型信息表明车辆为新能源车。"),
    _definition(ReasonCode.ROUTE_MODIFIED_CAR, "改装车", "Modified car", "车辆存在明确改装信息。", "WARN"),
    _definition(ReasonCode.ROUTE_MAJOR_ACCIDENT, "重大事故车", "Major accident", "车况字段表明存在重大事故风险。", "ERROR"),
    _definition(ReasonCode.ROUTE_FLOOD_OR_FIRE, "泡水或火烧车", "Flood or fire", "车况字段表明存在泡水或火烧风险。", "ERROR"),
    _definition(ReasonCode.ROUTE_MANUAL_REVIEW, "人工复核", "Manual review", "证据不足或风险过高，必须人工复核。", "WARN"),
    _definition(ReasonCode.RETRIEVAL_EXACT_SAME_TRIM, "精确同款", "Exact trim", "候选车与目标车款型一致。"),
    _definition(ReasonCode.RETRIEVAL_SAME_MODEL_YEAR, "同年款", "Same model year", "候选车与目标车年款一致。"),
    _definition(ReasonCode.RETRIEVAL_SAME_CITY, "同城", "Same city", "候选车与目标车城市一致。"),
    _definition(ReasonCode.RETRIEVAL_SAME_COLOR, "同颜色", "Same color", "候选车与目标车颜色一致。"),
    _definition(ReasonCode.RETRIEVAL_SAME_CONDITION, "同车况", "Same condition", "候选车与目标车车况等级一致。"),
    _definition(ReasonCode.RETRIEVAL_MILEAGE_WITHIN_10000_KM, "里程差一万公里内", "Mileage within 10,000 km", "候选车与目标车里程差不超过1万公里。"),
    _definition(ReasonCode.RETRIEVAL_AGE_WITHIN_0_5_YEAR, "车龄差半年内", "Age within 0.5 year", "候选车与目标车车龄差不超过0.5年。"),
    _definition(ReasonCode.RETRIEVAL_RECENT_TRANSACTION, "近期成交", "Recent transaction", "候选价格在180天内可用。"),
    _definition(ReasonCode.RETRIEVAL_NATIONAL_SAME_TRIM_FALLBACK, "全国同款回退", "National same-trim fallback", "同城证据不足，使用全国同款证据。"),
    _definition(ReasonCode.RETRIEVAL_ADJACENT_TRIM_FALLBACK, "相邻款型回退", "Adjacent-trim fallback", "精确款型证据不足，使用相邻款型。", "WARN"),
    _definition(ReasonCode.RETRIEVAL_PARENT_TRIM_YEAR_EVIDENCE, "同款同年父级借力", "Parent trim-year evidence", "精确同质簇稀疏，向同款同年同车况父级借力。"),
    _definition(ReasonCode.COMPARABLE_ACCEPT_HIGHEST_QUALITY, "采用最高质量候选", "Accept highest-quality candidate", "候选质量分排名第一，被用于单点价格。"),
    _definition(ReasonCode.COMPARABLE_ACCEPT_EXACT_CLUSTER, "采用精确同质簇候选", "Accept exact-cluster candidate", "候选属于精确同质车簇。"),
    _definition(ReasonCode.COMPARABLE_ACCEPT_SOURCE_COMPONENT, "采用来源价格组件", "Accept source component", "来源级价格组件参与稳健融合。"),
    _definition(ReasonCode.COMPARABLE_REJECT_WRONG_TRIM, "款型不一致", "Wrong trim", "候选款型与目标车不一致。", "WARN"),
    _definition(ReasonCode.COMPARABLE_REJECT_WRONG_MODEL_YEAR, "年款不一致", "Wrong model year", "候选年款与目标车不一致。", "WARN"),
    _definition(ReasonCode.COMPARABLE_REJECT_CONDITION_CONFLICT, "车况冲突", "Condition conflict", "候选车况与目标车不一致。", "WARN"),
    _definition(ReasonCode.COMPARABLE_REJECT_ENERGY_TYPE_CONFLICT, "动力类型冲突", "Energy conflict", "候选动力类型与目标车不一致。", "ERROR"),
    _definition(ReasonCode.COMPARABLE_REJECT_MAJOR_ACCIDENT_CONFLICT, "重大事故冲突", "Major-accident conflict", "候选存在重大事故风险。", "ERROR"),
    _definition(ReasonCode.COMPARABLE_REJECT_PRICE_OUTLIER_LOW, "异常低价", "Low price outlier", "候选价格低于稳定价格云。", "WARN"),
    _definition(ReasonCode.COMPARABLE_REJECT_PRICE_OUTLIER_HIGH, "异常高价", "High price outlier", "候选价格高于稳定价格云。", "WARN"),
    _definition(ReasonCode.COMPARABLE_REJECT_TOO_OLD, "证据过旧", "Evidence too old", "候选证据超过允许时效。", "WARN"),
    _definition(ReasonCode.COMPARABLE_REJECT_MILEAGE_DISTANCE_TOO_LARGE, "里程差过大", "Mileage distance too large", "候选里程与目标车差异过大。", "WARN"),
    _definition(ReasonCode.COMPARABLE_REJECT_AGE_DISTANCE_TOO_LARGE, "车龄差过大", "Age distance too large", "候选车龄与目标车差异过大。", "WARN"),
    _definition(ReasonCode.COMPARABLE_REJECT_CITY_EVIDENCE_TOO_WEAK, "城市证据弱", "Weak city evidence", "城市不同且缺少足够全国同款支持。", "WARN"),
    _definition(ReasonCode.COMPARABLE_REJECT_DUPLICATE_VEHICLE, "重复车辆", "Duplicate vehicle", "候选与已保留候选为同一车辆。", "WARN"),
    _definition(ReasonCode.COMPARABLE_REJECT_DUPLICATE_LIFECYCLE, "重复生命周期", "Duplicate lifecycle", "候选为同一车辆生命周期的重复价格。", "WARN"),
    _definition(ReasonCode.COMPARABLE_REJECT_LOW_DATA_QUALITY, "数据质量低", "Low data quality", "候选未通过市场知识质量门槛。", "ERROR"),
    _definition(ReasonCode.COMPARABLE_REJECT_LOW_RANKER_SCORE, "排序分较低", "Low ranker score", "候选可召回但未成为当前单点价格来源。"),
    _definition(ReasonCode.COMPARABLE_REJECT_SOURCE_NOT_RELIABLE, "来源不可靠", "Unreliable source", "候选来源不允许作为强价格证据。", "WARN"),
    _definition(ReasonCode.BASELINE_WINNER_TAKES_ALL, "最高质量候选单点", "Winner-takes-all baseline", "当前严格时序链路使用质量分第一候选作为统计基线。"),
    _definition(ReasonCode.BASELINE_ROBUST_LOG_SOURCE_BLEND, "稳健对数多源融合", "Robust log source blend", "来源价格在对数空间按证据、时效和稳定性加权融合。"),
    _definition(ReasonCode.BASELINE_HIERARCHICAL_SHRINKAGE, "层级收缩", "Hierarchical shrinkage", "精确簇向同款同年父级进行透明收缩。"),
    _definition(ReasonCode.BASELINE_PURCHASE_TO_SOLD_BRIDGE, "收售折扣桥", "Purchase-to-sold bridge", "使用历史收车价与售出价比例连接C2B与B2C价格角色。"),
    _definition(ReasonCode.MODEL_ADJUSTMENT_NO_RESIDUAL_MODEL, "未启用残差模型", "No residual model", "当前报价没有树模型残差调整，调整金额为0。"),
    _definition(ReasonCode.MODEL_ADJUSTMENT_CLIPPED_LOW, "模型下调被裁剪", "Model adjustment clipped low", "模型原始下调超过允许范围。", "WARN"),
    _definition(ReasonCode.MODEL_ADJUSTMENT_CLIPPED_HIGH, "模型上调被裁剪", "Model adjustment clipped high", "模型原始上调超过允许范围。", "WARN"),
    _definition(ReasonCode.MODEL_ADJUSTMENT_OTHER_FEATURES, "其他特征", "Other features", "非主要特征贡献合并展示。"),
    _definition(ReasonCode.MODEL_ADJUSTMENT_NONLINEAR_INTERACTION_REMAINDER, "非线性交互余项", "Nonlinear interaction remainder", "用于确保特征金额与最终模型调整完全对账。"),
    _definition(ReasonCode.INTERVAL_NARROW_MANY_EXACT_COMPARABLES, "精确可比车充足", "Many exact comparables", "精确可比车数量充足，区间可收窄。"),
    _definition(ReasonCode.INTERVAL_NARROW_LOW_PRICE_DISPERSION, "价格离散度低", "Low price dispersion", "可比车价格离散度低，区间可收窄。"),
    _definition(ReasonCode.INTERVAL_NARROW_RECENT_EVIDENCE, "近期证据", "Recent evidence", "近期价格证据充足，区间可收窄。"),
    _definition(ReasonCode.INTERVAL_WIDE_FEW_COMPARABLES, "可比车较少", "Few comparables", "有效可比车数量较少，区间扩大。", "WARN"),
    _definition(ReasonCode.INTERVAL_WIDE_PARENT_LEVEL_EVIDENCE, "使用父级证据", "Parent-level evidence", "使用同款同年父级证据，区间扩大。", "WARN"),
    _definition(ReasonCode.INTERVAL_WIDE_STALE_EVIDENCE, "证据较旧", "Stale evidence", "最新证据距今较久，区间扩大。", "WARN"),
    _definition(ReasonCode.INTERVAL_WIDE_HIGH_PRICE_DISPERSION, "价格离散度高", "High price dispersion", "可比车价格离散度较高，区间扩大。", "WARN"),
    _definition(ReasonCode.INTERVAL_WIDE_UNKNOWN_CONDITION, "车况未知", "Unknown condition", "车况未知，区间扩大。", "WARN"),
    _definition(ReasonCode.INTERVAL_WIDE_GLOBAL_BRIDGE_USED, "使用全局折扣桥", "Global bridge used", "细粒度收售比例不足，使用全局折扣桥。", "WARN"),
    _definition(ReasonCode.INTERVAL_WIDE_MODEL_BASELINE_DISAGREEMENT, "模型与基线分歧", "Model-baseline disagreement", "模型与统计基线分歧较大，区间扩大。", "WARN"),
    _definition(ReasonCode.INTERVAL_WIDE_HIGH_HISTORICAL_ERROR, "历史误差高", "High historical error", "该车型历史误差较高，区间扩大。", "WARN"),
    _definition(ReasonCode.CONFIDENCE_HIGH_EXACT_STABLE_RECENT, "高置信", "High confidence", "精确、稳定且较新的证据支持当前价格。"),
    _definition(ReasonCode.CONFIDENCE_MEDIUM_LIMITED_EXACT_EVIDENCE, "中置信", "Medium confidence", "证据可用，但精确数量、时效或稳定性未达到高置信。"),
    _definition(ReasonCode.CONFIDENCE_LOW_WEAK_OR_WIDE_EVIDENCE, "低置信", "Low confidence", "证据层级较弱或价格区间较宽。", "WARN"),
    _definition(ReasonCode.CONFIDENCE_MANUAL_NO_RELIABLE_EVIDENCE, "人工复核", "Manual confidence", "没有足够可靠证据支持自动单点报价。", "ERROR"),
    _definition(ReasonCode.CONFIDENCE_RISK_MODEL_NOT_AVAILABLE, "风险模型未接入", "Risk model unavailable", "尚无风险模型，expected APE等概率字段保持为空。"),
    _definition(ReasonCode.DATA_QUALITY_MARKET_CLEAN, "通过市场清洗", "Market clean", "候选通过市场知识基础清洗。"),
    _definition(ReasonCode.DATA_QUALITY_UNKNOWN_CONDITION, "车况未知", "Unknown condition", "候选事故等风险字段无异常，但检测评级缺失。", "WARN"),
    _definition(ReasonCode.DATA_QUALITY_MAJOR_RISK, "重大车况风险", "Major condition risk", "候选存在事故、泡水、火烧、调表或D/E评级。", "ERROR"),
    _definition(ReasonCode.DATA_QUALITY_FUTURE_EVIDENCE_BLOCKED, "未来证据已阻断", "Future evidence blocked", "候选知识可用时间晚于报价时间，禁止参与。", "ERROR"),
    _definition(ReasonCode.DATA_QUALITY_CANDIDATE_TRACE_TRUNCATED, "候选轨迹截断", "Candidate trace truncated", "审计样本仅保留前N名候选，完整召回数量另行记录。", "WARN"),
    _definition(ReasonCode.MANUAL_REVIEW_NO_COMPARABLE, "无可靠可比车", "No reliable comparable", "没有报价时点之前可用的可靠可比车。", "ERROR"),
    _definition(ReasonCode.MANUAL_REVIEW_MAJOR_RISK, "重大车况风险复核", "Major-risk review", "重大事故等风险车辆需要人工判断。", "ERROR"),
    _definition(ReasonCode.MANUAL_REVIEW_WIDE_PRICE_CLOUD, "价格云过宽", "Wide price cloud review", "同质候选价格云过宽，需要人工复核。", "WARN"),
    _definition(ReasonCode.MANUAL_REVIEW_PRODUCTION_COSTS_MISSING, "经营成本未接入", "Business costs missing", "真实整备、资金、风险和目标利润未接入，不能作为最终审批收车价。", "WARN"),
]

CATALOG_BY_CODE = {item.code: item for item in CATALOG}


def export_catalog(path: str | Path) -> pd.DataFrame:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([asdict(item) for item in CATALOG]).sort_values("code")
    frame.to_csv(output, index=False)
    return frame


def label(code: str) -> str:
    item = CATALOG_BY_CODE.get(code)
    return item.name_zh if item else code

