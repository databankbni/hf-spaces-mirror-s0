from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any


EVIDENCE_CARD_VERSION = "v193_qwen_semantic_evidence_card_v1"


def build_evidence_card(facts: dict[str, Any]) -> dict[str, Any]:
    """Generate an explanation from structured facts only."""
    candidates = facts.get("baseline_candidates") or []
    interval = facts.get("interval_only_candidates") or []
    manual = facts.get("manual_reference_candidates") or []
    trust = facts.get("trust_gate_result") or {}
    summary = (
        f"本次报价使用 {len(candidates)} 个基线候选、{len(interval)} 个区间候选、"
        f"{len(manual)} 个人工参考候选；Trust Gate={trust.get('level', trust.get('confidence', 'UNKNOWN'))}。"
    )
    return {
        "evidence_card_version": EVIDENCE_CARD_VERSION,
        "business_summary": summary,
        "dealer_facing_explanation": facts.get("dealer_facing_explanation") or summary,
        "audit_trace": facts,
    }


def render_evidence_card_html(card: dict[str, Any]) -> str:
    trace = card.get("audit_trace") or {}
    rows = []
    for group in ["baseline_candidates", "interval_only_candidates", "manual_reference_candidates"]:
        for item in trace.get(group) or []:
            rows.append(
                "<tr>"
                f"<td>{escape(group)}</td>"
                f"<td>{escape(str(item.get('candidate_id', '')))}</td>"
                f"<td>{escape(str(item.get('relationship_type', item.get('semantic_tier', ''))))}</td>"
                f"<td>{escape(str(item.get('price', item.get('c2b_converted_price', ''))))}</td>"
                f"<td>{escape(str(item.get('reason', item.get('blocked_from_baseline_reason', ''))))}</td>"
                "</tr>"
            )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>v193 evidence</title>
<style>body{{font-family:Arial,sans-serif;line-height:1.45}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:6px}}</style>
</head><body>
<h1>v193 Evidence Card</h1>
<p>{escape(card.get('business_summary',''))}</p>
<h2>Candidate Evidence</h2>
<table><thead><tr><th>group</th><th>candidate</th><th>relation</th><th>price</th><th>reason</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<h2>Audit Trace</h2>
<pre>{escape(json.dumps(trace, ensure_ascii=False, indent=2, default=str))}</pre>
</body></html>"""


def write_evidence_card(card: dict[str, Any], json_path: Path, html_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(card, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    html_path.write_text(render_evidence_card_html(card), encoding="utf-8")

