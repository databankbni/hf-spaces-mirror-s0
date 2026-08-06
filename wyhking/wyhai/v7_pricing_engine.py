"""v7 layered pricing engine for the AI used-car pricing assistant.

This module keeps the existing Flask app shape intact while adding a safer
runtime path:

user text -> vehicle catalog normalization -> comparable retrieval -> layered
model routing -> point/range price + review reasons.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
DEFAULT_REGISTRY_PATH = ROOT / "config" / "model_registry.json"
PREDICTION_LOG_PATH = ROOT / "feedback_records" / "pricing_prediction_log.jsonl"

RAG_COLUMNS = [
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
    "rag_distance_mean",
    "rag_confidence_score",
    "rag_match_level"
]

TRAIN_INDEX_COLUMNS = [
    "source_dataset",
    "source_id",
    "split",
    "target_price",
    "model_id",
    "series_id",
    "brand",
    "series",
    "vehicle_model",
    "source_category",
    "model_year",
    "first_license_year",
    "city",
    "color",
    "mileage_wan_km",
    "mileage_km",
    "transfer_count",
    "energy_type",
    "is_new_energy",
    "estimate_year",
    "real_car_age_years",
    "car_age_proxy",
    "age_for_training",
    "age_source",
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
    "brand_series_sample_count",
    "city_brand_series_sample_count",
    "condition_group",
    "good_condition_strict_flag",
    "good_condition_loose_flag",
    "target_task"
]


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return default
        # Chinese mileage usually appears as "5.2万公里"; keep the numeric part.
        m = re.search(r"-?\d+(?:\.\d+)?", text)
        if not m:
            return default
        value = m.group(0)
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    number = _safe_float(value, None)
    if number is None:
        return default
    return int(number)


def _norm_text(value: Any) -> str:
    text = "" if value is None or (isinstance(value, float) and math.isnan(value)) else str(value)
    return (
        text.lower()
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
        .replace("（", "(")
        .replace("）", ")")
        .replace("款", "")
        .strip()
    )


def _yuan_to_wan(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(float(value) / 10000, 2)


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _materialize_b64_file(path: Path) -> Path:
    """Materialize a base64 text artifact to /tmp for HuggingFace git deploys.

    HF Spaces rejects binary blobs in normal git pushes. The project already uses
    .b64 assets for uploaded reports, so model/index artifacts can use the same
    pattern without requiring git-lfs/Xet in local development.
    """
    if path.exists() and not str(path).endswith(".b64"):
        return path
    # Local development often keeps the real gzip/pkl artifact while the
    # registry points at its `.b64` deployment name. Prefer the real artifact
    # when it is present instead of silently falling into legacy/fallback logic.
    if str(path).endswith(".b64"):
        raw_path = Path(str(path)[:-4])
        if raw_path.exists():
            return raw_path
    b64_path = path if str(path).endswith(".b64") else Path(str(path) + ".b64")
    if not b64_path.exists():
        return path
    cache_dir = Path(os.environ.get("PRICING_ARTIFACT_CACHE", "/tmp/pricing_artifacts"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_name = b64_path.name[:-4] if b64_path.name.endswith(".b64") else b64_path.name
    out_path = cache_dir / out_name
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path
    raw = base64.b64decode(b64_path.read_text(encoding="utf-8"))
    out_path.write_bytes(raw)
    return out_path


def _write_jsonl(path: Path, record: Dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception:
        # Prediction logging must never break pricing.
        pass


def _model_feature_names(model: Any) -> List[str]:
    preprocessor = getattr(model, "named_steps", {}).get("preprocessor") if hasattr(model, "named_steps") else None
    if preprocessor is not None and hasattr(preprocessor, "feature_names_in_"):
        return list(preprocessor.feature_names_in_)
    return []


@lru_cache(maxsize=1)
def load_registry() -> Dict[str, Any]:
    registry_path = Path(os.environ.get("PRICING_MODEL_REGISTRY", DEFAULT_REGISTRY_PATH))
    if not registry_path.is_absolute():
        registry_path = ROOT / registry_path
    return _read_json(registry_path)


@lru_cache(maxsize=8)
def load_model(model_key: str) -> Any:
    registry = load_registry()
    model_cfg = registry["models"][model_key]
    path = Path(model_cfg["artifact_path"])
    if not path.is_absolute():
        path = ROOT / path
    path = _materialize_b64_file(path)
    if not path.exists():
        raise FileNotFoundError(f"Model artifact missing: {path}")
    return joblib.load(path)


@lru_cache(maxsize=4)
def load_manifest(path_text: str) -> Dict[str, Any]:
    path = Path(path_text)
    if not path.is_absolute():
        path = ROOT / path
    return _read_json(path)


@lru_cache(maxsize=1)
def load_vehicle_catalog() -> pd.DataFrame:
    registry = load_registry()
    model_path = ROOT / registry["vehicle_catalog"]["model"]
    if not model_path.exists():
        raise FileNotFoundError(
            f"Vehicle catalog not found: {model_path}. Run scripts/build_vehicle_catalog_from_history.py first."
        )
    df = pd.read_csv(model_path)
    try:
        legacy_path = ROOT / "data" / "最近六月定价最终价格单.csv"
        if legacy_path.exists():
            legacy_cols = {"品牌", "车系", "年款", "车型", "车型ID", "里程"}
            legacy = pd.read_csv(legacy_path, usecols=lambda c: c in legacy_cols)
            if {"品牌", "车系", "年款", "车型", "车型ID"}.issubset(legacy.columns):
                legacy = legacy.dropna(subset=["品牌", "车系", "年款", "车型ID"])
                legacy["车型ID"] = pd.to_numeric(legacy["车型ID"], errors="coerce")
                legacy["年款"] = pd.to_numeric(legacy["年款"], errors="coerce")
                legacy = legacy.dropna(subset=["车型ID", "年款"])
                legacy["车型"] = legacy["车型"].fillna("").astype(str).str.strip()
                legacy_grouped = legacy.groupby(["车型ID", "年款", "品牌", "车系", "车型"], dropna=True).agg(
                    sample_count=("车型", "size"),
                    median_mileage_wan=("里程", "median") if "里程" in legacy.columns else ("车型", "size"),
                ).reset_index()
                existing_keys = set()
                if {"model_id", "model_year", "model_name"}.issubset(df.columns):
                    for _, row in df[["model_id", "model_year", "model_name"]].dropna(subset=["model_id", "model_year"]).iterrows():
                        existing_keys.add((
                            int(float(row["model_id"])),
                            int(float(row["model_year"])),
                            _norm_text(row.get("model_name", "")),
                        ))
                legacy_grouped["_catalog_key"] = [
                    (int(float(mid)), int(float(year)), _norm_text(name))
                    for mid, year, name in zip(legacy_grouped["车型ID"], legacy_grouped["年款"], legacy_grouped["车型"])
                ]
                legacy_grouped = legacy_grouped[~legacy_grouped["_catalog_key"].isin(existing_keys)]
                if not legacy_grouped.empty:
                    legacy_df = pd.DataFrame({
                        "id": legacy_grouped["车型ID"].map(lambda x: f"model_{int(x)}"),
                        "brand_id": legacy_grouped["品牌"].map(lambda x: f"brand_{x}"),
                        "series_ref_id": "",
                        "model_year": legacy_grouped["年款"],
                        "model_name": legacy_grouped["车型"],
                        "trim_name": "",
                        "displacement": "",
                        "energy_type": "",
                        "official_price_min": np.nan,
                        "official_price_max": np.nan,
                        "source": "legacy_model_search_csv",
                        "model_id": legacy_grouped["车型ID"],
                        "series_id": np.nan,
                        "brand": legacy_grouped["品牌"],
                        "series": legacy_grouped["车系"],
                        "sample_count": legacy_grouped["sample_count"],
                        "median_price": np.nan,
                        "p25_price": np.nan,
                        "p75_price": np.nan,
                        "median_mileage_wan": legacy_grouped["median_mileage_wan"],
                    })
                    df = pd.concat([df, legacy_df], ignore_index=True, sort=False)

        # 车型库 CSV 可能少量漏掉线上可比索引里已有的标准车型（例如 2026 Model Y 后轮驱动版）。
        # 用 train-only comparable index 补齐 catalog，保证“车型搜索”和“模型标准化”口径一致。
        idx = load_comparable_index("c2b")
        needed = {"model_id", "series_id", "brand", "series", "model_year", "vehicle_model"}
        if needed.issubset(idx.columns):
            known_keys = set()
            if {"model_id", "model_year", "model_name"}.issubset(df.columns):
                for _, row in df[["model_id", "model_year", "model_name"]].dropna(subset=["model_id", "model_year"]).iterrows():
                    known_keys.add((
                        int(float(row["model_id"])),
                        int(float(row["model_year"])),
                        _norm_text(row.get("model_name", "")),
                    ))
            key_df = idx[["model_id", "model_year", "vehicle_model"]].copy()
            key_df["_catalog_key"] = [
                (
                    int(float(mid)) if pd.notna(mid) else None,
                    int(float(year)) if pd.notna(year) else None,
                    _norm_text(name),
                )
                for mid, year, name in zip(key_df["model_id"], key_df["model_year"], key_df["vehicle_model"])
            ]
            supplement = idx[~key_df["_catalog_key"].isin(known_keys)].copy()
            if not supplement.empty:
                agg = {
                    "series_id": "first",
                    "brand": "first",
                    "series": "first",
                    "model_year": "first",
                    "vehicle_model": "first",
                }
                if "target_price" in supplement.columns:
                    agg["target_price"] = ["count", "median"]
                if "mileage_wan_km" in supplement.columns:
                    agg["mileage_wan_km"] = "median"
                if "energy_type" in supplement.columns:
                    agg["energy_type"] = "first"
                grouped = supplement.groupby("model_id", dropna=True).agg(agg)
                grouped.columns = ["_".join(col).strip("_") if isinstance(col, tuple) else col for col in grouped.columns]
                grouped = grouped.reset_index()
                supplement_df = pd.DataFrame({
                    "id": grouped["model_id"].map(lambda x: f"model_{int(x)}"),
                    "brand_id": grouped["brand_first"].map(lambda x: f"brand_{x}"),
                    "series_ref_id": grouped["series_id_first"].map(lambda x: f"series_{int(x)}" if pd.notna(x) else ""),
                    "model_year": grouped["model_year_first"],
                    "model_name": grouped["vehicle_model_first"],
                    "trim_name": "",
                    "displacement": "",
                    "energy_type": grouped.get("energy_type_first", ""),
                    "official_price_min": np.nan,
                    "official_price_max": np.nan,
                    "source": "comparable_index_v7",
                    "model_id": grouped["model_id"],
                    "series_id": grouped["series_id_first"],
                    "brand": grouped["brand_first"],
                    "series": grouped["series_first"],
                    "sample_count": grouped.get("target_price_count", 0),
                    "median_price": grouped.get("target_price_median", np.nan),
                    "p25_price": np.nan,
                    "p75_price": np.nan,
                    "median_mileage_wan": grouped.get("mileage_wan_km_median", np.nan),
                })
                df = pd.concat([df, supplement_df], ignore_index=True, sort=False)
    except Exception as exc:
        print(f"[v7_pricing] vehicle catalog supplement skipped: {exc}")
    for col in ["brand", "series", "model_name", "energy_type", "displacement", "trim_name"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()
            df[f"{col}_norm"] = df[col].map(_norm_text)
    if "model_year" in df.columns:
        df["model_year"] = pd.to_numeric(df["model_year"], errors="coerce")
    if "model_id" in df.columns:
        df["model_id"] = pd.to_numeric(df["model_id"], errors="coerce")
    if "series_id" in df.columns:
        df["series_id"] = pd.to_numeric(df["series_id"], errors="coerce")
    for col in ["sample_count", "median_price", "p25_price", "p75_price", "median_mileage_wan"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@lru_cache(maxsize=4)
def load_comparable_index(task: str) -> pd.DataFrame:
    registry = load_registry()
    key = "c2b_index" if task == "c2b" else "b2c_index"
    path = Path(registry["rag"][key])
    if not path.is_absolute():
        path = ROOT / path
    path = _materialize_b64_file(path)
    if not path.exists():
        raise FileNotFoundError(f"Comparable index missing: {path}")
    header = pd.read_csv(path, nrows=0)
    usecols = [c for c in TRAIN_INDEX_COLUMNS if c in header.columns]
    df = pd.read_csv(path, usecols=usecols)
    if "split" in df.columns:
        df = df[df["split"].astype(str).str.lower().eq("train")].copy()
    for col in ["brand", "series", "vehicle_model", "city", "color", "energy_type", "condition_group"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()
    numeric_cols = [
        "target_price",
        "model_id",
        "series_id",
        "model_year",
        "first_license_year",
        "mileage_wan_km",
        "mileage_km",
        "transfer_count",
        "age_for_training"
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["target_price"])


def parse_vehicle_text(text: str) -> Dict[str, Any]:
    text = text or ""
    year = None
    m = re.search(r"(20\d{2}|19\d{2})\s*款?", text)
    if m:
        year = int(m.group(1))
    else:
        m2 = re.search(r"(?<!\d)(\d{2})\s*款", text)
        if m2:
            yy = int(m2.group(1))
            year = 2000 + yy if yy <= 40 else 1900 + yy
    displacement = ""
    d = re.search(r"(\d\.\d\s*[tTlL])", text)
    if d:
        displacement = d.group(1).upper().replace(" ", "")
    energy = ""
    if re.search(r"纯电|EV|电动|Model\s?[3YSX]", text, re.I):
        energy = "EV"
    elif re.search(r"插混|PHEV|DM-i|DM-p|Hi4|Hi4-Z", text, re.I):
        energy = "PHEV"
    elif re.search(r"增程|EREV", text, re.I):
        energy = "EREV"
    elif re.search(r"混动|HEV", text, re.I):
        energy = "HEV"
    trim_keywords = []
    for kw in ["豪华", "尊贵", "旗舰", "运动", "M运动", "AMG", "RS", "S line", "行政", "典雅", "长续航", "Performance", "四驱", "两驱", "长轴", "标轴", "Pro", "Max", "Ultra"]:
        if re.search(re.escape(kw), text, re.I):
            trim_keywords.append(kw)
    return {
        "model_year": year,
        "displacement_text": displacement,
        "energy_type": energy,
        "trim_keywords": ",".join(trim_keywords),
        "luxury_variant_flag": int(bool(re.search(r"AMG|迈巴赫|Maybach|M运动|RS|GTS|Turbo|Cayenne|卫士|揽胜", text, re.I))),
        "long_wheelbase_flag": int(bool(re.search(r"长轴|Li\\b|\\bL\\b", text, re.I))),
        "four_wheel_drive_flag": int(bool(re.search(r"四驱|4MATIC|xDrive|quattro|AWD", text, re.I))),
        "performance_variant_flag": int(bool(re.search(r"AMG|M运动|RS|GTS|Performance|Turbo", text, re.I))),
        "new_energy_flag": int(bool(re.search(r"纯电|EV|PHEV|DM-i|DM-p|增程|Hi4|Model", text, re.I)))
    }


def normalize_vehicle(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw_text = " ".join(
        str(payload.get(k, "") or "")
        for k in ["brand", "series", "model", "modelName", "vehicle_model", "car_model", "query", "rawText"]
    )
    parsed = parse_vehicle_text(raw_text)
    brand = str(payload.get("brand") or "").strip()
    series = str(payload.get("series") or "").strip()
    model_text = str(payload.get("model") or payload.get("modelName") or payload.get("vehicle_model") or payload.get("car_model") or "").strip()
    model_id = _safe_int(payload.get("modelId") or payload.get("model_id") or payload.get("standardModelId"))
    series_id = _safe_int(payload.get("seriesId") or payload.get("series_id"))
    model_year = _safe_int(
        payload.get("vehicle_model_year")
        or payload.get("vehicleModelYear")
        or payload.get("modelYear")
        or payload.get("year")
        or payload.get("model_year")
        or parsed.get("model_year")
    )

    catalog = load_vehicle_catalog()
    candidates = catalog.copy()
    match_method = "fuzzy"
    confidence = 0.0
    trusted_model_id_match = False

    if model_id is not None:
        exact = candidates[candidates["model_id"].eq(model_id)]
        if not exact.empty:
            narrowed = exact.copy()
            year_conflict = False
            if model_year:
                year_match = narrowed[narrowed["model_year"].eq(model_year)]
                if not year_match.empty:
                    narrowed = year_match
                else:
                    year_conflict = True
            raw_norm = _norm_text(raw_text)
            if raw_norm and not narrowed.empty:
                text_match = narrowed[
                    narrowed["model_name_norm"].apply(lambda name: bool(name) and (name in raw_norm or raw_norm in name))
                ]
                if not text_match.empty:
                    narrowed = text_match
            # The catalog can contain duplicated model_id rows across years or
            # trims. If the supplied id conflicts with the user-visible year,
            # do not let that id override the text; fall back to brand/series
            # matching so a 2021 BMW i/3/5-series cannot become a 2024 Tesla/BMW row.
            if not year_conflict:
                candidates = narrowed
                match_method = "model_id_refined" if len(narrowed) < len(exact) else "model_id"
                confidence = 0.99 if len(candidates) == 1 else 0.90
                trusted_model_id_match = True
            else:
                match_method = "model_id_year_conflict"
                confidence = 0.0

    if not trusted_model_id_match:
        if brand:
            candidates = candidates[candidates["brand_norm"].eq(_norm_text(brand))]
            if not candidates.empty:
                confidence += 0.25
        if series:
            series_norm = _norm_text(series)
            narrowed = candidates[candidates["series_norm"].eq(series_norm)] if not candidates.empty else candidates
            if not narrowed.empty:
                candidates = narrowed
                confidence += 0.30
        if model_year:
            narrowed = candidates[candidates["model_year"].eq(model_year)] if not candidates.empty else candidates
            if not narrowed.empty:
                candidates = narrowed
                confidence += 0.20
        model_norm = _norm_text(model_text)
        if model_norm:
            exact_model = candidates[candidates["model_name_norm"].eq(model_norm)] if not candidates.empty else candidates
            if not exact_model.empty:
                candidates = exact_model
                confidence += 0.20
                match_method = "exact_text"
            else:
                contains = candidates[candidates["model_name_norm"].str.contains(model_norm, regex=False, na=False)] if not candidates.empty else candidates
                if not contains.empty:
                    candidates = contains
                    confidence += 0.10
                    match_method = "contains_text"
                else:
                    # 用户常输入“2026款 特斯拉Model Y 后轮驱动版”这种完整车型串；
                    # 车型库里的款型名只有“后轮驱动版”。反向检查款型名是否出现在
                    # 完整输入里，避免退化成按样本数选择“标准版”。
                    raw_norm = _norm_text(raw_text)
                    reverse_contains = candidates[
                        candidates["model_name_norm"].apply(lambda name: bool(name) and name in raw_norm)
                    ] if not candidates.empty else candidates
                    if not reverse_contains.empty:
                        candidates = reverse_contains
                        confidence += 0.20
                        match_method = "raw_contains_model_name"

    if candidates.empty:
        return {
            "matched": False,
            "need_manual_confirm": True,
            "match_confidence": 0.0,
            "match_method": "no_match",
            "match_reason": "车型库无稳定候选",
            "candidates": [],
            "parsed": parsed
        }

    if "model_id" in candidates.columns:
        try:
            c2b_counts = load_comparable_index("c2b").groupby("model_id").size()
            b2c_counts = load_comparable_index("b2c").groupby("model_id").size()
            rag_counts = c2b_counts.add(b2c_counts, fill_value=0)
            candidates = candidates.copy()
            candidates["_rag_count"] = candidates["model_id"].map(rag_counts).fillna(0)
        except Exception:
            candidates = candidates.copy()
            candidates["_rag_count"] = 0
    else:
        candidates = candidates.copy()
        candidates["_rag_count"] = 0
    candidates["_sample_count_num"] = pd.to_numeric(candidates.get("sample_count", 0), errors="coerce").fillna(0)
    # A tiny RAG hit count (for example 1-2 rows) is weaker than a richer
    # catalog/history candidate. Use combined coverage first, then RAG count.
    candidates["_coverage_count"] = np.maximum(candidates["_rag_count"], candidates["_sample_count_num"])
    candidates = candidates.sort_values(["_coverage_count", "_rag_count", "_sample_count_num", "median_price"], ascending=[False, False, False, False]).head(5)
    top = candidates.iloc[0].to_dict()
    if model_id is None:
        confidence = min(confidence + (0.10 if len(candidates) == 1 else 0.0), 0.95)
        if confidence == 0:
            confidence = 0.55
    need_manual = confidence < float(load_registry()["routing"]["min_auto_model_match_confidence"]) or len(candidates) > 3
    candidate_rows = [
        {
            "model_id": str(int(row["model_id"])) if pd.notna(row.get("model_id")) else "",
            "series_id": str(int(row["series_id"])) if pd.notna(row.get("series_id")) else "",
            "brand": row.get("brand", ""),
            "series": row.get("series", ""),
            "model_year": int(row["model_year"]) if pd.notna(row.get("model_year")) else None,
            "model_name": row.get("model_name", ""),
            "sample_count": int(row.get("sample_count", 0) or 0)
        }
        for _, row in candidates.iterrows()
    ]
    return {
        "matched": True,
        "need_manual_confirm": need_manual,
        "brand_id": top.get("brand_id", ""),
        "brand_name": top.get("brand", ""),
        "series_id": str(int(top["series_id"])) if pd.notna(top.get("series_id")) else "",
        "series_name": top.get("series", ""),
        "model_id": str(int(top["model_id"])) if pd.notna(top.get("model_id")) else "",
        "model_name": top.get("model_name", ""),
        "model_year": int(top["model_year"]) if pd.notna(top.get("model_year")) else model_year,
        "energy_type": top.get("energy_type", "") or parsed.get("energy_type") or payload.get("energy_type") or "",
        "match_confidence": round(float(confidence), 4),
        "match_method": match_method,
        "match_reason": "车型库标准化匹配",
        "candidates": candidate_rows,
        "parsed": parsed,
        "catalog_row": top
    }


def _compute_distance(index: pd.DataFrame, query: Dict[str, Any]) -> pd.Series:
    distance = pd.Series(0.0, index=index.index)
    mileage = _safe_float(query.get("mileage_wan_km"))
    if mileage is not None and "mileage_wan_km" in index.columns:
        distance += (index["mileage_wan_km"].fillna(mileage).sub(mileage).abs() / 10.0).clip(0, 3)
    age = _safe_float(query.get("age_for_training"))
    if age is not None and "age_for_training" in index.columns:
        distance += (index["age_for_training"].fillna(age).sub(age).abs() / 5.0).clip(0, 2)
    transfer = _safe_float(query.get("transfer_count"))
    if transfer is not None and "transfer_count" in index.columns:
        distance += (index["transfer_count"].fillna(transfer).sub(transfer).abs() / 3.0).clip(0, 1)
    city = _norm_text(query.get("city"))
    if city:
        distance += np.where(index["city"].map(_norm_text).eq(city), 0.0, 0.2)
    color = _norm_text(query.get("color"))
    if color:
        distance += np.where(index["color"].map(_norm_text).eq(color), 0.0, 0.05)
    return distance


def retrieve_comparables(task: str, standard_vehicle: Dict[str, Any], request_features: Dict[str, Any], top_k: int = 10) -> Dict[str, Any]:
    index = load_comparable_index(task)
    model_id = _safe_int(standard_vehicle.get("model_id"))
    series_id = _safe_int(standard_vehicle.get("series_id"))
    brand = standard_vehicle.get("brand_name") or request_features.get("brand") or ""
    series = standard_vehicle.get("series_name") or request_features.get("series") or ""
    model_year = _safe_int(standard_vehicle.get("model_year") or request_features.get("model_year"))
    energy_type = standard_vehicle.get("energy_type") or request_features.get("energy_type") or ""

    levels: List[Tuple[str, pd.Series]] = []
    if model_id is not None and "model_id" in index.columns:
        levels.append(("same_model_id", index["model_id"].eq(model_id)))
    if brand and series and model_year is not None:
        levels.append(
            (
                "same_brand_series_year",
                index["brand"].eq(brand) & index["series"].eq(series) & index["model_year"].eq(model_year)
            )
        )
    if brand and series:
        levels.append(("same_brand_series", index["brand"].eq(brand) & index["series"].eq(series)))
    if series_id is not None and "series_id" in index.columns:
        levels.append(("same_series_id", index["series_id"].eq(series_id)))
    if brand and energy_type:
        levels.append(("same_brand_energy", index["brand"].eq(brand) & index["energy_type"].eq(energy_type)))

    selected = pd.DataFrame()
    level_name = "no_match"
    for level, mask in levels:
        selected = index[mask].copy()
        if len(selected) >= 3 or (level == "same_model_id" and len(selected) > 0):
            level_name = level
            break
    if selected.empty:
        selected = index.sample(min(top_k, len(index)), random_state=42).copy() if len(index) else pd.DataFrame()
        level_name = "global_train_fallback" if not selected.empty else "no_match"

    if selected.empty:
        return _empty_rag_features()

    selected["distance"] = _compute_distance(selected, request_features)
    selected = selected.sort_values(["distance", "target_price"], ascending=[True, True]).head(top_k)
    prices = selected["target_price"].astype(float)
    distances = selected["distance"].astype(float)
    top5 = prices.head(5)
    count = len(selected)
    same_model_count = int(selected["model_id"].eq(model_id).sum()) if model_id is not None else 0
    same_series_count = int(selected["series"].eq(series).sum()) if series else 0
    city = request_features.get("city") or ""
    same_city_count = int(selected["city"].eq(city).sum()) if city else 0
    top5_median = float(top5.median()) if len(top5) else np.nan
    top5_iqr = float(top5.quantile(0.75) - top5.quantile(0.25)) if len(top5) >= 3 else 0.0
    top5_std = float(top5.std(ddof=0) or 0.0) if len(top5) else 0.0
    top5_dispersion = float(top5_iqr / top5_median) if top5_median and np.isfinite(top5_median) else 1.0
    confidence_score = float(max(0.0, min(1.0, 1.0 / (1.0 + distances.mean()))))
    confidence_score = float(max(0.0, confidence_score * max(0.25, 1.0 - min(top5_dispersion, 0.75))))
    if level_name in {"same_model_id", "same_brand_series_year"} and count >= 5:
        confidence = "high"
    elif level_name in {"same_brand_series", "same_series_id"} and count >= 3:
        confidence = "medium"
    elif level_name == "no_match":
        confidence = "no_match"
    else:
        confidence = "low"
    if confidence == "high" and top5_dispersion > 0.22:
        confidence = "medium"
    if confidence in {"high", "medium"} and top5_dispersion > 0.38:
        confidence = "low"

    features = {
        "rag_match_level": level_name,
        "rag_top1_price": float(prices.iloc[0]),
        "rag_top3_mean_price": float(prices.head(3).mean()),
        "rag_top5_mean_price": float(prices.head(5).mean()),
        "rag_top10_mean_price": float(prices.head(10).mean()),
        "rag_top5_median_price": top5_median,
        "rag_top10_median_price": float(prices.head(10).median()),
        "rag_top5_min_price": float(prices.head(5).min()),
        "rag_top5_max_price": float(prices.head(5).max()),
        "rag_top5_std_price": top5_std,
        "rag_top5_iqr_price": top5_iqr,
        "rag_top5_dispersion_ratio": top5_dispersion,
        "rag_top5_count": int(min(5, count)),
        "rag_top10_count": int(min(10, count)),
        "rag_same_model_id_count": same_model_count,
        "rag_same_series_count": same_series_count,
        "rag_same_city_count": same_city_count,
        "rag_distance_mean": float(distances.mean()),
        "rag_confidence_score": confidence_score
    }
    return {
        "features": features,
        "confidence": confidence,
        "match_level": level_name,
        "comparable_count": int(count),
        "topk_summary": {
            "top1_price": features["rag_top1_price"],
            "top3_mean_price": features["rag_top3_mean_price"],
            "top5_median_price": features["rag_top5_median_price"]
        },
        "ref_cars": [
            {
                "source_id": str(row.get("source_id", "")),
                "brand": row.get("brand", ""),
                "series": row.get("series", ""),
                "model": row.get("vehicle_model", ""),
                "model_year": _safe_int(row.get("model_year")),
                "mileage_wan_km": _safe_float(row.get("mileage_wan_km")),
                "city": row.get("city", ""),
                "price": _safe_float(row.get("target_price")),
                "distance": _safe_float(row.get("distance"))
            }
            for _, row in selected.head(5).iterrows()
        ]
    }


def _empty_rag_features() -> Dict[str, Any]:
    features = {col: np.nan for col in RAG_COLUMNS}
    features.update(
        {
            "rag_match_level": "no_match",
            "rag_top5_count": 0,
            "rag_top10_count": 0,
            "rag_same_model_id_count": 0,
            "rag_same_series_count": 0,
            "rag_same_city_count": 0,
            "rag_confidence_score": 0.0
        }
    )
    return {
        "features": features,
        "confidence": "no_match",
        "match_level": "no_match",
        "comparable_count": 0,
        "topk_summary": {"top1_price": None, "top3_mean_price": None, "top5_median_price": None},
        "ref_cars": []
    }


def build_base_features(payload: Dict[str, Any], standard_vehicle: Dict[str, Any], rag_features: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    parsed = standard_vehicle.get("parsed") or parse_vehicle_text(str(payload))
    catalog_row = standard_vehicle.get("catalog_row") or {}
    model_year = _safe_int(standard_vehicle.get("model_year") or payload.get("modelYear") or payload.get("year"))
    first_license_year = _safe_int(payload.get("firstLicenseYear") or payload.get("licenseYear"))
    reg_date = str(payload.get("regDate") or payload.get("reg_date") or payload.get("licenseDate") or "")
    if first_license_year is None:
        m = re.search(r"(20\d{2}|19\d{2})", reg_date)
        first_license_year = int(m.group(1)) if m else model_year
    mileage_wan = _safe_float(payload.get("mileage_wan_km") or payload.get("mileage") or payload.get("mileageWanKm"))
    if mileage_wan is None and _safe_float(payload.get("mileage_km")) is not None:
        mileage_wan = _safe_float(payload.get("mileage_km")) / 10000
    mileage_km = mileage_wan * 10000 if mileage_wan is not None else None
    estimate_year = datetime.now().year
    age = _safe_float(payload.get("age_for_training"))
    if age is None and first_license_year:
        age = max(0.0, estimate_year - first_license_year)
    if age is None and model_year:
        age = max(0.0, estimate_year - model_year)
    transfer_count = _safe_int(payload.get("transferCount") or payload.get("transfer_count"), 0)
    city = str(payload.get("city") or "").strip()
    color = str(payload.get("color") or "").strip()
    energy_type = str(payload.get("energy_type") or payload.get("energyType") or standard_vehicle.get("energy_type") or parsed.get("energy_type") or "unknown")

    missing = []
    for name, value in {
        "model_id": standard_vehicle.get("model_id"),
        "model_year": model_year,
        "mileage": mileage_wan,
        "city": city,
        "color": color
    }.items():
        if value in (None, "", "nan"):
            missing.append(name)

    brand = standard_vehicle.get("brand_name") or payload.get("brand") or ""
    series = standard_vehicle.get("series_name") or payload.get("series") or ""
    model_name = standard_vehicle.get("model_name") or payload.get("model") or payload.get("modelName") or ""
    brand_series = f"{brand}_{series}"
    brand_series_year = f"{brand_series}_{model_year or ''}"

    features = {
        "model_id": _safe_int(standard_vehicle.get("model_id")),
        "series_id": _safe_int(standard_vehicle.get("series_id")),
        "brand": brand,
        "series": series,
        "vehicle_model": model_name,
        "source_category": catalog_row.get("source_category", ""),
        "model_year": model_year,
        "first_license_year": first_license_year,
        "city": city,
        "color": color,
        "mileage_wan_km": mileage_wan,
        "mileage_km": mileage_km,
        "transfer_count": transfer_count,
        "energy_type": energy_type,
        "is_new_energy": "1" if energy_type in {"EV", "PHEV", "EREV", "HEV"} else "0",
        "estimate_year": estimate_year,
        "real_car_age_years": age,
        "car_age_proxy": max(0, estimate_year - model_year) if model_year else age,
        "age_for_training": age,
        "age_source": "runtime_first_license" if first_license_year else "runtime_model_year_proxy",
        "brand_series": brand_series,
        "brand_series_year": brand_series_year,
        "displacement_text": parsed.get("displacement_text") or catalog_row.get("displacement", ""),
        "trim_keywords": parsed.get("trim_keywords") or catalog_row.get("trim_name", ""),
        "luxury_variant_flag": parsed.get("luxury_variant_flag", 0),
        "long_wheelbase_flag": parsed.get("long_wheelbase_flag", 0),
        "four_wheel_drive_flag": parsed.get("four_wheel_drive_flag", 0),
        "performance_variant_flag": parsed.get("performance_variant_flag", 0),
        "new_energy_flag": parsed.get("new_energy_flag", 0),
        "luxury_category_flag": int(brand in {"奔驰", "宝马", "奥迪", "保时捷", "路虎", "雷克萨斯", "沃尔沃", "凯迪拉克", "捷豹"}),
        "domestic_flag": int(brand in {"比亚迪", "吉利", "长安", "奇瑞", "长城", "理想", "蔚来", "小鹏", "零跑", "问界"}),
        "joint_venture_flag": 0,
        "imported_or_luxury_flag": int(brand in {"奔驰", "宝马", "奥迪", "保时捷", "路虎", "雷克萨斯", "沃尔沃", "捷豹"}),
        "model_sample_count": catalog_row.get("sample_count", np.nan),
        "series_sample_count": catalog_row.get("sample_count", np.nan),
        "brand_sample_count": np.nan,
        "brand_series_sample_count": catalog_row.get("sample_count", np.nan),
        "city_brand_series_sample_count": np.nan
    }
    features.update(rag_features)
    return features, missing


def _choose_route(preliminary_price: Optional[float], rag_confidence: str, standard_vehicle: Dict[str, Any], missing_fields: List[str]) -> Tuple[str, str, List[str]]:
    reasons: List[str] = []
    if missing_fields:
        reasons.append("MISSING_REQUIRED_FIELDS")
    if not standard_vehicle.get("matched") or standard_vehicle.get("need_manual_confirm"):
        reasons.append("MODEL_NOT_MATCHED")
    if rag_confidence in {"low", "no_match"}:
        reasons.append("LOW_RAG_CONFIDENCE" if rag_confidence == "low" else "NO_COMPARABLE_MATCH")
    if preliminary_price is None or not np.isfinite(preliminary_price):
        reasons.append("NO_COMPARABLE_MATCH")
        return "manual_review", "manual_review", reasons
    if preliminary_price < 10000:
        reasons.append("LOW_PRICE_0_1W")
        return "manual_review", "manual_review", reasons
    if preliminary_price < 30000:
        reasons.append("LOW_PRICE_1_3W_REQUIRES_CONFIRM")
        return "low_price_specialist", "low_price_specialist", reasons
    return "main_model", "main_model", reasons


def _predict_model(model_key: str, features: Dict[str, Any]) -> Tuple[float, List[str]]:
    model = load_model(model_key)
    columns = _model_feature_names(model)
    if not columns:
        cfg = load_registry()["models"][model_key]
        manifest = load_manifest(cfg["feature_manifest"])
        columns = list(manifest.get("feature_columns", [])) + [c for c in RAG_COLUMNS if c not in manifest.get("feature_columns", [])]
    row = {col: features.get(col, np.nan) for col in columns}
    preprocessor = getattr(model, "named_steps", {}).get("preprocessor") if hasattr(model, "named_steps") else None
    numeric_columns = set()
    if preprocessor is not None:
        for name, _transformer, cols in getattr(preprocessor, "transformers_", []):
            if name == "num":
                numeric_columns.update(cols)
    for col in numeric_columns:
        if col in row:
            row[col] = _safe_float(row[col], 0.0)
    pred = float(model.predict(pd.DataFrame([row], columns=columns))[0])
    # Training scripts used log1p(target_price). Runtime pkl models therefore
    # return log-price scale; convert back when the raw prediction is clearly
    # not in yuan.
    if pred < 1000:
        pred = float(np.expm1(pred))
    return max(0.0, pred), columns


def _mileage_safety_adjustment(point: Optional[float], mileage_wan: Optional[float]) -> Tuple[Optional[float], Optional[str]]:
    """Runtime guard for out-of-distribution high-mileage cars.

    The tabular model already receives mileage, but very high-mileage inputs are
    sparse in training data. Apply a monotonic business guard so 30w/50w/100w km
    cars cannot receive almost the same quote as normal-mileage cars.
    """
    if point is None or mileage_wan is None:
        return point, None
    try:
        mileage = float(mileage_wan)
    except (TypeError, ValueError):
        return point, None
    if mileage <= 15:
        return point, None
    if mileage <= 30:
        factor = 1.0 - 0.008 * (mileage - 15)
    elif mileage <= 60:
        factor = 0.88 - 0.010 * (mileage - 30)
    else:
        factor = 0.58 - 0.002 * min(mileage - 60, 60)
    factor = max(0.42, min(1.0, factor))
    adjusted = point * factor
    return adjusted, "EXTREME_MILEAGE_ADJUSTMENT" if mileage >= 30 else "HIGH_MILEAGE_ADJUSTMENT"


def _build_interval(point: Optional[float], mode: str, rag: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], str]:
    if point is None:
        return None, None, "manual_review_no_interval"
    rag_features = rag.get("features", {})
    rag_min = _safe_float(rag_features.get("rag_top5_min_price"))
    rag_max = _safe_float(rag_features.get("rag_top5_max_price"))
    rag_count = int(_safe_float(rag_features.get("rag_top5_count"), 0) or 0)
    rag_confidence = str(rag.get("confidence") or "").lower()
    rag_match_level = str(rag.get("match_level") or "").lower()
    pct = 0.20 if mode == "low_price_specialist" else 0.12
    max_rag_pct = 0.24 if mode == "low_price_specialist" else 0.16
    use_rag_distribution = (
        rag_min
        and rag_max
        and rag_max > rag_min
        and rag_count >= 3
        and rag_confidence in {"high", "medium"}
        and rag_match_level not in {"global_train_fallback", "no_match", "weak_match"}
    )
    if use_rag_distribution:
        lower = max(min(point, rag_min), point * (1 - max_rag_pct))
        upper = min(max(point, rag_max), point * (1 + max_rag_pct))
        if lower >= upper:
            lower = point * (1 - pct)
            upper = point * (1 + pct)
            method = "rule_based_fallback"
        else:
            method = "rag_distribution_clamped"
    else:
        lower = point * (1 - pct)
        upper = point * (1 + pct)
        method = "rule_based_fallback"
    if mode == "low_price_specialist":
        lower = max(1000, min(lower, point - 1500))
        upper = max(upper, point + 1500)
    return round(lower, 0), round(upper, 0), method


def _apply_comparable_anchor_guard(point: Optional[float], rag: Dict[str, Any]) -> Tuple[Optional[float], Optional[str]]:
    """Prevent a model point from overruling strong comparable evidence.

    This is not a fixed vehicle discount. It only activates when the model's raw
    point is far outside a sufficiently specific comparable set, and it records a
    review reason so the UI does not present the quote as high-confidence.
    """
    if point is None:
        return point, None
    rag_confidence = str(rag.get("confidence") or "").lower()
    match_level = str(rag.get("match_level") or "").lower()
    if rag_confidence not in {"high", "medium"} or match_level in {"global_train_fallback", "no_match"}:
        return point, None
    features = rag.get("features") or {}
    count = int(_safe_float(features.get("rag_top5_count"), 0) or 0)
    median = _safe_float(features.get("rag_top5_median_price"))
    dispersion = _safe_float(features.get("rag_top5_dispersion_ratio"), 1.0) or 1.0
    if count < 3 or not median or median <= 0:
        return point, None
    ratio = float(point) / float(median)
    if ratio > 1.35 or ratio < 0.65:
        # If the comparable pool itself is noisy, use the median only as a
        # conservative reference and require review.
        anchored = median if dispersion <= 0.45 else (0.5 * point + 0.5 * median)
        return round(float(anchored), 0), "MODEL_RAG_DIVERGENCE_REVIEW"
    return point, None


def predict_layered_price(payload: Dict[str, Any]) -> Dict[str, Any]:
    request_id = payload.get("request_id") or payload.get("traceId") or str(uuid.uuid4())
    task = str(payload.get("task") or payload.get("target") or "both").lower()
    if task in {"purchase", "c2b_price", "收车价"}:
        tasks = ["c2b"]
    elif task in {"sale", "b2c_price", "售价"}:
        tasks = ["b2c"]
    else:
        tasks = ["c2b", "b2c"]

    standard_vehicle = normalize_vehicle(payload)
    results = {}
    all_review_reasons: List[str] = []
    first_rag: Optional[Dict[str, Any]] = None

    for current_task in tasks:
        rag = retrieve_comparables(current_task, standard_vehicle, payload)
        if first_rag is None:
            first_rag = rag
        base_features, missing_fields = build_base_features(payload, standard_vehicle, rag["features"])
        preliminary = _safe_float(rag.get("topk_summary", {}).get("top5_median_price"))
        mode, model_mode, review_reasons = _choose_route(preliminary, rag["confidence"], standard_vehicle, missing_fields)
        point: Optional[float] = None
        feature_columns: List[str] = []
        model_key = None

        if model_mode == "main_model":
            model_key = "main_c2b" if current_task == "c2b" else "main_b2c"
        elif model_mode == "low_price_specialist":
            model_key = "low_price_c2b" if current_task == "c2b" else "low_price_b2c"

        if model_key and "MISSING_REQUIRED_FIELDS" not in review_reasons and "MODEL_NOT_MATCHED" not in review_reasons:
            try:
                point, feature_columns = _predict_model(model_key, base_features)
            except Exception as exc:
                review_reasons.append("MODEL_LOAD_OR_PREDICT_FAILED")
                point = preliminary
                base_features["model_error"] = str(exc)
        elif preliminary is not None and model_mode != "manual_review":
            point = preliminary

        if model_mode == "manual_review" and preliminary is not None:
            point = preliminary
        point, mileage_adjustment_reason = _mileage_safety_adjustment(point, base_features.get("mileage_wan_km"))
        if mileage_adjustment_reason and mileage_adjustment_reason not in review_reasons:
            review_reasons.append(mileage_adjustment_reason)
        point, rag_anchor_reason = _apply_comparable_anchor_guard(point, rag)
        if rag_anchor_reason and rag_anchor_reason not in review_reasons:
            review_reasons.append(rag_anchor_reason)
        if point is not None and point < 10000 and "LOW_PRICE_0_1W" not in review_reasons:
            review_reasons.append("LOW_PRICE_0_1W")
            mode = "manual_review"
        lower, upper, interval_method = _build_interval(point, mode, rag)
        review_required = bool(review_reasons) or mode != "main_model"
        all_review_reasons.extend(review_reasons)
        results[current_task] = {
            "task": current_task,
            "pricing_mode": mode,
            "model_key": model_key,
            "point": round(point, 0) if point is not None else None,
            "lower": lower,
            "upper": upper,
            "interval_method": interval_method,
            "review_required": review_required,
            "review_reasons": sorted(set(review_reasons)),
            "feature_columns": feature_columns,
            "rag": rag
        }

        _write_jsonl(
            PREDICTION_LOG_PATH,
            {
                "request_id": request_id,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "user_input_json": payload,
                "normalized_vehicle_json": {k: v for k, v in standard_vehicle.items() if k != "catalog_row"},
                "model_version": load_registry().get("active_version"),
                "task": current_task,
                "pricing_mode": mode,
                "feature_hash": hashlib.md5(json.dumps(base_features, sort_keys=True, default=str).encode()).hexdigest(),
                "rag_features_json": rag.get("features", {}),
                "point_price": point,
                "lower_price": lower,
                "upper_price": upper,
                "review_required": review_required,
                "review_reasons": sorted(set(review_reasons))
            }
        )

    if "c2b" in results and "b2c" in results:
        c2b_point = _safe_float(results["c2b"].get("point"))
        b2c_point = _safe_float(results["b2c"].get("point"))
        if c2b_point is not None and b2c_point is not None and b2c_point < c2b_point * 1.03:
            adjusted_b2c = round(c2b_point * 1.08, 0)
            results["b2c"]["point"] = adjusted_b2c
            lower, upper, interval_method = _build_interval(adjusted_b2c, results["b2c"]["pricing_mode"], results["b2c"]["rag"])
            results["b2c"]["lower"] = lower
            results["b2c"]["upper"] = upper
            results["b2c"]["interval_method"] = interval_method
            results["b2c"]["review_required"] = True
            reasons = set(results["b2c"].get("review_reasons") or [])
            reasons.add("B2C_BELOW_C2B_ADJUSTED")
            results["b2c"]["review_reasons"] = sorted(reasons)
            all_review_reasons.append("B2C_BELOW_C2B_ADJUSTED")

    primary_task = tasks[0]
    primary = results[primary_task]
    response = {
        "success": True,
        "request_id": request_id,
        "model_version": load_registry().get("active_version", "v7_layered_2026"),
        "task": task if task in {"c2b", "b2c"} else "both",
        "pricing_mode": primary["pricing_mode"],
        "standard_vehicle": {
            "brand_id": standard_vehicle.get("brand_id", ""),
            "brand_name": standard_vehicle.get("brand_name", ""),
            "series_id": standard_vehicle.get("series_id", ""),
            "series_name": standard_vehicle.get("series_name", ""),
            "model_id": standard_vehicle.get("model_id", ""),
            "model_name": standard_vehicle.get("model_name", ""),
            "model_year": standard_vehicle.get("model_year"),
            "match_confidence": standard_vehicle.get("match_confidence", 0.0),
            "match_reason": standard_vehicle.get("match_reason", ""),
            "match_method": standard_vehicle.get("match_method", ""),
            "candidates": standard_vehicle.get("candidates", [])
        },
        "price": {
            "point": primary["point"],
            "lower": primary["lower"],
            "upper": primary["upper"],
            "currency": "CNY",
            "interval_method": primary["interval_method"]
        },
        "rag": {
            "confidence": primary["rag"]["confidence"],
            "match_level": primary["rag"]["match_level"],
            "comparable_count": primary["rag"]["comparable_count"],
            "topk_summary": primary["rag"]["topk_summary"]
        },
        "review": {
            "required": any(item["review_required"] for item in results.values()),
            "reasons": sorted(set(all_review_reasons))
        },
        "explanation": {
            "summary": "基于车型库标准化、历史可比车源和 v7 分层估价模型生成报价；低置信或低价场景会保留人工复核。",
            "factors": ["标准车型ID", "同车型/同车系可比样本", "车龄", "里程", "城市行情", "过户次数"]
        },
        "tasks": results
    }

    # Backward-compatible fields used by the existing single-page frontend.
    c2b = results.get("c2b")
    b2c = results.get("b2c")
    if c2b:
        response.update(
            {
                "c2bPrice": _yuan_to_wan(c2b["point"]),
                "c2b_price": _yuan_to_wan(c2b["point"]),
                "c2bRange": [_yuan_to_wan(c2b["lower"]), _yuan_to_wan(c2b["upper"])],
                "targetC2B": _yuan_to_wan(c2b["point"])
            }
        )
    if b2c:
        response.update(
            {
                "b2cPrice": _yuan_to_wan(b2c["point"]),
                "b2c_price": _yuan_to_wan(b2c["point"]),
                "b2cRange": [_yuan_to_wan(b2c["lower"]), _yuan_to_wan(b2c["upper"])],
                "targetB2C": _yuan_to_wan(b2c["point"])
            }
        )
    refs = primary["rag"].get("ref_cars", [])
    response["ref_cars"] = refs
    response["reason"] = response["explanation"]["summary"]
    response["pricing_engine"] = "v7_layered_2026"
    response["modelName"] = "v7.1-main/v7.2-low-price-layered"
    return response
