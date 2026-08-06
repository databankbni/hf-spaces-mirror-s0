from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from .v193_qwen_client import QwenSemanticClient
from .v193_2_market_evidence_ranker import rank_external_evidence, usage_audit
from .v193_2_market_evidence_schema import dedupe_key, normalize_price_role, parse_price_yuan, validate_market_evidence
from .v193_2_search_client import OpenSearchClient, SearchResponse
from .v193_2_web_evidence_cache import append_search_cache, default_data_dir, find_cached_results, now_iso, read_parquet_or_empty, search_cache_key, write_parquet
from .v193_2_web_page_extractor import fetch_and_extract


BUILDER_VERSION = "v193_2_market_evidence_builder_v1"
OBS_PATH = Path(__file__).resolve().parents[2] / "data/v192_16/vehicle_source_price_observation_v192_16_semantic.parquet"
AUDIT_DIR = Path(__file__).resolve().parents[2] / "results/audit"
EXPLANATION_DIR = Path(__file__).resolve().parents[2] / "results/explanations"
MODEL_RESULTS_DIR = Path(__file__).resolve().parents[2] / "results/model_results"


QUERY_TEMPLATES = [
    "{city} {model_year} {brand} {series} {trim} 二手车 价格",
    "{brand} {series} {model_year} {trim} 二手车 成交价",
    "{brand} {series} {trim} 汽车之家 二手车",
    "{brand} {series} {trim} 懂车帝 二手车",
    "{brand} {series} {trim} 瓜子 二手车",
    "{brand} {series} {trim} 人人车 二手车",
]

FIXED_CASES = [
    {"case_group": "bmw_320i", "brand": "宝马", "series": "宝马3系", "model_year": 2021, "trim": "320i 运动套装", "canonical_trim_key": "宝马|宝马3系|2021|ICE|320i|standard|sport", "city": "北京"},
    {"case_group": "camry", "brand": "丰田", "series": "凯美瑞", "model_year": 2021, "trim": "2.0G 豪华版", "canonical_trim_key": "丰田|凯美瑞|2021|ICE|2.0|luxury", "city": "北京"},
    {"case_group": "camry", "brand": "丰田", "series": "凯美瑞", "model_year": 2021, "trim": "双擎 2.5HG 豪华版", "canonical_trim_key": "丰田|凯美瑞|2021|HEV|2.5hg|luxury", "city": "北京"},
    {"case_group": "q5l", "brand": "奥迪", "series": "奥迪Q5L", "model_year": 2022, "trim": "40 TFSI 时尚动感型", "canonical_trim_key": "奥迪|奥迪q5l|2022|ICE|40tfsi|dynamic", "city": "北京"},
    {"case_group": "q5l", "brand": "奥迪", "series": "奥迪Q5L", "model_year": 2022, "trim": "45 TFSI 臻选动感型", "canonical_trim_key": "奥迪|奥迪q5l|2022|ICE|45tfsi|dynamic", "city": "北京"},
    {"case_group": "x3", "brand": "宝马", "series": "宝马X3", "model_year": 2022, "trim": "xDrive25i M运动套装", "canonical_trim_key": "宝马|宝马x3|2022|ICE|25i|awd|sport", "city": "北京"},
    {"case_group": "x3", "brand": "宝马", "series": "宝马X3", "model_year": 2022, "trim": "xDrive28i M运动套装", "canonical_trim_key": "宝马|宝马x3|2022|ICE|28i|awd|sport", "city": "北京"},
    {"case_group": "x3", "brand": "宝马", "series": "宝马X3", "model_year": 2022, "trim": "xDrive30i 领先型 M曜夜套装", "canonical_trim_key": "宝马|宝马x3|2022|ICE|30i|awd|night", "city": "北京"},
    {"case_group": "miniev", "brand": "五菱汽车", "series": "五菱宏光MINIEV", "model_year": 2024, "trim": "215km进阶版 磷酸铁锂", "canonical_trim_key": "五菱汽车|五菱宏光miniev|2024|BEV|215_lfp", "city": "北京"},
]


def _stable_task_id(row: dict[str, Any]) -> str:
    from .v193_2_web_evidence_cache import stable_hash

    return stable_hash({k: row.get(k) for k in ["brand", "series", "model_year", "canonical_trim_key", "city", "query_text"]})[:24]


def _latest30_seed_rows(limit: int = 80) -> pd.DataFrame:
    if not OBS_PATH.exists():
        return pd.DataFrame()
    cols = ["brand", "series", "model_year", "trim", "canonical_trim_key", "city", "event_time", "source_type", "market_clean_flag"]
    frame = pd.read_parquet(OBS_PATH, columns=[c for c in cols if c in pd.read_parquet(OBS_PATH, columns=[]).columns]) if False else pd.read_parquet(OBS_PATH, columns=cols)
    frame["event_time"] = pd.to_datetime(frame["event_time"], errors="coerce")
    frame = frame[frame["event_time"].notna()].sort_values("event_time", ascending=False)
    frame = frame[frame["brand"].fillna("").astype(str).ne("") & frame["series"].fillna("").astype(str).ne("")]
    frame = frame.drop_duplicates(["brand", "series", "model_year", "canonical_trim_key", "city"]).head(limit)
    return frame[["brand", "series", "model_year", "trim", "canonical_trim_key", "city"]].copy()


def build_search_tasks(*, provider: str = "searxng", include_fixed_cases: bool = True, latest30_limit: int = 30, data_dir: Path | None = None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if include_fixed_cases:
        rows.extend(FIXED_CASES)
    latest = _latest30_seed_rows(latest30_limit)
    rows.extend(latest.to_dict("records"))
    tasks: list[dict[str, Any]] = []
    created = now_iso()
    for base in rows:
        trim = str(base.get("trim") or "").strip()
        if not trim:
            continue
        for template in QUERY_TEMPLATES:
            item = {
                "brand": base.get("brand"),
                "series": base.get("series"),
                "model_year": int(float(base.get("model_year"))) if pd.notna(base.get("model_year")) else None,
                "trim": trim,
                "canonical_trim_key": base.get("canonical_trim_key"),
                "city": base.get("city") or "全国",
                "query_text": template.format(**{**base, "trim": trim}),
                "search_provider": provider,
                "status": "PENDING",
                "created_at": created,
                "last_run_at": "",
                "retry_count": 0,
                "case_group": base.get("case_group", ""),
            }
            item["task_id"] = _stable_task_id(item)
            tasks.append(item)
    result = pd.DataFrame(tasks).drop_duplicates("task_id")
    path = (data_dir or default_data_dir()) / "web_search_tasks.parquet"
    existing = read_parquet_or_empty(path)
    if not existing.empty:
        existing_ids = set(existing["task_id"].astype(str))
        result = pd.concat([existing, result[~result["task_id"].astype(str).isin(existing_ids)]], ignore_index=True)
    write_parquet(result, path)
    return result


def _qwen_extract(target: dict[str, Any], search_row: dict[str, Any], extract_row: dict[str, Any], client: QwenSemanticClient) -> dict[str, Any]:
    schema = {
        "is_vehicle_listing": bool,
        "is_relevant_to_target": bool,
        "brand": str,
        "series": str,
        "trim": str,
        "price_role": str,
        "source_family": str,
        "evidence_quality": str,
        "risk_flags": list,
        "reject_reason_codes": list,
        "confidence": (int, float),
    }
    payload = {
        "target_vehicle": target,
        "query_text": search_row.get("query_text"),
        "search_result_title": search_row.get("title"),
        "search_result_snippet": search_row.get("snippet"),
        "url": search_row.get("url"),
        "page_text_sample": extract_row.get("page_text_sample", "")[:2000],
        "detected": extract_row,
    }
    result = client.complete_json(
        kind="v193_2_external_market_evidence_extract",
        system_prompt=(
            "Extract one Chinese used-car external market evidence item as strict JSON. "
            "Do not estimate prices. Listing pages are B2C_LISTING by default unless explicitly sold. "
            "If target relevance or price is unclear, reject."
        ),
        user_payload=payload,
        schema=schema,
    )
    if result.get("_semantic_model") == "RULE_FALLBACK":
        return {
            "is_vehicle_listing": bool(extract_row.get("detected_price_text")),
            "is_relevant_to_target": _rule_relevant(target, search_row, extract_row),
            "brand": target.get("brand") or "",
            "series": target.get("series") or "",
            "model_year": target.get("model_year"),
            "trim": target.get("trim") or "",
            "canonical_trim_key": target.get("canonical_trim_key") or "",
            "city": extract_row.get("detected_city") or target.get("city") or "",
            "mileage_km": _parse_mileage_km(extract_row.get("detected_mileage")),
            "price_yuan": parse_price_yuan(extract_row.get("detected_price_text")),
            "price_role": normalize_price_role("", source_family=extract_row.get("detected_source_family") or "", text=(search_row.get("title") or "") + " " + (extract_row.get("page_text_sample") or "")),
            "seller_type": "unknown",
            "source_family": extract_row.get("detected_source_family") or "unknown",
            "evidence_quality": "low",
            "risk_flags": [],
            "reject_reason_codes": [result.get("_qwen_status", "RULE_FALLBACK")],
            "confidence": 0.45,
            "semantic_model": result.get("_semantic_model", "RULE_FALLBACK"),
            "qwen_status": result.get("_qwen_status", "RULE_FALLBACK"),
        }
    return {
        **result,
        "model_year": result.get("model_year") or target.get("model_year"),
        "canonical_trim_key": result.get("canonical_trim_key") or target.get("canonical_trim_key"),
        "city": result.get("city") or extract_row.get("detected_city") or target.get("city"),
        "mileage_km": result.get("mileage_km") or _parse_mileage_km(extract_row.get("detected_mileage")),
        "price_yuan": result.get("price_yuan") or parse_price_yuan(extract_row.get("detected_price_text")),
        "semantic_model": result.get("_semantic_model", client.model_name),
        "qwen_status": result.get("_qwen_status", "OK"),
    }


def _parse_mileage_km(text: Any) -> float | None:
    import re

    raw = str(text or "")
    match = re.search(r"(\d{1,2}(?:\.\d+)?)\s*万公里", raw)
    if match:
        return float(match.group(1)) * 10000
    match = re.search(r"(\d{3,6})\s*公里", raw)
    if match:
        return float(match.group(1))
    return None


def _rule_relevant(target: dict[str, Any], search_row: dict[str, Any], extract_row: dict[str, Any]) -> bool:
    text = " ".join(str(search_row.get(k) or "") for k in ["title", "snippet"]) + " " + str(extract_row.get("page_text_sample") or "")
    return str(target.get("series") or "") in text and str(target.get("brand") or "") in text


def run_batch(
    *,
    batch_size: int = 5,
    max_tasks: int = 20,
    provider: str = "searxng",
    resume: bool = True,
    ttl_days: int | None = None,
    data_dir: Path | None = None,
    qwen_max_structures: int | None = None,
) -> dict[str, Any]:
    data_dir = data_dir or default_data_dir()
    ttl_days = int(ttl_days if ttl_days is not None else os.environ.get("WEB_EVIDENCE_CACHE_TTL_DAYS", "7"))
    for path in [data_dir, data_dir / "search_cache", AUDIT_DIR, MODEL_RESULTS_DIR, EXPLANATION_DIR]:
        path.mkdir(parents=True, exist_ok=True)
    tasks = build_search_tasks(provider=provider, data_dir=data_dir)
    if resume:
        pending = tasks[tasks["status"].fillna("PENDING").isin(["PENDING", "FAILED", "SEARCH_PROVIDER_UNAVAILABLE"])].copy()
    else:
        pending = tasks.copy()
    pending = pending.head(max_tasks)
    client = OpenSearchClient(provider=provider)
    qwen = QwenSemanticClient()
    max_qwen = int(qwen_max_structures if qwen_max_structures is not None else os.environ.get("WEB_EVIDENCE_MAX_QWEN_STRUCTURES_PER_RUN", "20"))
    qwen_count = 0
    progress_rows: list[dict[str, Any]] = []
    search_cache_rows: list[dict[str, Any]] = []
    extract_rows: list[dict[str, Any]] = []
    raw_evidence_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    processed = 0
    for task in pending.to_dict("records"):
        if processed >= max_tasks:
            break
        cached = find_cached_results(str(task["search_provider"]), str(task["query_text"]), ttl_days=ttl_days, data_dir=data_dir)
        from_cache = not cached.empty
        if from_cache:
            response = SearchResponse(provider=str(task["search_provider"]), query_text=str(task["query_text"]), status="CACHE_HIT", results=[], latency_ms=0)
            search_rows = cached.to_dict("records")
        else:
            response = client.search(str(task["query_text"]), provider=str(task["search_provider"]), max_results=batch_size)
            search_rows = []
            for result in response.results:
                row = asdict(result)
                row["cache_key"] = search_cache_key(result.provider, result.query_text)
                row["cache_expire_at"] = (pd.Timestamp.utcnow() + pd.Timedelta(days=ttl_days)).isoformat()
                row["raw_result_json"] = json.dumps(row["raw_result_json"], ensure_ascii=False, default=str)
                search_rows.append(row)
            search_cache_rows.extend(search_rows)
        if not search_rows:
            failure_rows.append({**task, "failure_stage": "search", "failure_reason": response.status, "provider": response.provider, "latency_ms": response.latency_ms, "error": response.error})
        for result_row in search_rows[:batch_size]:
            extract = fetch_and_extract(str(result_row.get("url") or ""), title=str(result_row.get("title") or ""), snippet=str(result_row.get("snippet") or ""))
            extract_record = asdict(extract)
            extract_record.update({"task_id": task["task_id"], "query_text": task["query_text"], "provider": result_row.get("provider"), "result_rank": result_row.get("result_rank")})
            extract_rows.append(extract_record)
            target = {k: task.get(k) for k in ["brand", "series", "model_year", "trim", "canonical_trim_key", "city"]}
            if qwen_count < max_qwen:
                structured = _qwen_extract(target, result_row, extract_record, qwen)
                qwen_count += 1
            else:
                structured = _qwen_extract(target, result_row, extract_record, QwenSemanticClient())
            raw = {
                **target,
                "task_id": task["task_id"],
                "query_text": task["query_text"],
                "provider": result_row.get("provider"),
                "result_rank": result_row.get("result_rank"),
                "title": result_row.get("title"),
                "url": result_row.get("url"),
                "snippet": result_row.get("snippet"),
                "page_text_sample": extract_record.get("page_text_sample"),
                "detected_price_text": extract_record.get("detected_price_text"),
                "detected_source_family": extract_record.get("detected_source_family"),
                **structured,
                "created_at": now_iso(),
                "builder_version": BUILDER_VERSION,
            }
            raw_evidence_rows.append(raw)
        progress_rows.append(
            {
                "task_id": task["task_id"],
                "query_text": task["query_text"],
                "provider": response.provider,
                "status": response.status,
                "from_cache": from_cache,
                "search_result_count": len(search_rows),
                "latency_ms": response.latency_ms,
                "error": response.error,
                "run_at": now_iso(),
            }
        )
        processed += 1
    if search_cache_rows:
        append_search_cache(search_cache_rows, data_dir=data_dir)
    else:
        cache_path = data_dir / "search_cache/search_results.parquet"
        if not cache_path.exists():
            write_parquet(
                pd.DataFrame(
                    columns=[
                        "cache_key",
                        "provider",
                        "query_text",
                        "result_rank",
                        "title",
                        "url",
                        "snippet",
                        "raw_result_json",
                        "search_time",
                        "cache_expire_at",
                    ]
                ),
                cache_path,
            )
    if progress_rows and "task_id" in tasks.columns:
        progress_by_task = {row["task_id"]: row for row in progress_rows}
        tasks = tasks.copy()
        for idx, task in tasks.iterrows():
            task_id = task.get("task_id")
            if task_id not in progress_by_task:
                continue
            progress = progress_by_task[task_id]
            tasks.at[idx, "status"] = progress.get("status")
            tasks.at[idx, "last_run_at"] = progress.get("run_at")
            if progress.get("status") not in {"OK", "CACHE_HIT"}:
                try:
                    tasks.at[idx, "retry_count"] = int(task.get("retry_count") or 0) + 1
                except Exception:
                    tasks.at[idx, "retry_count"] = 1
        write_parquet(tasks, data_dir / "web_search_tasks.parquet")
    _append_or_write(pd.DataFrame(extract_rows), data_dir / "web_page_extracts.parquet")
    raw = pd.DataFrame(raw_evidence_rows)
    if raw.empty:
        raw = pd.DataFrame(columns=["task_id", "query_text", "url", "schema_valid"])
    write_parquet(raw, data_dir / "external_market_evidence_raw.parquet")
    validated_rows = [validate_market_evidence(row) for row in raw.to_dict("records")] if not raw.empty else []
    validated = pd.DataFrame(validated_rows)
    if not validated.empty:
        validated["schema_reject_reason_codes"] = validated["schema_reject_reason_codes"].map(lambda x: "|".join(x) if isinstance(x, list) else str(x))
        validated["dedupe_key"] = validated.apply(lambda r: dedupe_key(r.to_dict()), axis=1)
    write_parquet(validated, data_dir / "external_market_evidence_validated.parquet")
    evidence = validated[validated.get("schema_valid", pd.Series(dtype=bool)).fillna(False)].copy() if not validated.empty else pd.DataFrame()
    before_dedup = len(evidence)
    if not evidence.empty:
        evidence = evidence.drop_duplicates("dedupe_key", keep="first")
        evidence = rank_external_evidence(evidence)
    write_parquet(evidence, data_dir / "external_market_evidence.parquet")
    progress = pd.DataFrame(progress_rows)
    progress.to_csv(AUDIT_DIR / "v193_2_web_search_batch_progress.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(failure_rows).to_csv(AUDIT_DIR / "v193_2_web_search_failure_cases.csv", index=False, encoding="utf-8-sig")
    validated.to_csv(AUDIT_DIR / "v193_2_web_evidence_schema_validation.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([{"before_dedup_rows": before_dedup, "after_dedup_rows": len(evidence), "removed_duplicate_rows": before_dedup - len(evidence)}]).to_csv(
        AUDIT_DIR / "v193_2_external_evidence_dedup_audit.csv", index=False
    )
    _price_role_audit(validated).to_csv(AUDIT_DIR / "v193_2_external_price_role_audit.csv", index=False)
    usage_audit(evidence).to_csv(AUDIT_DIR / "v193_2_external_evidence_usage_audit.csv", index=False)
    _provider_quality(progress, extract_rows, validated, evidence).to_csv(AUDIT_DIR / "v193_2_web_search_provider_quality.csv", index=False)
    _write_ab_outputs(evidence)
    _write_cards(evidence)
    return {
        "tasks_considered": len(pending),
        "tasks_processed": processed,
        "search_rows": len(search_cache_rows),
        "extract_rows": len(extract_rows),
        "raw_evidence_rows": len(raw),
        "validated_rows": len(validated),
        "valid_evidence_rows": len(evidence),
        "provider": provider,
    }


def _append_or_write(frame: pd.DataFrame, path: Path) -> None:
    if frame.empty:
        if not path.exists():
            write_parquet(frame, path)
        return
    existing = read_parquet_or_empty(path)
    combined = pd.concat([existing, frame], ignore_index=True) if not existing.empty else frame
    if {"url", "query_text"}.issubset(combined.columns):
        combined = combined.drop_duplicates(["url", "query_text"], keep="last")
    write_parquet(combined, path)


def _price_role_audit(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "price_role" not in frame:
        return pd.DataFrame([{"price_role": "NONE", "rows": 0, "can_enter_baseline": 0}])
    return frame.groupby("price_role", dropna=False).agg(rows=("price_role", "size"), can_enter_baseline=("can_enter_baseline", "sum")).reset_index()


def _provider_quality(progress: pd.DataFrame, extracts: list[dict[str, Any]], validated: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    provider = progress.get("provider", pd.Series(["unknown"])).iloc[0] if not progress.empty else "unknown"
    query_count = len(progress)
    search_success = float((progress.get("search_result_count", pd.Series(dtype=int)).fillna(0).gt(0)).mean()) if query_count else 0.0
    extract_success = sum(1 for row in extracts if str(row.get("extract_status", "")).startswith("OK")) / max(len(extracts), 1)
    schema_valid = float(validated.get("schema_valid", pd.Series(dtype=bool)).fillna(False).mean()) if not validated.empty else 0.0
    dedupe_survival = len(evidence) / max(int(validated.get("schema_valid", pd.Series(dtype=bool)).fillna(False).sum()), 1)
    avg_latency = float(pd.to_numeric(progress.get("latency_ms", pd.Series(dtype=float)), errors="coerce").fillna(0).mean()) if query_count else 0.0
    return pd.DataFrame(
        [
            {
                "provider": provider,
                "query_count": query_count,
                "search_success_rate": search_success,
                "extract_success_rate": extract_success,
                "schema_valid_rate": schema_valid,
                "dedupe_survival_rate": dedupe_survival,
                "valid_evidence_count": len(evidence),
                "average_latency_ms": avg_latency,
            }
        ]
    )


def _write_ab_outputs(evidence: pd.DataFrame) -> None:
    MODEL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = [
        {"variant": "A_v193_1_no_external_search", "external_evidence_rows": 0, "price_effect_allowed": False, "manual_reference_enhanced": False},
        {"variant": "B_v193_2_external_interval_manual_reference", "external_evidence_rows": len(evidence), "price_effect_allowed": False, "manual_reference_enhanced": len(evidence) > 0},
    ]
    pd.DataFrame(rows).to_csv(MODEL_RESULTS_DIR / "v193_2_web_evidence_ab_sample.csv", index=False)
    pd.DataFrame(rows).to_csv(MODEL_RESULTS_DIR / "v193_2_web_evidence_ab_latest30_sample.csv", index=False)


def _write_cards(evidence: pd.DataFrame) -> None:
    from .v193_evidence_card_generator import write_evidence_card

    EXPLANATION_DIR.mkdir(parents=True, exist_ok=True)
    groups = {"bmw_320i": "v193_2_bmw_320i_web_evidence_card", "camry": "v193_2_camry_web_evidence_card", "q5l": "v193_2_q5l_web_evidence_card", "x3": "v193_2_x3_web_evidence_card"}
    for group, filename in groups.items():
        if evidence.empty:
            subset = pd.DataFrame()
        else:
            mask = evidence.get("query_text", pd.Series(dtype=str)).astype(str).str.contains(group.split("_")[0], case=False, na=False)
            if group == "bmw_320i":
                mask = evidence.get("series", pd.Series(dtype=str)).astype(str).str.contains("宝马3系", na=False)
            elif group == "camry":
                mask = evidence.get("series", pd.Series(dtype=str)).astype(str).str.contains("凯美瑞", na=False)
            elif group == "q5l":
                mask = evidence.get("series", pd.Series(dtype=str)).astype(str).str.contains("Q5L|奥迪Q5L", case=False, regex=True, na=False)
            elif group == "x3":
                mask = evidence.get("series", pd.Series(dtype=str)).astype(str).str.contains("宝马X3|X3", case=False, regex=True, na=False)
            subset = evidence[mask].head(10)
        card = {
            "evidence_card_version": "v193_2_web_evidence_card_v1",
            "business_summary": f"外部联网证据 {len(subset)} 条；默认仅用于区间/人工参考，不进入自动点价 baseline。",
            "audit_trace": {
                "web_evidence_group": group,
                "external_evidence_count": len(subset),
                "external_evidence_can_affect_price": False,
                "manual_reference_candidates": subset.to_dict("records") if not subset.empty else [],
                "reason": "external B2C listing evidence requires calibration before entering baseline",
            },
        }
        write_evidence_card(card, EXPLANATION_DIR / f"{filename}.json", EXPLANATION_DIR / f"{filename}.html")
