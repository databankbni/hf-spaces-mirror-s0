from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


FORBIDDEN_FEATURES = {
    "purchase_price",
    "sale_price",
    "purchase_price_wan",
    "sale_price_wan",
    "purchase_to_guide_ratio",
    "sale_to_guide_ratio",
    "true_price",
    "pred_price",
    "abs_error",
    "ape",
    "exclude_reason",
    "price_ratio_sale_to_purchase",
}

TARGET_BY_TASK = {
    "c2b": "purchase_price",
    "b2c": "sale_price",
}

VALID_FLAG_BY_TASK = {
    "c2b": "is_valid_for_c2b",
    "b2c": "is_valid_for_b2c",
}

RAG_FEATURES = [
    "rag_top1_price",
    "rag_top3_mean_price",
    "rag_top5_mean_price",
    "rag_top10_mean_price",
    "rag_top5_median_price",
    "rag_top10_median_price",
    "rag_top5_min_price",
    "rag_top5_max_price",
    "rag_top5_std_price",
    "rag_top5_count",
    "rag_top10_count",
    "rag_same_model_id_count",
    "rag_same_series_count",
    "rag_same_city_count",
    "rag_same_source_count",
    "rag_distance_mean",
    "rag_confidence_score",
    "rag_match_level",
    "rag_confidence",
]

FEATURE_SETS = {
    "F0_proxy": [
        "series",
        "car_age_proxy",
        "color",
        "city",
        "transfer_count",
        "mileage_wan_km",
    ],
    "F0_real_age": [
        "series",
        "age_for_training",
        "color",
        "city",
        "transfer_count",
        "mileage_wan_km",
    ],
    "F1": [
        "series",
        "age_for_training",
        "color",
        "city",
        "transfer_count",
        "mileage_wan_km",
        "model_id",
        "brand",
        "vehicle_model",
        "category_type",
        "is_new_energy_raw",
        "energy_type_inferred",
        "brand_series",
        "brand_series_year",
    ],
    "F2": [
        "series",
        "age_for_training",
        "color",
        "city",
        "transfer_count",
        "mileage_wan_km",
        "model_id",
        "brand",
        "vehicle_model",
        "category_type",
        "is_new_energy_raw",
        "energy_type_inferred",
        "brand_series",
        "brand_series_year",
        "displacement_text",
        "trim_keywords",
        "luxury_variant_flag",
        "long_wheelbase_flag",
        "four_wheel_drive_flag",
        "performance_variant_flag",
        "new_energy_flag",
        "luxury_category_flag",
        "domestic_flag",
        "joint_venture_flag",
        "imported_or_luxury_flag",
    ],
    "F3": [
        "series",
        "age_for_training",
        "color",
        "city",
        "transfer_count",
        "mileage_wan_km",
        "model_id",
        "brand",
        "vehicle_model",
        "category_type",
        "is_new_energy_raw",
        "energy_type_inferred",
        "brand_series",
        "brand_series_year",
        "displacement_text",
        "trim_keywords",
        "luxury_variant_flag",
        "long_wheelbase_flag",
        "four_wheel_drive_flag",
        "performance_variant_flag",
        "new_energy_flag",
        "luxury_category_flag",
        "domestic_flag",
        "joint_venture_flag",
        "imported_or_luxury_flag",
        "model_sample_count",
        "series_sample_count",
        "brand_sample_count",
        "city_series_sample_count",
        "city_brand_series_sample_count",
    ],
    "F4": [
        "series",
        "age_for_training",
        "color",
        "city",
        "transfer_count",
        "mileage_wan_km",
        "model_id",
        "brand",
        "vehicle_model",
        "category_type",
        "is_new_energy_raw",
        "energy_type_inferred",
        "brand_series",
        "brand_series_year",
        "displacement_text",
        "trim_keywords",
        "luxury_variant_flag",
        "long_wheelbase_flag",
        "four_wheel_drive_flag",
        "performance_variant_flag",
        "new_energy_flag",
        "luxury_category_flag",
        "domestic_flag",
        "joint_venture_flag",
        "imported_or_luxury_flag",
        "model_sample_count",
        "series_sample_count",
        "brand_sample_count",
        "city_series_sample_count",
        "city_brand_series_sample_count",
        "guide_price_min_wan",
        "guide_price_max_wan",
        "guide_price_mid_wan",
        "guide_price_match_confidence",
        "guide_price_match_level",
        "guide_price_year",
        "guide_price_missing_flag",
    ],
    "F4_source": [
        "series",
        "age_for_training",
        "color",
        "city",
        "transfer_count",
        "mileage_wan_km",
        "model_id",
        "brand",
        "vehicle_model",
        "category_type",
        "is_new_energy_raw",
        "energy_type_inferred",
        "brand_series",
        "brand_series_year",
        "displacement_text",
        "trim_keywords",
        "luxury_variant_flag",
        "long_wheelbase_flag",
        "four_wheel_drive_flag",
        "performance_variant_flag",
        "new_energy_flag",
        "luxury_category_flag",
        "domestic_flag",
        "joint_venture_flag",
        "imported_or_luxury_flag",
        "model_sample_count",
        "series_sample_count",
        "brand_sample_count",
        "city_series_sample_count",
        "city_brand_series_sample_count",
        "guide_price_min_wan",
        "guide_price_max_wan",
        "guide_price_mid_wan",
        "guide_price_match_confidence",
        "guide_price_match_level",
        "guide_price_year",
        "guide_price_missing_flag",
        "source_dataset",
        "sale_price_source",
    ],
}

FEATURE_SETS["F5"] = FEATURE_SETS["F4_source"] + RAG_FEATURES


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    features: list[str]
    missing: list[str]
    categorical: list[str]
    numeric: list[str]


def available_feature_spec(df_columns: Iterable[str], feature_set: str, task: str) -> FeatureSpec:
    if feature_set not in FEATURE_SETS:
        raise KeyError(f"未知特征组: {feature_set}")
    columns = set(df_columns)
    raw_features = list(FEATURE_SETS[feature_set])
    if task != "b2c":
        raw_features = [c for c in raw_features if c != "sale_price_source"]
    missing = [c for c in raw_features if c not in columns]
    features = [c for c in raw_features if c in columns and c not in FORBIDDEN_FEATURES]
    categorical = []
    numeric = []
    for c in features:
        if c in {"rag_confidence_score", "rag_distance_mean"} or c.startswith("rag_top") or c.startswith("rag_same") or c.endswith("_count"):
            numeric.append(c)
        elif c in {
            "car_age_proxy",
            "age_for_training",
            "transfer_count",
            "mileage_wan_km",
            "mileage_km",
            "guide_price_min_wan",
            "guide_price_max_wan",
            "guide_price_mid_wan",
            "guide_price_match_confidence",
            "guide_price_year",
            "model_sample_count",
            "series_sample_count",
            "brand_sample_count",
            "city_series_sample_count",
            "city_brand_series_sample_count",
        }:
            numeric.append(c)
        else:
            categorical.append(c)
    return FeatureSpec(feature_set, features, missing, categorical, numeric)

