#!/usr/bin/env python3
"""Restore private production assets before a public Hugging Face Space starts.

The public Space intentionally contains only application code and static UI.
Pricing books, appraiser panels, market caches, and internal reports live in a
private dataset repository and are materialized into the ephemeral container
filesystem at startup.  Non-Hugging-Face deployments are unchanged because
the helper is a no-op when ``HF_PRIVATE_ASSET_REPO`` is unset.
"""

from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ASSETS = (
    Path("data/v195/unified_single_answer_price_book_v195439.parquet"),
    Path("data/v195/internal_dcd_vehicle_catalog.parquet"),
    Path("data/v195/internal_dcd_appraiser_vehicle_evidence.parquet"),
    Path("data/manual_price_book/manual_identity_price_panels_v195438.parquet"),
    Path("runtime/business_market_cache"),
    Path("runtime/selection_history_cache"),
    Path("runtime/ranking_signal_index"),
    Path("results/evals/selection_profit_frontier_champion_20260713.json"),
    Path("results/evals/selection_market_dsi_global_champion_20260713.json"),
    Path("uploaded_reports"),
)


def main() -> int:
    repo_id = (os.environ.get("HF_PRIVATE_ASSET_REPO") or "").strip()
    if not repo_id:
        return 0
    token = (os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("HF_PRIVATE_ASSET_REPO is set but HF_TOKEN is missing")

    marker = ROOT / "runtime" / "hf_private_assets_v195439.ready"
    if marker.is_file() and all((ROOT / path).exists() for path in REQUIRED_ASSETS):
        return 0

    from huggingface_hub import snapshot_download

    allow_patterns: list[str] = []
    for path in REQUIRED_ASSETS:
        value = path.as_posix().rstrip("/")
        allow_patterns.extend((value, f"{value}/**"))
    snapshot_download(
        repo_id=repo_id,
        repo_type="dataset",
        token=token,
        local_dir=ROOT,
        allow_patterns=allow_patterns,
        max_workers=8,
    )
    missing = [str(path) for path in REQUIRED_ASSETS if not (ROOT / path).exists()]
    if missing:
        raise RuntimeError("private runtime asset restore incomplete: " + ", ".join(missing))
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("v195439\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
