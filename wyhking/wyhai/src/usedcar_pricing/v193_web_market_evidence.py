from __future__ import annotations

import hashlib
import time
from typing import Any

import pandas as pd

from .v193_qwen_client import QwenSemanticClient
from .v193_vehicle_semantic_parser import rule_parse_vehicle


WEB_EVIDENCE_VERSION = "v193_web_market_evidence_v1"


def _dedupe_key(row: dict[str, Any]) -> str:
    raw = "|".join(str(row.get(key, "")) for key in ["source_url", "brand", "series", "model_year", "trim", "city", "price"])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def evidence_from_search_queries(queries: list[str], client: QwenSemanticClient | None = None) -> pd.DataFrame:
    client = client or QwenSemanticClient()
    rows: list[dict[str, Any]] = []
    for query in queries:
        result = client.web_search(query)
        for item in result.get("results") or []:
            parsed = rule_parse_vehicle(
                brand=item.get("brand"),
                series=item.get("series"),
                model_year=item.get("model_year"),
                raw_trim=item.get("trim"),
                raw_energy=item.get("energy_type"),
            )
            price = pd.to_numeric(item.get("price"), errors="coerce")
            row = {
                "evidence_id": "",
                "source_url": item.get("source_url", ""),
                "source_title": item.get("title", item.get("source_title", "")),
                "source_family": item.get("source_family", "qwen_web_search"),
                "crawl_time": result.get("crawl_time") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "city": item.get("city", ""),
                "brand": item.get("brand", parsed["brand"]),
                "series": item.get("series", parsed["series"]),
                "model_year": item.get("model_year", parsed["model_year"]),
                "trim": item.get("trim", ""),
                "canonical_trim_key": parsed["canonical_trim_key"],
                "mileage": pd.to_numeric(item.get("mileage"), errors="coerce"),
                "price": price,
                "price_role": item.get("price_role", "B2C_LISTING" if pd.notna(price) else "UNKNOWN"),
                "seller_type": item.get("seller_type", ""),
                "valid_for_baseline": False,
                "valid_for_interval": bool(pd.notna(price)),
                "valid_for_manual_reference": True,
                "risk_flags": item.get("risk_flags", []),
                "query": query,
                "model_name": result.get("model_name", client.model_name),
                "search_strategy": result.get("search_strategy", client.config.search_strategy),
                "web_evidence_version": WEB_EVIDENCE_VERSION,
            }
            row["dedupe_key"] = _dedupe_key(row)
            row["evidence_id"] = row["dedupe_key"]
            rows.append(row)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "evidence_id",
                "source_url",
                "source_title",
                "source_family",
                "crawl_time",
                "city",
                "brand",
                "series",
                "model_year",
                "trim",
                "canonical_trim_key",
                "mileage",
                "price",
                "price_role",
                "seller_type",
                "dedupe_key",
                "valid_for_baseline",
                "valid_for_interval",
                "valid_for_manual_reference",
                "risk_flags",
                "query",
                "model_name",
                "search_strategy",
                "web_evidence_version",
            ]
        )
    frame = frame.drop_duplicates("dedupe_key", keep="first").reset_index(drop=True)
    frame["risk_flags"] = frame["risk_flags"].map(lambda value: "|".join(value) if isinstance(value, list) else str(value or ""))
    return frame

