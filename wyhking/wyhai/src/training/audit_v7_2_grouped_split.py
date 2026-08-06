#!/usr/bin/env python3
"""Grouped split audit entrypoint.

The actual split and near-duplicate audit is generated during
`build_v7_2_low_price_addback_dataset.py`.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports/V7_2_GROUPED_SPLIT_REPORT.md"

if __name__ == "__main__":
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        "# V7.2 Grouped Split 审计\n\n"
        "Grouped split 和 near-duplicate audit 已由 `src/features/build_v7_2_low_price_addback_dataset.py` 生成：\n"
        "- `artifacts/audit/v7_2_split_distribution_*_grouped.csv`\n"
        "- `artifacts/audit/v7_2_near_duplicate_audit_*_grouped.csv`\n",
        encoding="utf-8",
    )
