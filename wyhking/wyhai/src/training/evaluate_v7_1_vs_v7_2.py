#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts/model_results"
REPORTS = ROOT / "reports"


def md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_无数据_"
    view = df.fillna("")
    lines = [
        "| " + " | ".join(map(str, view.columns)) + " |",
        "| " + " | ".join(["---"] * len(view.columns)) + " |",
    ]
    for _, row in view.iterrows():
        lines.append("| " + " | ".join(str(row[c]).replace("\n", " ") for c in view.columns) + " |")
    return "\n".join(lines)


def best(path: Path, label: str) -> dict:
    if not path.exists():
        return {"version": label, "status": "missing", "path": str(path)}
    df = pd.read_csv(path)
    ok = df[df.get("status", "completed").eq("completed")] if "status" in df else df
    if ok.empty:
        return {"version": label, "status": "empty", "path": str(path)}
    row = ok.sort_values("MAPE").iloc[0].to_dict()
    row["version"] = label
    return row


def main() -> None:
    rows = []
    for task in ["c2b", "b2c"]:
        rows.append(best(ART / f"model_comparison_{task}_full_v7_1.csv", f"v7.1_random_{task}"))
        rows.append(best(ART / f"grouped_split_model_comparison_{task}_v7_1.csv", f"v7.1_grouped_{task}"))
        rows.append(best(ART / f"v7_2_model_comparison_{task}_random.csv", f"v7.2_random_{task}"))
        rows.append(best(ART / f"v7_2_model_comparison_{task}_grouped.csv", f"v7.2_grouped_{task}"))
    out = pd.DataFrame(rows)
    out.to_csv(ART / "v7_1_vs_v7_2_summary.csv", index=False, encoding="utf-8-sig")
    REPORTS.mkdir(parents=True, exist_ok=True)
    REPORTS.joinpath("V7_1_VS_V7_2_COMPARISON_REPORT.md").write_text(
        "# V7.1 vs V7.2 对比报告\n\n" + md_table(out),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
