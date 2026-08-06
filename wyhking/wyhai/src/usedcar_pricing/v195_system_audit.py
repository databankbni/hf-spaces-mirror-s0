"""Stage-1 audit for the v195 production pricing book.

The audit is intentionally read-only with respect to the existing pricing
runtime and model artifacts.  It records what can be reproduced from the
current workspace before v195 builds any new truth, price-book, or override
layers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


ENGINE_VERSION = "v195_production_pricing_book_v1"
STAGE1_SCHEMA_VERSION = "v195.stage1.audit.v1"
DEFAULT_OUTPUT_RELATIVE = Path("artifacts/v195_production_pricing_book/stage1")

UNKNOWN_TEXT = {
    "",
    "0",
    "nan",
    "none",
    "null",
    "other",
    "unknown",
    "其它",
    "其他",
    "未知",
    "未识别",
}


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    path: Path
    file_format: str
    source: str
    price_type: str
    primary_price_column: str
    price_columns: tuple[str, ...]
    observed_at_columns: tuple[str, ...]
    transaction_at_columns: tuple[str, ...]
    duplicate_key_candidates: tuple[tuple[str, ...], ...]
    identity_columns: tuple[str, ...]
    source_confidence: str
    is_transaction_ground_truth: bool
    required: bool
    role: str
    target_definition: str | None
    clean_rolling_rule: str
    production_rule: str
    sheet_name: str | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_timestamp(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("Asia/Shanghai")
    return timestamp.isoformat()


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _schema_hash(schema: list[dict[str, str]]) -> str:
    payload = json.dumps(schema, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _git_state(root: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {
            "is_git_repository": False,
            "commit_sha": None,
            "status": "NOT_A_GIT_REPOSITORY",
            "detail": result.stderr.strip() or result.stdout.strip(),
        }
    sha = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "is_git_repository": sha.returncode == 0,
        "commit_sha": sha.stdout.strip() if sha.returncode == 0 else None,
        "status": "OK" if sha.returncode == 0 else "GIT_SHA_UNAVAILABLE",
        "repository_root": result.stdout.strip(),
    }


def source_specs(root: Path, downloads: Path) -> list[SourceSpec]:
    common_clean = (
        "Row is eligible only when its row-level availability timestamp is "
        "strictly earlier than the prediction timestamp."
    )
    external_clean = (
        "Listing is a feature, never a transaction target. Historical clean "
        "evaluation requires observed_at < prediction_at; a current snapshot "
        "must not be replayed into dates before it was observed."
    )
    return [
        SourceSpec(
            source_id="internal_b2c_transactions",
            path=root / "data/v194/daily_confirmed_b2c_sold_actuals.parquet",
            file_format="parquet",
            source="DONGCHEDI_INTERNAL",
            price_type="INTERNAL_B2C_TRANSACTION",
            primary_price_column="price_yuan",
            price_columns=("price_yuan", "price"),
            observed_at_columns=("pricing_available_at", "knowledge_available_at"),
            transaction_at_columns=("event_time",),
            duplicate_key_candidates=(
                ("daily_business_event_key",),
                ("daily_source_row_hash",),
                ("vehicle_id", "event_time", "price_yuan"),
            ),
            identity_columns=("model_id", "canonical_trim_key"),
            source_confidence="HIGHEST_INTERNAL_TRANSACTION",
            is_transaction_ground_truth=True,
            required=True,
            role="canonical_transaction_store",
            target_definition="训练1目标列：最新订单成交价",
            clean_rolling_rule=common_clean,
            production_rule="May use confirmed records available by T-1.",
        ),
        SourceSpec(
            source_id="internal_c2b_transactions",
            path=root / "data/v194/daily_confirmed_c2b_actuals.parquet",
            file_format="parquet",
            source="DONGCHEDI_INTERNAL",
            price_type="INTERNAL_C2B_TRANSACTION",
            primary_price_column="price_yuan",
            price_columns=("price_yuan", "price"),
            observed_at_columns=("pricing_available_at", "knowledge_available_at"),
            transaction_at_columns=("event_time",),
            duplicate_key_candidates=(
                ("daily_business_event_key",),
                ("daily_source_row_hash",),
                ("vehicle_id", "event_time", "price_yuan"),
            ),
            identity_columns=("model_id", "canonical_trim_key"),
            source_confidence="HIGHEST_INTERNAL_TRANSACTION",
            is_transaction_ground_truth=True,
            required=True,
            role="canonical_transaction_store",
            target_definition="训练2目标列：收车合同价",
            clean_rolling_rule=common_clean,
            production_rule="May use confirmed records available by T-1.",
        ),
        SourceSpec(
            source_id="dongchedi_current_listings",
            path=root / "data/external/dongchedi_current_usedcar_market.parquet",
            file_format="parquet",
            source="DONGCHEDI_EXTERNAL",
            price_type="DONGCHEDI_LISTING",
            primary_price_column="listing_price_yuan",
            price_columns=("listing_price_yuan", "listing_price_wan"),
            observed_at_columns=("fetched_at",),
            transaction_at_columns=(),
            duplicate_key_candidates=(("sku_id",), ("detail_url",)),
            identity_columns=("series_id", "standard_vehicle"),
            source_confidence="TRUSTED_EXTERNAL_LISTING",
            is_transaction_ground_truth=False,
            required=True,
            role="current_market_listing_evidence",
            target_definition=None,
            clean_rolling_rule=external_clean,
            production_rule="Use as current listing evidence after source discount calibration.",
        ),
        SourceSpec(
            source_id="autohome_current_listings",
            path=root / "data/external/autohome_current_usedcar_market.parquet",
            file_format="parquet",
            source="AUTOHOME",
            price_type="AUTOHOME_LISTING",
            primary_price_column="price_yuan",
            price_columns=("price_yuan", "price_wan"),
            observed_at_columns=("snapshot_date", "public_date"),
            transaction_at_columns=(),
            duplicate_key_candidates=(("listing_id",), ("source_url",)),
            identity_columns=("spec_id", "display_name"),
            source_confidence="EXTERNAL_LISTING",
            is_transaction_ground_truth=False,
            required=True,
            role="current_market_listing_evidence",
            target_definition=None,
            clean_rolling_rule=external_clean,
            production_rule="Use after duplicate, bait-price, identity, and source-bias calibration.",
        ),
        SourceSpec(
            source_id="guazi_current_listings",
            path=root / "data/knowledge/v54_guazi_used_market_listing_snapshot.parquet",
            file_format="parquet",
            source="GUAZI",
            price_type="GUAZI_LISTING",
            primary_price_column="listing_price_yuan",
            price_columns=("listing_price_yuan", "listing_price_wan"),
            observed_at_columns=("snapshot_date",),
            transaction_at_columns=(),
            duplicate_key_candidates=(("source_name", "listing_id"), ("source_url",)),
            identity_columns=("canonical_series", "trim_normalized"),
            source_confidence="EXTERNAL_LISTING",
            is_transaction_ground_truth=False,
            required=True,
            role="current_market_listing_evidence",
            target_definition=None,
            clean_rolling_rule=external_clean,
            production_rule="Use after duplicate, bait-price, identity, and source-bias calibration.",
        ),
        SourceSpec(
            source_id="latest_b2c_upload_20260710",
            path=downloads / "训练1-2026-07-10 16-44-13.xlsx",
            file_format="xlsx",
            source="DONGCHEDI_INTERNAL_UPLOAD",
            price_type="INTERNAL_B2C_TRANSACTION",
            primary_price_column="最新订单成交价",
            price_columns=("最新订单成交价", "首次展板价", "收车合同价"),
            observed_at_columns=("已售时间", "首次上架时间"),
            transaction_at_columns=("已售时间",),
            duplicate_key_candidates=(("车源货品ID",), ("车源商品ID",)),
            identity_columns=("车型ID", "车型"),
            source_confidence="RAW_INTERNAL_UPLOAD",
            is_transaction_ground_truth=True,
            required=True,
            role="raw_ingestion_input_non_additive_with_canonical_store",
            target_definition="训练1目标列：最新订单成交价",
            clean_rolling_rule=common_clean,
            production_rule="Ingest idempotently, then use only after canonical-store confirmation.",
            sheet_name="Sheet1",
        ),
        SourceSpec(
            source_id="latest_c2b_upload_20260710",
            path=downloads / "训练2-2026-07-10 16-44-16.xlsx",
            file_format="xlsx",
            source="DONGCHEDI_INTERNAL_UPLOAD",
            price_type="INTERNAL_C2B_TRANSACTION",
            primary_price_column="收车合同价",
            price_columns=("收车合同价", "首次展板价", "最新订单成交价"),
            observed_at_columns=("收车合同签订时间",),
            transaction_at_columns=("收车合同签订时间",),
            duplicate_key_candidates=(("车源货品ID",), ("车源商品ID",)),
            identity_columns=("车型ID", "车型"),
            source_confidence="RAW_INTERNAL_UPLOAD",
            is_transaction_ground_truth=True,
            required=True,
            role="raw_ingestion_input_non_additive_with_canonical_store",
            target_definition="训练2目标列：收车合同价",
            clean_rolling_rule=common_clean,
            production_rule="Ingest idempotently, then use only after canonical-store confirmation.",
            sheet_name="Sheet1",
        ),
    ]


def _parquet_schema(path: Path) -> tuple[int, list[dict[str, str]]]:
    parquet = pq.ParquetFile(path)
    schema = [
        {"name": field.name, "dtype": str(field.type)}
        for field in parquet.schema_arrow
    ]
    return int(parquet.metadata.num_rows), schema


def _xlsx_schema(path: Path, sheet_name: str | None) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    frame = pd.read_excel(path, sheet_name=sheet_name or 0)
    schema = [{"name": str(column), "dtype": str(frame[column].dtype)} for column in frame.columns]
    return frame, schema


def _read_relevant_columns(spec: SourceSpec, available: Iterable[str]) -> pd.DataFrame:
    available_set = set(available)
    requested: set[str] = {
        spec.primary_price_column,
        *spec.price_columns,
        *spec.observed_at_columns,
        *spec.transaction_at_columns,
        *spec.identity_columns,
    }
    for keys in spec.duplicate_key_candidates:
        requested.update(keys)
    if spec.file_format == "parquet" and spec.role == "canonical_transaction_store":
        requested.update(
            {
                "runtime_candidate_dedup_keep_flag",
                "market_clean_flag",
                "is_token_price",
                "price_type",
            }
        )
    requested_columns = [column for column in requested if column in available_set]
    if spec.file_format == "parquet":
        return pd.read_parquet(spec.path, columns=requested_columns)
    return pd.read_excel(spec.path, sheet_name=spec.sheet_name or 0, usecols=requested_columns)


def _as_bool(series: pd.Series, default: bool) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(default)
    normalized = series.fillna("").astype(str).str.strip().str.lower()
    true_values = {"true", "1", "yes", "y", "是"}
    false_values = {"false", "0", "no", "n", "否"}
    result = pd.Series(default, index=series.index, dtype=bool)
    result.loc[normalized.isin(true_values)] = True
    result.loc[normalized.isin(false_values)] = False
    return result


def _unknown_mask(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce").fillna(0).le(0)
    return series.fillna("").astype(str).str.strip().str.lower().isin(UNKNOWN_TEXT)


def _date_ranges(frame: pd.DataFrame, columns: Iterable[str]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for column in columns:
        if column not in frame.columns:
            continue
        values = pd.to_datetime(frame[column], errors="coerce")
        valid = values.dropna()
        output[column] = {
            "valid_count": int(valid.size),
            "missing_count": int(values.isna().sum()),
            "min": _iso_timestamp(valid.min()) if not valid.empty else None,
            "max": _iso_timestamp(valid.max()) if not valid.empty else None,
        }
    return output


def _duplicate_summary(frame: pd.DataFrame, candidates: Iterable[tuple[str, ...]]) -> dict[str, Any]:
    for keys in candidates:
        if not set(keys).issubset(frame.columns):
            continue
        key_frame = frame[list(keys)].copy()
        valid = pd.Series(True, index=frame.index)
        for column in keys:
            valid &= ~_unknown_mask(key_frame[column])
        duplicates = key_frame.loc[valid].duplicated(list(keys), keep="first")
        return {
            "key": list(keys),
            "valid_key_rows": int(valid.sum()),
            "duplicate_rows_after_first": int(duplicates.sum()),
        }
    return {"key": [], "valid_key_rows": 0, "duplicate_rows_after_first": None}


def _price_quality(spec: SourceSpec, frame: pd.DataFrame) -> dict[str, Any]:
    if spec.primary_price_column not in frame.columns:
        return {
            "primary_price_column_present": False,
            "valid_business_price_rows": 0,
            "legal_rows": 0,
        }
    price = pd.to_numeric(frame[spec.primary_price_column], errors="coerce")
    upper = 1_000_000 if spec.is_transaction_ground_truth else 2_000_000
    valid_price = price.between(3_000, upper)
    legal = valid_price.copy()
    if spec.role == "canonical_transaction_store":
        if "runtime_candidate_dedup_keep_flag" in frame:
            legal &= _as_bool(frame["runtime_candidate_dedup_keep_flag"], False)
        if "market_clean_flag" in frame:
            legal &= _as_bool(frame["market_clean_flag"], False)
        if "is_token_price" in frame:
            legal &= ~_as_bool(frame["is_token_price"], False)
    return {
        "primary_price_column_present": True,
        "missing_primary_price_rows": int(price.isna().sum()),
        "non_positive_price_rows": int(price.le(0).fillna(False).sum()),
        "out_of_business_range_rows": int((price.notna() & ~valid_price).sum()),
        "valid_business_price_rows": int(valid_price.sum()),
        "legal_rows": int(legal.sum()),
        "price_min_yuan": float(price[valid_price].min()) if valid_price.any() else None,
        "price_max_yuan": float(price[valid_price].max()) if valid_price.any() else None,
        "price_median_yuan": float(price[valid_price].median()) if valid_price.any() else None,
    }


def _identity_quality(spec: SourceSpec, frame: pd.DataFrame) -> dict[str, Any]:
    per_column: dict[str, int] = {}
    any_unknown = pd.Series(False, index=frame.index)
    present = 0
    for column in spec.identity_columns:
        if column not in frame.columns:
            per_column[column] = len(frame)
            any_unknown |= True
            continue
        present += 1
        unknown = _unknown_mask(frame[column])
        per_column[column] = int(unknown.sum())
        any_unknown |= unknown
    return {
        "identity_columns_present": present,
        "unknown_rows_by_identity_column": per_column,
        "rows_not_safe_for_exact_identity": int(any_unknown.sum()),
        "other_unknown_forbidden_for_exact_match": True,
    }


def audit_source(spec: SourceSpec) -> dict[str, Any]:
    base = {
        **{key: value for key, value in asdict(spec).items() if key != "path"},
        "path": str(spec.path),
        "exists": spec.path.exists(),
    }
    if not spec.path.exists():
        return {**base, "status": "MISSING"}

    if spec.file_format == "parquet":
        row_count, schema = _parquet_schema(spec.path)
        columns = [item["name"] for item in schema]
        frame = _read_relevant_columns(spec, columns)
    elif spec.file_format == "xlsx":
        full_frame, schema = _xlsx_schema(spec.path, spec.sheet_name)
        row_count = len(full_frame)
        columns = [item["name"] for item in schema]
        frame = _read_relevant_columns(spec, columns)
    else:
        raise ValueError(f"Unsupported source format: {spec.file_format}")

    observed_ranges = _date_ranges(frame, spec.observed_at_columns)
    transaction_ranges = _date_ranges(frame, spec.transaction_at_columns)
    maxima = [
        item["max"]
        for item in [*observed_ranges.values(), *transaction_ranges.values()]
        if item["max"] is not None
    ]
    observed_price_types: dict[str, int] = {}
    if "price_type" in frame.columns:
        observed_price_types = {
            str(key): int(value)
            for key, value in frame["price_type"].fillna("MISSING").value_counts().items()
        }
    freshness_quality: dict[str, Any] = {"policy_applies": False}
    if spec.role == "current_market_listing_evidence" and spec.observed_at_columns:
        observed_column = next(
            (column for column in spec.observed_at_columns if column in frame.columns), None
        )
        if observed_column:
            observed = pd.to_datetime(frame[observed_column], errors="coerce", utc=True)
            cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=14)
            primary_price = pd.to_numeric(
                frame.get(spec.primary_price_column, pd.Series(np.nan, index=frame.index)),
                errors="coerce",
            )
            valid_price = primary_price.between(3_000, 2_000_000)
            fresh = observed.ge(cutoff)
            freshness_quality = {
                "policy_applies": True,
                "max_age_days": 14,
                "freshness_cutoff": cutoff.isoformat(),
                "fresh_rows": int(fresh.sum()),
                "stale_or_missing_rows": int((~fresh).sum()),
                "online_eligible_price_rows": int((fresh & valid_price).sum()),
            }
    stat = spec.path.stat()
    return {
        **base,
        "status": "OK",
        "size_bytes": int(stat.st_size),
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "sha256": _sha256(spec.path),
        "row_count": int(row_count),
        "column_count": len(schema),
        "schema_sha256": _schema_hash(schema),
        "schema": schema,
        "observed_at_ranges": observed_ranges,
        "transaction_at_ranges": transaction_ranges,
        "data_cutoff": max(maxima) if maxima else None,
        "observed_price_type_counts": observed_price_types,
        "duplicate_summary": _duplicate_summary(frame, spec.duplicate_key_candidates),
        "price_quality": _price_quality(spec, frame),
        "identity_quality": _identity_quality(spec, frame),
        "freshness_quality": freshness_quality,
    }


def _tail_metrics(frame: pd.DataFrame, actual_column: str, prediction_column: str) -> dict[str, Any]:
    actual = pd.to_numeric(frame[actual_column], errors="coerce")
    predicted = pd.to_numeric(frame[prediction_column], errors="coerce")
    valid = actual.gt(0) & predicted.notna()
    actual = actual.loc[valid]
    predicted = predicted.loc[valid]
    ape = (predicted - actual).abs() / actual
    absolute_error = (predicted - actual).abs()
    top_count = int(np.ceil(len(ape) * 0.10)) if len(ape) else 0
    top_index = ape.nlargest(top_count).index if top_count else ape.index[:0]
    remainder = ape.drop(index=top_index)
    return {
        "n": int(len(ape)),
        "overall_mape": float(ape.mean()) if len(ape) else None,
        "overall_wmape": float(absolute_error.sum() / actual.sum()) if len(ape) else None,
        "bias_pct": float(((predicted - actual) / actual).mean() * 100.0) if len(ape) else None,
        "p50_ape": float(ape.quantile(0.50)) if len(ape) else None,
        "p90_ape": float(ape.quantile(0.90)) if len(ape) else None,
        "top10_count": top_count,
        "top10_percent_mape": float(ape.loc[top_index].mean()) if top_count else None,
        "top10_ape_contribution": float(ape.loc[top_index].sum() / ape.sum()) if ape.sum() else None,
        "top10_absolute_error_contribution": (
            float(absolute_error.loc[top_index].sum() / absolute_error.sum())
            if absolute_error.sum()
            else None
        ),
        "remaining90_mape": float(remainder.mean()) if len(remainder) else None,
        "error_contribution_definition": "sum(APE in largest 10% APE rows) / sum(APE in all rows)",
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _metric_row(path: Path, scope: str, prediction: str) -> dict[str, Any]:
    frame = pd.read_csv(path, low_memory=False)
    selected = frame.loc[frame["scope"].eq(scope) & frame["prediction"].eq(prediction)]
    if len(selected) != 1:
        raise RuntimeError(f"Expected one metric row in {path}: {scope}/{prediction}")
    row = selected.iloc[0].to_dict()
    return {
        key: (value.item() if isinstance(value, np.generic) else value)
        for key, value in row.items()
    }


def _trace_day_range(frame: pd.DataFrame) -> list[str | None]:
    if "day" not in frame.columns:
        return [None, None]
    days = pd.to_datetime(frame["day"], errors="coerce").dropna()
    if days.empty:
        return [None, None]
    return [str(days.min().date()), str(days.max().date())]


def _service_versions(root: Path) -> dict[str, str | None]:
    path = root / "services/v194_quote_service.py"
    text = path.read_text(encoding="utf-8")
    output: dict[str, str | None] = {"path": str(path)}
    for name in ("PRICING_ENGINE_VERSION", "MODEL_VERSION", "POLICY_VERSION"):
        match = re.search(rf"^{name}\s*=\s*[\"']([^\"']+)[\"']", text, flags=re.MULTILINE)
        output[name.lower()] = match.group(1) if match else None
    return output


def build_metric_baseline(root: Path) -> dict[str, Any]:
    b2c_metric_path = root / "results/model_results/v194_355_b2c_30d_champion_metrics.csv"
    b2c_policy_path = root / "models/v194_355/v194_355_b2c_30d_champion.policy.json"
    b2c_trace_path = root / "results/traces/v194_355_b2c_30d_champion_trace.csv"
    c2b_metric_path = root / "results/model_results/v194_369_c2b_90d_listing_discount_metrics.csv"
    c2b_policy_path = root / "models/v194_369/v194_369_c2b_90d_listing_discount.policy.json"
    c2b_trace_path = root / "results/traces/v194_369_c2b_90d_listing_discount_trace.csv"
    c2b_v367_policy_path = root / "models/v194_367/v194_367_c2b_recent_strict_trim_knn.policy.json"

    required = [
        b2c_metric_path,
        b2c_policy_path,
        b2c_trace_path,
        c2b_metric_path,
        c2b_policy_path,
        c2b_trace_path,
        c2b_v367_policy_path,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Metric baseline artifacts missing: {missing}")

    b2c_metric = _metric_row(b2c_metric_path, "rolling_30d_all", "champion_pred_yuan")
    b2c_holdout = _metric_row(b2c_metric_path, "holdout_latest_7d", "champion_pred_yuan")
    b2c_policy = _read_json(b2c_policy_path)
    b2c_trace = pd.read_csv(
        b2c_trace_path,
        usecols=["day", "actual_yuan", "champion_pred_yuan"],
        low_memory=False,
    )
    b2c_tail = _tail_metrics(b2c_trace, "actual_yuan", "champion_pred_yuan")

    c2b_metric = _metric_row(c2b_metric_path, "latest_7d_all", "listing_discount_c2b_pred_yuan")
    c2b_policy = _read_json(c2b_policy_path)
    c2b_v367_policy = _read_json(c2b_v367_policy_path)
    c2b_trace = pd.read_csv(
        c2b_trace_path,
        usecols=[
            "day",
            "actual_yuan",
            "listing_discount_c2b_pred_yuan",
            "b2c_transaction_pred_yuan",
        ],
        low_memory=False,
    )
    c2b_tail = _tail_metrics(c2b_trace, "actual_yuan", "listing_discount_c2b_pred_yuan")
    inversion = c2b_trace["actual_yuan"].gt(c2b_trace["b2c_transaction_pred_yuan"])

    b2c_consistent = abs(float(b2c_metric["mape"]) - float(b2c_tail["overall_mape"])) < 1e-12
    c2b_consistent = abs(float(c2b_metric["mape"]) - float(c2b_tail["overall_mape"])) < 1e-12
    return {
        "schema_version": STAGE1_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "generated_at": _utc_now().isoformat(),
        "target_definitions": {
            "b2c": {"source_role": "训练1", "target_column": "最新订单成交价"},
            "c2b": {"source_role": "训练2", "target_column": "收车合同价"},
        },
        "online_runtime": {
            **_service_versions(root),
            "latest_eval_entry": str(root / "scripts/run_latest_online_pricing_eval.py"),
            "audit_entry": str(root / "scripts/run_v194_223_t30_online_service_audit.py"),
            "v195_challengers_deployed": False,
        },
        "b2c": {
            "version": b2c_policy.get("version"),
            "artifact_paths": {
                "metrics": str(b2c_metric_path),
                "policy": str(b2c_policy_path),
                "trace": str(b2c_trace_path),
            },
            "rolling_30d": b2c_metric,
            "holdout_latest_7d": b2c_holdout,
            "trace_window": _trace_day_range(b2c_trace),
            "tail_metrics": b2c_tail,
            "artifact_consistency": b2c_consistent,
            "strictly_prequential_claim": bool(b2c_policy.get("strictly_prequential")),
            "deployed": bool(b2c_policy.get("deployed")),
            "target_gap_to_5pct_percentage_points": (float(b2c_metric["mape"]) - 0.05) * 100.0,
            "clean_rolling_eligibility": (
                "BASELINE_ONLY_NOT_STAGE5_CERTIFIED: aggregate includes its model-selection window; "
                "current-market evidence also requires row-level as-of verification."
            ),
        },
        "c2b": {
            "version": c2b_policy.get("version"),
            "artifact_paths": {
                "metrics": str(c2b_metric_path),
                "policy": str(c2b_policy_path),
                "trace": str(c2b_trace_path),
            },
            "latest_7d": c2b_metric,
            "trace_window": _trace_day_range(c2b_trace),
            "tail_metrics": c2b_tail,
            "artifact_consistency": c2b_consistent,
            "deployed": bool(c2b_policy.get("deployed")),
            "target_gap_to_5pct_percentage_points": (float(c2b_metric["mape"]) - 0.05) * 100.0,
            "b2c_anchor_inversion_before": {
                "count": int(inversion.sum()),
                "n": int(len(inversion)),
                "rate": float(inversion.mean()),
                "definition": "actual C2B transaction > old predicted B2C transaction anchor",
            },
            "previous_strict_trim_baseline": {
                "version": c2b_v367_policy.get("version"),
                "mape": c2b_v367_policy.get("latest_7d_mape"),
                "wmape": c2b_v367_policy.get("latest_7d_wmape"),
            },
            "reported_best_observation_not_currently_reproducible": {
                "mape": 0.06707346636,
                "wmape": 0.05476039486,
                "status": "NOT_AN_OFFICIAL_BASELINE",
                "reason": (
                    "The original no-inspection-score artifact was overwritten by a later rerun. "
                    "The persisted trace currently reproduces 6.7157%, not 6.7073%."
                ),
            },
            "clean_rolling_eligibility": (
                "BASELINE_ONLY_NOT_STAGE5_CERTIFIED: current three-source listing snapshots are "
                "features, but their row-level observed_at must be reconstructed before clean replay."
            ),
        },
        "formal_claims": {
            "clean_rolling_eval_completed": False,
            "production_daily_knowledge_eval_completed": False,
            "post_hoc_oracle_eval_completed": False,
            "b2c_under_5pct_claim": bool(float(b2c_metric["mape"]) < 0.05),
            "c2b_under_5pct_claim": False,
            "both_sides_under_5pct_claim": False,
        },
    }


def _manifest(root: Path, downloads: Path) -> dict[str, Any]:
    audited = [audit_source(spec) for spec in source_specs(root, downloads)]
    fingerprints = "".join(
        str(source.get("sha256") or source.get("status")) for source in audited
    ).encode("utf-8")
    return {
        "schema_version": STAGE1_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "generated_at": _utc_now().isoformat(),
        "workspace_root": str(root),
        "repository": _git_state(root),
        "input_fingerprint_sha256": hashlib.sha256(fingerprints).hexdigest(),
        "evaluation_modes": {
            "CLEAN_ROLLING_EVAL": {
                "alias": "honest_backtest",
                "cutoff_rule": "Only evidence available strictly before each prediction timestamp.",
                "future_override_allowed": False,
                "current_snapshot_backfill_allowed": False,
            },
            "PRODUCTION_DAILY_KNOWLEDGE": {
                "alias": "operational_replay",
                "cutoff_rule": "Use all confirmed internal, market, and approved knowledge available by T-1.",
                "future_override_allowed": False,
                "current_snapshot_backfill_allowed": False,
            },
            "POST_HOC_ORACLE": {
                "alias": "diagnostic_oracle",
                "cutoff_rule": "May inspect future labels only in isolated oracle artifacts.",
                "future_override_allowed": True,
                "may_be_reported_as_generalization": False,
            },
        },
        "target_definitions": {
            "INTERNAL_B2C_TRANSACTION": "训练1目标列：最新订单成交价",
            "INTERNAL_C2B_TRANSACTION": "训练2目标列：收车合同价",
            "external_listing_target_policy": "External listing prices are never transaction targets.",
        },
        "sources": audited,
    }


def _audit_markdown(manifest: dict[str, Any], baseline: dict[str, Any]) -> str:
    source_by_id = {source["source_id"]: source for source in manifest["sources"]}
    b2c = baseline["b2c"]
    c2b = baseline["c2b"]
    runtime = baseline["online_runtime"]
    missing = [source["source_id"] for source in manifest["sources"] if not source["exists"]]
    lines = [
        "# v195 Production Pricing Book - Stage 1 Audit",
        "",
        f"Generated at: `{baseline['generated_at']}`",
        "",
        "## Executive Findings",
        "",
        f"- Persisted B2C 30-day challenger: **{float(b2c['rolling_30d']['mape']) * 100:.4f}% MAPE** "
        f"on {int(b2c['rolling_30d']['n'])} rows. It is below 5% by only "
        f"{-float(b2c['target_gap_to_5pct_percentage_points']):.4f} percentage points and has no safety margin.",
        f"- Persisted C2B latest-7-day challenger: **{float(c2b['latest_7d']['mape']) * 100:.4f}% MAPE** "
        f"on {int(c2b['latest_7d']['n'])} rows. It is not below 5%.",
        f"- Current C2B top-10% APE rows contribute **{float(c2b['tail_metrics']['top10_ape_contribution']) * 100:.2f}%** "
        f"of total APE; remaining 90% MAPE is **{float(c2b['tail_metrics']['remaining90_mape']) * 100:.4f}%**.",
        f"- Old B2C anchor inversion: **{c2b['b2c_anchor_inversion_before']['count']}/{c2b['b2c_anchor_inversion_before']['n']}** "
        "real C2B prices exceed the predicted B2C anchor. B2C must be repaired before hierarchy projection.",
        f"- Online runtime is still `{runtime.get('pricing_engine_version')}` / `{runtime.get('model_version')}`; "
        "the v194.355 and v194.369 challengers are not deployed.",
        "- The historical 6.7073% C2B observation is not accepted as the current baseline because its original artifact was overwritten. "
        f"The persisted trace reproduces {float(c2b['latest_7d']['mape']) * 100:.4f}%.",
        "- Current external snapshots are listing evidence only. They cannot be used as transaction labels and cannot be replayed before their observed timestamp in CLEAN_ROLLING_EVAL.",
        "- `same_series_year` is prohibited as a primary price anchor in v195; strict model/trim identity remains mandatory.",
    ]
    if not manifest["repository"]["is_git_repository"]:
        lines.append("- This workspace is not a Git repository. `COMMIT_SHA.txt` must say `NOT_A_GIT_REPOSITORY`; a SHA must not be fabricated.")
    if missing:
        lines.append(f"- Missing required source candidates: `{', '.join(missing)}`.")

    lines.extend(
        [
            "",
            "## Data Inventory",
            "",
            "| Source | Price type | Rows | Legal/usable rows | Cutoff | Role |",
            "|---|---:|---:|---:|---|---|",
        ]
    )
    for source in manifest["sources"]:
        quality = source.get("price_quality", {})
        freshness = source.get("freshness_quality", {})
        usable_rows = (
            freshness.get("online_eligible_price_rows")
            if freshness.get("policy_applies")
            else quality.get("legal_rows", 0)
        )
        lines.append(
            f"| {source['source_id']} | {source['price_type']} | {source.get('row_count', 0):,} | "
            f"{usable_rows:,} | {source.get('data_cutoff') or '-'} | {source['role']} |"
        )

    lines.extend(
        [
            "",
            "## Source-Specific Risks",
            "",
            f"- Dongchedi current listing rows: {source_by_id['dongchedi_current_listings'].get('row_count', 0):,}.",
            f"- Autohome current listing rows: {source_by_id['autohome_current_listings'].get('row_count', 0):,}.",
            f"- Guazi current listing rows: {source_by_id['guazi_current_listings'].get('row_count', 0):,}; coverage is much thinner and must receive lower learned reliability until calibrated.",
            "- Raw July-10 uploads overlap the canonical stores by design. They are ingestion inputs, not additive independent observations; idempotent business-key ingestion is required.",
            "- External cross-platform duplicates have not yet been removed in Stage 1. Stage 2 must build fuzzy vehicle signatures and source-calibrated evidence weights.",
            "",
            "## Metric Status",
            "",
            "| Side | Window | N | MAPE | WMAPE | P90 APE | Deploy status |",
            "|---|---|---:|---:|---:|---:|---|",
            f"| B2C | {b2c['trace_window'][0]} to {b2c['trace_window'][1]} | {b2c['tail_metrics']['n']:,} | "
            f"{b2c['tail_metrics']['overall_mape'] * 100:.4f}% | {b2c['tail_metrics']['overall_wmape'] * 100:.4f}% | "
            f"{b2c['tail_metrics']['p90_ape'] * 100:.4f}% | challenger, not deployed |",
            f"| C2B | {c2b['trace_window'][0]} to {c2b['trace_window'][1]} | {c2b['tail_metrics']['n']:,} | "
            f"{c2b['tail_metrics']['overall_mape'] * 100:.4f}% | {c2b['tail_metrics']['overall_wmape'] * 100:.4f}% | "
            f"{c2b['tail_metrics']['p90_ape'] * 100:.4f}% | challenger, not deployed |",
            "",
            "These are audited current artifacts, not the final Stage-5 CLEAN_ROLLING_EVAL. The clean report must reconstruct row-level as-of market snapshots and exclude all future overrides.",
            "",
            "## Unified v195 Direction",
            "",
            "1. Build one source-normalized truth layer with explicit price types and as-of cutoffs.",
            "2. Repair B2C anchors before imposing any C2B-to-B2C hierarchy.",
            "3. Materialize a strict multi-level price book keyed primarily by model/trim identity, with series-level data only as weak fallback context.",
            "4. Route approved, effective, non-stale overrides ahead of models; retain full evidence, owner, version, TTL, and rollback metadata.",
            "5. Produce listing, B2C transaction, max C2B, first offer, expected final C2B, and recommended acquisition prices, then run deterministic weighted projection.",
            "6. Report full-legal-data MAPE independently from AUTO_QUOTE MAPE. Manual routing cannot be used to pretend full MAPE is under 5%.",
            "7. Keep CLEAN_ROLLING_EVAL, PRODUCTION_DAILY_KNOWLEDGE, and POST_HOC_ORACLE artifacts physically separate.",
            "",
            "## Stage 1 Acceptance Boundary",
            "",
            "Stage 1 passes when source files, labels, cutoffs, schemas, metric traces, and current deployment versions are reproducibly inventoried. Passing Stage 1 does **not** mean either final pricing target has been achieved.",
        ]
    )
    return "\n".join(lines) + "\n"


def validate_stage1_documents(manifest: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    sources = {source["source_id"]: source for source in manifest.get("sources", [])}
    required_ids = {spec.source_id for spec in source_specs(Path("/unused"), Path("/unused")) if spec.required}
    add(
        "required_source_ids_present",
        required_ids.issubset(sources),
        f"required={sorted(required_ids)} present={sorted(sources)}",
    )
    missing = [source_id for source_id in required_ids if not sources.get(source_id, {}).get("exists")]
    add("required_source_files_readable", not missing, f"missing={missing}")
    empty = [
        source_id
        for source_id in required_ids
        if int(sources.get(source_id, {}).get("row_count") or 0) <= 0
    ]
    add("required_sources_non_empty", not empty, f"empty={empty}")

    expected_types = {
        "internal_b2c_transactions": "INTERNAL_B2C_TRANSACTION",
        "internal_c2b_transactions": "INTERNAL_C2B_TRANSACTION",
        "dongchedi_current_listings": "DONGCHEDI_LISTING",
        "autohome_current_listings": "AUTOHOME_LISTING",
        "guazi_current_listings": "GUAZI_LISTING",
    }
    wrong_types = {
        source_id: sources.get(source_id, {}).get("price_type")
        for source_id, expected in expected_types.items()
        if sources.get(source_id, {}).get("price_type") != expected
    }
    add("price_type_contract", not wrong_types, f"wrong={wrong_types}")

    external_ids = {
        "dongchedi_current_listings",
        "autohome_current_listings",
        "guazi_current_listings",
    }
    external_target_errors = [
        source_id
        for source_id in external_ids
        if sources.get(source_id, {}).get("is_transaction_ground_truth")
    ]
    add(
        "external_listings_not_transaction_targets",
        not external_target_errors,
        f"violations={external_target_errors}",
    )
    target_definitions = baseline.get("target_definitions", {})
    add(
        "target_labels_exact",
        target_definitions.get("b2c", {}).get("target_column") == "最新订单成交价"
        and target_definitions.get("c2b", {}).get("target_column") == "收车合同价",
        json.dumps(target_definitions, ensure_ascii=False),
    )
    modes = manifest.get("evaluation_modes", {})
    add(
        "three_evaluation_modes_isolated_by_contract",
        set(modes) == {"CLEAN_ROLLING_EVAL", "PRODUCTION_DAILY_KNOWLEDGE", "POST_HOC_ORACLE"},
        f"modes={sorted(modes)}",
    )
    add(
        "b2c_metric_artifact_reproduces",
        bool(baseline.get("b2c", {}).get("artifact_consistency")),
        f"mape={baseline.get('b2c', {}).get('tail_metrics', {}).get('overall_mape')}",
    )
    add(
        "c2b_metric_artifact_reproduces",
        bool(baseline.get("c2b", {}).get("artifact_consistency")),
        f"mape={baseline.get('c2b', {}).get('tail_metrics', {}).get('overall_mape')}",
    )
    claims = baseline.get("formal_claims", {})
    add(
        "no_false_both_under_5_claim",
        claims.get("both_sides_under_5pct_claim") is False,
        json.dumps(claims, ensure_ascii=False),
    )
    add(
        "c2b_gap_reported_honestly",
        float(baseline.get("c2b", {}).get("latest_7d", {}).get("mape", 0)) >= 0.05
        and claims.get("c2b_under_5pct_claim") is False,
        f"c2b_mape={baseline.get('c2b', {}).get('latest_7d', {}).get('mape')}",
    )

    failed = [check for check in checks if not check["passed"]]
    return {
        "schema_version": STAGE1_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "generated_at": _utc_now().isoformat(),
        "status": "PASS" if not failed else "FAIL",
        "stage_scope": "AUDIT_ONLY_NOT_MODEL_TARGET_ACCEPTANCE",
        "check_count": len(checks),
        "failed_count": len(failed),
        "checks": checks,
        "warnings": [
            "Workspace is not a Git repository; no commit SHA is available."
            if not manifest.get("repository", {}).get("is_git_repository")
            else None,
            "C2B remains above 5%; Stage 1 acceptance does not waive the pricing target.",
        ],
    }


def build_stage1_audit(root: Path, downloads: Path, output_dir: Path) -> dict[str, Path]:
    root = root.resolve()
    downloads = downloads.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = _manifest(root, downloads)
    baseline = build_metric_baseline(root)
    acceptance = validate_stage1_documents(manifest, baseline)

    manifest_path = output_dir / "data_source_manifest.json"
    baseline_path = output_dir / "current_metric_baseline.json"
    audit_path = output_dir / "pricing_system_audit.md"
    acceptance_path = output_dir / "stage1_acceptance_report.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    baseline_path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
    audit_path.write_text(_audit_markdown(manifest, baseline), encoding="utf-8")
    acceptance_path.write_text(json.dumps(acceptance, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "manifest": manifest_path,
        "baseline": baseline_path,
        "audit": audit_path,
        "acceptance": acceptance_path,
    }


def accept_existing_stage1(output_dir: Path) -> dict[str, Any]:
    manifest_path = output_dir / "data_source_manifest.json"
    baseline_path = output_dir / "current_metric_baseline.json"
    audit_path = output_dir / "pricing_system_audit.md"
    missing = [str(path) for path in (manifest_path, baseline_path, audit_path) if not path.exists()]
    if missing:
        return {
            "schema_version": STAGE1_SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "generated_at": _utc_now().isoformat(),
            "status": "FAIL",
            "failed_count": len(missing),
            "checks": [],
            "missing_artifacts": missing,
        }
    manifest = _read_json(manifest_path)
    baseline = _read_json(baseline_path)
    return validate_stage1_documents(manifest, baseline)
