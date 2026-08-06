"""IndiaScam-Bench harness v0 — measures any predictor against samples.jsonl.

Usage:  python3 eval/harness.py [--engine rules] [--report eval/report_v0.md]
Pure stdlib. Metrics: overall accuracy, scam recall/precision, benign FPR,
per-class recall, latency stats. Writes a markdown report.
"""
from __future__ import annotations
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.engine.rules import analyze as rules_analyze  # noqa: E402
from app.engine.fusion import analyze_hybrid  # noqa: E402
from app.engine import llm as llm_mod  # noqa: E402


def get_engine(name: str):
    if name == "hybrid":
        return lambda t: analyze_hybrid(t)
    return rules_analyze


def load_samples(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def run(samples: list[dict], engine_fn=None) -> dict:
    engine_fn = engine_fn or rules_analyze
    tp = fp = tn = fn = 0
    per_class: dict[str, dict] = {}
    latencies = []
    errors = []
    llm_used = 0
    for s in samples:
        r = engine_fn(s["text"])
        if "llm" in r:
            llm_used += 1
        latencies.append(r["latency_ms"])
        predicted_scam = r["verdict"] in ("SCAM", "SUSPICIOUS")
        actual_scam = s["label"] == "scam"
        if actual_scam:
            c = per_class.setdefault(s["scam_type"], {"n": 0, "hit": 0})
            c["n"] += 1
            if predicted_scam:
                tp += 1
                c["hit"] += 1
            else:
                fn += 1
                errors.append(("MISSED SCAM", s["id"], r["verdict"], r["score"], s["text"][:80]))
        else:
            if predicted_scam:
                fp += 1
                errors.append(("FALSE POSITIVE", s["id"], r["verdict"], r["score"], s["text"][:80]))
            else:
                tn += 1
    n_scam, n_benign = tp + fn, fp + tn
    return {
        "n": len(samples), "n_scam": n_scam, "n_benign": n_benign,
        "recall": tp / n_scam if n_scam else 0.0,
        "precision": tp / (tp + fp) if (tp + fp) else 0.0,
        "fpr": fp / n_benign if n_benign else 0.0,
        "accuracy": (tp + tn) / len(samples),
        "per_class": per_class,
        "latency_p50": statistics.median(latencies),
        "latency_max": max(latencies),
        "llm_used": llm_used,
        "errors": errors,
    }


def to_markdown(m: dict, engine: str) -> str:
    lines = [
        f"# IndiaScam-Bench report — engine `{engine}`",
        f"_Generated {time.strftime('%Y-%m-%d %H:%M:%S')} · {m['n']} samples "
        f"({m['n_scam']} scam / {m['n_benign']} benign)_",
        "",
        "| Metric | Value | Target |",
        "|---|---|---|",
        f"| Scam recall | **{m['recall']:.1%}** | >= 90% |",
        f"| Scam precision | **{m['precision']:.1%}** | >= 95% |",
        f"| Benign false-positive rate | **{m['fpr']:.1%}** | < 2% |",
        f"| Accuracy | {m['accuracy']:.1%} | — |",
        f"| Latency p50 / max (ms) | {m['latency_p50']:.1f} / {m['latency_max']:.1f} | p90 < 3000 |",
        f"| Samples that used the LLM | {m['llm_used']} | fast-path + fallback keep this low |",
        "",
        "## Per-class recall",
        "",
        "| Scam type | Samples | Recall |",
        "|---|---|---|",
    ]
    for cls, c in sorted(m["per_class"].items()):
        lines.append(f"| {cls} | {c['n']} | {c['hit'] / c['n']:.0%} |")
    lines += ["", "## Errors", ""]
    if not m["errors"]:
        lines.append("None. All samples classified on the correct side.")
    else:
        lines.append("| Type | ID | Verdict | Score | Text |")
        lines.append("|---|---|---|---|---|")
        for e in m["errors"]:
            lines.append("| " + " | ".join(str(x) for x in e) + " |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="rules", choices=["rules", "hybrid"])
    ap.add_argument("--report", default=str(ROOT / "eval" / "report_v0.md"))
    args = ap.parse_args()
    if args.engine == "hybrid" and not llm_mod.available():
        print("NOTE: no LLM key/network — hybrid will fall back to rules on every ambiguous sample")
    samples = load_samples(ROOT / "data" / "samples.jsonl")
    m = run(samples, get_engine(args.engine))
    md = to_markdown(m, args.engine)
    Path(args.report).write_text(md, encoding="utf-8")
    print(md)
    ok = m["recall"] >= 0.9 and m["fpr"] < 0.02
    print(("PASS" if ok else "NOT YET AT TARGET") + f" — recall {m['recall']:.1%}, FPR {m['fpr']:.1%}")
