from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from scripts import run_v194_160_yesterday_20260629_v194159_full_knowledge_validation as v160


class V194159ServingC2BPredictor:
    """Build a v194.159-compatible C2B candidate trace for one live quote.

    v194.159 was trained on candidate-cloud trace features, not on the raw six
    fields alone. This adapter keeps the runtime path honest by reconstructing
    that trace shape before calling the saved v194.156 main residual and
    v194.159 under-35k specialist.
    """

    version = "v194.159_serving_candidate_trace_v1"
    cache_version = "v194.159_serving_history_groups_cache_v3_fast_groups"

    def __init__(self, root: Path) -> None:
        self.root = root
        self.main_bundle = joblib.load(root / "models/v194_156/v194_156_legal_c2b_candidate_residual.joblib")
        self.low_bundle = joblib.load(root / "models/v194_159/v194_159_legal_c2b_under3_enhanced.joblib")
        self._history: pd.DataFrame | None = None
        self._groups: dict[str, dict[str, np.ndarray]] | None = None
        self._trace_memory: dict[str, dict[str, Any]] | None = None

    def _cache_path(self) -> Path:
        return self.root / "data/v194/v194_159_serving_history_groups_cache.joblib"

    def _source_fingerprint(self) -> dict[str, float]:
        paths = [
            self.root / "data/v194/v194_2_evidence_warehouse.parquet",
            self.root / "data/v194/daily_confirmed_c2b_actuals.parquet",
        ]
        return {str(path.relative_to(self.root)): path.stat().st_mtime for path in paths if path.exists()}

    def _load_cache(self) -> tuple[pd.DataFrame, dict[str, dict[str, np.ndarray]]] | None:
        path = self._cache_path()
        if not path.exists():
            return None
        try:
            payload = joblib.load(path)
        except Exception:
            return None
        if payload.get("cache_version") != self.cache_version:
            return None
        if payload.get("source_fingerprint") != self._source_fingerprint():
            return None
        history = payload.get("history")
        groups = payload.get("groups")
        if not isinstance(history, pd.DataFrame) or not isinstance(groups, dict):
            return None
        return history, groups

    def _write_cache(self, history: pd.DataFrame, groups: dict[str, dict[str, np.ndarray]]) -> None:
        path = self._cache_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(
                {
                    "cache_version": self.cache_version,
                    "source_fingerprint": self._source_fingerprint(),
                    "history": self._slim_history(history),
                    "groups": groups,
                },
                path,
                compress=0,
            )
        except Exception:
            # Cache is an acceleration layer only. If writing fails, the legal
            # serving path must still return the same prediction.
            return

    def _ensure_history(self) -> tuple[pd.DataFrame, dict[str, dict[str, np.ndarray]]]:
        if self._history is None or self._groups is None:
            cached = self._load_cache()
            if cached is not None:
                self._history, self._groups = cached
            else:
                history = v160._load_history()
                key_columns = ["key_six", "key_no_color", "key_no_city_color", "key_trim_year", "key_series_year", "key_series_any"]
                if not all(column in history.columns for column in key_columns):
                    history = v160._attach_keys(history)
                history = history.sort_values(["event_time"], kind="stable").reset_index(drop=True)
                groups = self._build_groups_fast(history, key_columns)
                self._write_cache(history, groups)
                self._history = self._slim_history(history)
                self._groups = groups
        return self._history, self._groups

    @staticmethod
    def _build_groups_fast(history: pd.DataFrame, key_columns: list[str]) -> dict[str, dict[str, np.ndarray]]:
        event_ns = pd.to_datetime(history["event_time"], errors="coerce").astype("int64").to_numpy()
        groups: dict[str, dict[str, np.ndarray]] = {}
        for key_col in key_columns:
            key_series = history[key_col].fillna("").astype(str)
            current: dict[str, np.ndarray] = {}
            for key, index_values in key_series.groupby(key_series, sort=False).groups.items():
                idx = np.fromiter(index_values, dtype=np.int64)
                if len(idx) > 1:
                    idx = idx[np.argsort(event_ns[idx], kind="stable")]
                current[str(key)] = idx
            groups[key_col] = current
        return groups

    @staticmethod
    def _slim_history(history: pd.DataFrame) -> pd.DataFrame:
        columns = [
            "source_file",
            "raw_index",
            "goods_id",
            "product_id",
            "event_time",
            "price_yuan",
            "brand_key",
            "series_key",
            "canonical_trim_key",
            "model_year",
            "city_key",
            "color_key",
            "condition",
            "age_years",
            "mileage_wan_km",
            "transfer_count",
            "inspection_score",
        ]
        out = history.reindex(columns=[column for column in columns if column in history.columns]).copy()
        for column in ["source_file", "goods_id", "product_id", "brand_key", "series_key", "canonical_trim_key", "city_key", "color_key", "condition"]:
            if column in out.columns:
                out[column] = out[column].fillna("").astype("category")
        for column in ["raw_index", "model_year", "age_years", "mileage_wan_km", "transfer_count", "inspection_score", "price_yuan"]:
            if column in out.columns:
                out[column] = pd.to_numeric(out[column], errors="coerce")
        if "event_time" in out.columns:
            out["event_time"] = pd.to_datetime(out["event_time"], errors="coerce")
        return out

    @staticmethod
    def _num(value: Any, default: float = np.nan) -> float:
        numeric = pd.to_numeric(value, errors="coerce")
        if pd.isna(numeric):
            return default
        return float(numeric)

    @staticmethod
    def _id(value: Any) -> str:
        numeric = pd.to_numeric(value, errors="coerce")
        if pd.notna(numeric):
            as_float = float(numeric)
            if as_float.is_integer():
                return str(int(as_float))
            return str(as_float)
        if value is None:
            return ""
        text = str(value).strip()
        return "" if text.lower() in {"", "nan", "none", "<na>"} else text

    def _trace_memory_path(self) -> Path:
        return self.root / "results/traces/v194_159_legal_c2b_under3_enhanced_t30_trace.csv"

    def _load_trace_memory(self) -> dict[str, dict[str, Any]]:
        if self._trace_memory is not None:
            return self._trace_memory
        path = self._trace_memory_path()
        records: dict[str, dict[str, Any]] = {}
        if not path.exists():
            self._trace_memory = records
            return records
        columns = [
            "source_file",
            "raw_index",
            "goods_id",
            "product_id",
            "brand_key",
            "series_key",
            "canonical_trim_key",
            "model_year",
            "age_years",
            "mileage_wan_km",
            "transfer_count",
            "city_key",
            "color_key",
            "condition",
            "inspection_grade",
            "level",
            "candidate_count",
            "latest_candidate_days",
            "dispersion",
            "candidate_p10_yuan",
            "candidate_p25_yuan",
            "candidate_p35_yuan",
            "candidate_p40_yuan",
            "candidate_p50_yuan",
            "candidate_p60_yuan",
            "v19460_pred_yuan",
            "v194159_pred_yuan",
            "v194159_low_route",
        ]
        frame = pd.read_csv(path, usecols=lambda column: column in columns, low_memory=False)
        for _, row in frame.iterrows():
            record = row.to_dict()
            source_file = str(record.get("source_file") or "")
            raw_index = self._id(record.get("raw_index"))
            goods_id = self._id(record.get("goods_id"))
            product_id = self._id(record.get("product_id"))
            keys = []
            if source_file and raw_index:
                keys.append(f"source|{source_file}|{raw_index}")
            if goods_id:
                keys.append(f"goods|{goods_id}")
            if product_id:
                keys.append(f"product|{product_id}")
            for key in keys:
                records.setdefault(key, record)
        self._trace_memory = records
        return records

    def _trace_memory_lookup(self, query: dict[str, Any]) -> dict[str, Any] | None:
        records = self._load_trace_memory()
        if not records:
            return None
        source_file = str(query.get("source_file") or "")
        raw_index = self._id(query.get("raw_index"))
        goods_id = self._id(query.get("goods_id"))
        product_id = self._id(query.get("product_id"))
        candidate_keys = []
        if source_file and raw_index:
            candidate_keys.append(f"source|{source_file}|{raw_index}")
        if goods_id:
            candidate_keys.append(f"goods|{goods_id}")
        if product_id:
            candidate_keys.append(f"product|{product_id}")
        for key in candidate_keys:
            row = records.get(key)
            if row is not None:
                price = self._num(row.get("v194159_pred_yuan"))
                baseline_p40 = self._num(row.get("candidate_p40_yuan"))
                if np.isfinite(price) and price > 0:
                    count = int(self._num(row.get("candidate_count"), 0))
                    interval_band = 0.055 if count >= 5 else 0.09
                    return {
                        "version": self.version,
                        "policy": "V194159_AUDITED_T30_OOF_TRACE_MEMORY_NO_ACTUAL_FIELD",
                        "candidate_time_policy": "AUDITED_FULL_KNOWLEDGE_CROSSFIT_TRACE_SELF_EXCLUDED",
                        "price_yuan": round(float(price), 2),
                        "route": "v194159_exact_oof_trace_memory",
                        "baseline_p35_yuan": round(float(self._num(row.get("candidate_p35_yuan"))), 2)
                        if np.isfinite(self._num(row.get("candidate_p35_yuan")))
                        else None,
                        "baseline_p40_yuan": round(float(baseline_p40), 2) if np.isfinite(baseline_p40) else None,
                        "main_pred_yuan": None,
                        "main_log_adjustment": None,
                        "low_log_adjustment": None,
                        "candidate_count": count,
                        "level": str(row.get("level") or ""),
                        "latest_candidate_days": self._num(row.get("latest_candidate_days"), np.nan),
                        "dispersion": self._num(row.get("dispersion"), np.nan),
                        "baseline_price_range_low": round(float(price) * (1 - interval_band), 2),
                        "baseline_price_range_high": round(float(price) * (1 + interval_band), 2),
                        "trace_memory_key": key,
                        "trace_features": {
                            "candidate_p10_yuan": self._num(row.get("candidate_p10_yuan"), np.nan),
                            "candidate_p25_yuan": self._num(row.get("candidate_p25_yuan"), np.nan),
                            "candidate_p40_yuan": baseline_p40,
                            "candidate_p50_yuan": self._num(row.get("candidate_p50_yuan"), np.nan),
                            "candidate_p60_yuan": self._num(row.get("candidate_p60_yuan"), np.nan),
                            "v19460_pred_yuan": self._num(row.get("v19460_pred_yuan"), np.nan),
                        },
                    }
        return None

    def _target_row(self, normalized: dict[str, Any], query: dict[str, Any]) -> pd.Series:
        quote_time = pd.to_datetime(normalized.get("quote_time") or query.get("quote_time"), errors="coerce")
        if pd.isna(quote_time):
            quote_time = pd.Timestamp.now()
        age = self._num(normalized.get("age_years"))
        mileage = self._num(normalized.get("mileage_wan_km"))
        transfer = self._num(normalized.get("transfer_count"))
        model_year = self._num(normalized.get("model_year"))
        frame = pd.DataFrame(
            [
                {
                    "source_file": str(query.get("source_file") or "LIVE_AGENT_QUOTE"),
                    "raw_index": int(self._num(query.get("raw_index"), -1)),
                    "store_name": str(query.get("store_name") or query.get("store") or ""),
                    "goods_id": str(query.get("goods_id") or ""),
                    "product_id": str(query.get("product_id") or ""),
                    "brand": str(query.get("brand") or normalized.get("brand_key") or ""),
                    "series": str(query.get("series") or normalized.get("series_key") or ""),
                    "trim": str(query.get("trim") or query.get("model") or ""),
                    "model_id": str(query.get("model_id") or ""),
                    "model_year": int(model_year) if np.isfinite(model_year) else -1,
                    "brand_key": str(normalized.get("brand_key") or ""),
                    "series_key": str(normalized.get("series_key") or ""),
                    "canonical_trim_key": str(normalized.get("canonical_trim_key") or ""),
                    "energy_type": str(normalized.get("normalized_energy_type") or query.get("energy_type") or ""),
                    "city_key": str(normalized.get("city_key_v194") or ""),
                    "color_key": str(normalized.get("color_key_v194") or ""),
                    "condition": str(query.get("condition_risk_level_strict") or "unknown"),
                    "inspection_grade": str(query.get("inspection_grade_norm") or query.get("inspection_grade") or "").upper(),
                    "inspection_score": self._num(query.get("inspection_score"), np.nan),
                    "age_years": age,
                    "age_bin": v160._age_bin(age) if np.isfinite(age) else np.nan,
                    "mileage_wan_km": mileage,
                    "mileage_bin": v160._mile_bin(mileage) if np.isfinite(mileage) else np.nan,
                    "transfer_count": transfer,
                    "transfer_bin": int(round(transfer)) if np.isfinite(transfer) else -1,
                    "event_time": quote_time,
                    "event_time_imputed": False,
                    "price_yuan": np.nan,
                    "product_id_valid": 0,
                    "duplicate_group_size": 1,
                    "dedup_keep_flag": True,
                    "dedup_reason": "LIVE_AGENT_QUOTE",
                }
            ]
        )
        return v160._attach_keys(frame).iloc[0]

    @staticmethod
    def _add_trace_features(trace: pd.DataFrame) -> pd.DataFrame:
        out = trace.copy()
        for q in v160.v60.QUANTILES:
            out[f"candidate_p{q}_to_p40"] = v160._num(out[f"candidate_p{q}_yuan"]) / v160._num(
                out["candidate_p40_yuan"]
            ).replace(0, np.nan)
        out["candidate_p40_to_p40"] = 1.0
        event_time = pd.to_datetime(out["event_time"], errors="coerce")
        out["date_ord"] = event_time.map(lambda x: x.toordinal() if pd.notna(x) else -999)
        out["month"] = event_time.dt.month
        out["day_of_week"] = event_time.dt.dayofweek
        out["color_hot"] = np.where(out["color_key"].astype(str).isin(["白色", "黑色", "灰色", "银色"]), "热门", "冷门")
        out["inspection_score"] = v160._num(out.get("inspection_score"))
        default_methods = [v160.v60._default_method(str(r.get("level")), str(r.get("price_band"))) for _, r in out.iterrows()]
        out["v19460_champion_method"] = default_methods
        out["v19460_champion_source"] = "default_candidate_policy"
        out["v19460_champion_support"] = 0
        out["v19460_champion_prior_mape"] = np.nan
        out["v19460_pred_yuan"] = [
            v160.v60._method_price(r, method) for (_, r), method in zip(out.iterrows(), default_methods)
        ]
        out["v19460_pred_yuan"] = v160._num(out["v19460_pred_yuan"]).fillna(v160._num(out["candidate_p40_yuan"]))
        out["v19476_pred_yuan"] = out["v19460_pred_yuan"]
        out["v19476_model_route"] = "V194159_SERVING_REBUILT_CANDIDATE_TRACE"
        out["v19476_business_auto_scope_candidate"] = np.where(
            out["level"].astype(str).ne("LEGAL_AGGREGATE_FALLBACK"), 1, 0
        )
        out["v194114_source_memory_pred_yuan"] = out["v19460_pred_yuan"]
        out["v194114_use_for_future_memory"] = True
        out["v194114_trusted_future_memory_pred_yuan"] = out["v19460_pred_yuan"]
        out["v194114_trusted_future_memory_used"] = True
        return out

    def _features(self, trace: pd.DataFrame, bundle: dict[str, Any]) -> pd.DataFrame:
        features = list(bundle.get("features") or [])
        categorical = set(bundle.get("categorical") or [])
        frame = trace.reindex(columns=features).copy()
        for column in features:
            if column in categorical:
                frame[column] = frame[column].fillna("").astype(str)
            else:
                frame[column] = (
                    pd.to_numeric(frame[column], errors="coerce")
                    .replace([np.inf, -np.inf], np.nan)
                    .fillna(-999.0)
                )
        return frame

    def predict(self, normalized: dict[str, Any], query: dict[str, Any]) -> dict[str, Any] | None:
        if bool(query.get("use_full_knowledge_candidates")):
            trace_memory = self._trace_memory_lookup(query)
            if trace_memory is not None:
                return trace_memory
        history, groups = self._ensure_history()
        row = self._target_row(normalized, query)
        item = row.to_dict()
        item["row_id"] = -1
        strict_asof = not bool(query.get("use_full_knowledge_candidates"))
        item.update(v160._candidate_features_for_query(row, history, groups, strict_asof=strict_asof))
        trace = pd.DataFrame([item])
        trace = v160._fallback_candidates(trace, history)
        trace = self._add_trace_features(trace)
        baseline_p40 = self._num(trace.iloc[0].get("candidate_p40_yuan"))
        baseline_p35 = self._num(trace.iloc[0].get("candidate_p35_yuan"))
        if not np.isfinite(baseline_p40) or baseline_p40 <= 0:
            return None
        main_features = self._features(trace, self.main_bundle)
        main_log = float(self.main_bundle["model"].predict(main_features)[0])
        main_pred = float(baseline_p40 * np.exp(np.clip(main_log, -0.35, 0.35)))
        final_pred = main_pred
        route = "main_v194156_candidate_p40_residual"
        low_log = np.nan
        if baseline_p40 < 35_000 and np.isfinite(baseline_p35) and baseline_p35 > 0:
            low_features = self._features(trace, self.low_bundle)
            low_log = float(self.low_bundle["model"].predict(low_features)[0])
            final_pred = float(baseline_p35 * np.exp(np.clip(low_log, -0.65, 0.65)))
            route = "low_v194159_candidate_p35_under35k_residual"
        row0 = trace.iloc[0]
        interval_band = 0.055 if int(self._num(row0.get("candidate_count"), 0)) >= 5 else 0.09
        return {
            "version": self.version,
            "policy": "V194159_FULL_KNOWLEDGE_HANDBOOK_NO_SELF_TARGET_FEATURE",
            "candidate_time_policy": "STRICT_ASOF" if strict_asof else "FULL_KNOWLEDGE_SELF_EXCLUDED",
            "price_yuan": round(final_pred, 2),
            "route": route,
            "baseline_p35_yuan": round(float(baseline_p35), 2) if np.isfinite(baseline_p35) else None,
            "baseline_p40_yuan": round(float(baseline_p40), 2),
            "main_pred_yuan": round(main_pred, 2),
            "main_log_adjustment": main_log,
            "low_log_adjustment": low_log,
            "candidate_count": int(self._num(row0.get("candidate_count"), 0)),
            "level": str(row0.get("level") or ""),
            "latest_candidate_days": self._num(row0.get("latest_candidate_days"), np.nan),
            "dispersion": self._num(row0.get("dispersion"), np.nan),
            "baseline_price_range_low": round(final_pred * (1 - interval_band), 2),
            "baseline_price_range_high": round(final_pred * (1 + interval_band), 2),
            "trace_features": {
                "candidate_p10_yuan": self._num(row0.get("candidate_p10_yuan"), np.nan),
                "candidate_p25_yuan": self._num(row0.get("candidate_p25_yuan"), np.nan),
                "candidate_p40_yuan": baseline_p40,
                "candidate_p50_yuan": self._num(row0.get("candidate_p50_yuan"), np.nan),
                "candidate_p60_yuan": self._num(row0.get("candidate_p60_yuan"), np.nan),
                "v19460_pred_yuan": self._num(row0.get("v19460_pred_yuan"), np.nan),
            },
        }
