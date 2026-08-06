from __future__ import annotations

from typing import Any

import pandas as pd


RANKER_VERSION = "v193_2_market_evidence_ranker_v1"


def rank_external_evidence(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    data = frame.copy()
    quality_score = data.get("evidence_quality", "reject").map({"high": 1.0, "medium": 0.7, "low": 0.35, "reject": 0.0}).fillna(0.0)
    role_score = data.get("price_role", "UNKNOWN").map({"B2C_SOLD": 0.9, "B2C_LISTING": 0.6, "UNKNOWN": 0.0, "C2B_PURCHASE": 0.0}).fillna(0.0)
    confidence = pd.to_numeric(data.get("confidence"), errors="coerce").fillna(0.0)
    data["external_evidence_rank_score"] = (0.5 * quality_score + 0.25 * role_score + 0.25 * confidence).round(6)
    data["external_evidence_ranker_version"] = RANKER_VERSION
    return data.sort_values(["external_evidence_rank_score", "confidence"], ascending=False).reset_index(drop=True)


def usage_audit(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(
            [
                {
                    "external_evidence_rows": 0,
                    "entered_baseline_rows": 0,
                    "entered_interval_rows": 0,
                    "entered_manual_reference_rows": 0,
                    "price_effect_allowed": False,
                }
            ]
        )
    return pd.DataFrame(
        [
            {
                "external_evidence_rows": len(frame),
                "entered_baseline_rows": int(pd.Series(frame.get("can_enter_baseline", False)).fillna(False).sum()),
                "entered_interval_rows": int(pd.Series(frame.get("can_enter_interval", False)).fillna(False).sum()),
                "entered_manual_reference_rows": int(pd.Series(frame.get("can_enter_manual_reference", False)).fillna(False).sum()),
                "price_effect_allowed": False,
            }
        ]
    )

