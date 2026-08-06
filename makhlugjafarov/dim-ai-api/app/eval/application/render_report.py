from __future__ import annotations

import json
from pathlib import Path
import datetime

from app.eval.domain.metrics import (
    EvalQuestion,
    EvalResult,
    ReviewItem,
    _expected_keys,
    _confidence_value,
    _confidence_label,
)


def build_review_queue(
    questions: list[EvalQuestion],
    results: list[EvalResult],
    weak_confidence_threshold: float,
    slow_ms: float,
) -> list[ReviewItem]:
    """Build a manual-review queue from production eval output."""
    q_map = {q.id: q for q in questions}
    review_items: list[ReviewItem] = []

    for result in results:
        question = q_map[result.question_id]
        reasons: list[str] = []
        expected_keys = _expected_keys(question)
        confidence = _confidence_value(result.confidence)

        if result.error:
            reasons.append("error")
        if confidence is None:
            reasons.append("missing_confidence")
        elif confidence < weak_confidence_threshold:
            reasons.append("weak_confidence")
        if not result.citations:
            reasons.append("no_citations")
        if result.latency_ms >= slow_ms:
            reasons.append("slow_response")
        if expected_keys and not result.hit_at_k(expected_keys, 10):
            reasons.append("expected_source_miss_at_10")

        if not reasons:
            continue

        priority = "high" if {"error", "no_citations", "expected_source_miss_at_10"} & set(reasons) else "medium"
        if reasons == ["slow_response"]:
            priority = "low"

        review_items.append(
            ReviewItem(
                question_id=result.question_id,
                question=result.question,
                reasons=reasons,
                priority=priority,
                confidence=confidence,
                latency_ms=result.latency_ms,
                citation_count=len(result.citations),
                tags=question.tags,
                answer_snippet=result.answer_snippet,
                suggested_action="Review retrieval sources, answer faithfulness, and whether this item should enter the regression set.",
            )
        )

    return sorted(review_items, key=lambda item: ({"high": 0, "medium": 1, "low": 2}[item.priority], -len(item.reasons), item.question_id))


def report(
    dataset_id: str,
    questions: list[EvalQuestion],
    results: list[EvalResult],
    recall_target: float,
    weak_confidence_threshold: float,
    architecture_version: str | None = None,
) -> int:
    """Print a summary report.  Returns 0 on pass, 1 on failure."""
    q_map = {q.id: q for q in questions}
    total = len(results)
    errors = [r for r in results if r.error]
    ok = [r for r in results if not r.error]

    # Recall metrics — only computed for questions with ground-truth sources
    grounded = [r for r in ok if _expected_keys(q_map[r.question_id])]
    hits5 = sum(1 for r in grounded if r.hit_at_k(_expected_keys(q_map[r.question_id]), 5))
    hits8 = sum(1 for r in grounded if r.hit_at_k(_expected_keys(q_map[r.question_id]), 8))
    hits10 = sum(1 for r in grounded if r.hit_at_k(_expected_keys(q_map[r.question_id]), 10))
    recall5 = hits5 / len(grounded) if grounded else None
    recall8 = hits8 / len(grounded) if grounded else None
    recall10 = hits10 / len(grounded) if grounded else None

    # Page-level recall (the meaningful signal): did we surface the right page,
    # not just the right book. Only for questions that carry an expected page.
    page_grounded = [r for r in grounded if q_map[r.question_id].expected_pages is not None]

    def _page_coverage(k: int) -> float | None:
        if not page_grounded:
            return None
        coverage_sum = sum(
            r.pages_coverage_at_k(_expected_keys(q_map[r.question_id]), q_map[r.question_id].expected_pages, k)
            for r in page_grounded
        )
        return coverage_sum / len(page_grounded)

    def _fully_covered(k: int) -> float | None:
        if not page_grounded:
            return None
        hits = sum(
            1 for r in page_grounded
            if r.fully_covered_at_k(_expected_keys(q_map[r.question_id]), q_map[r.question_id].expected_pages, k)
        )
        return hits / len(page_grounded)

    # Only @5 and @10 are reported below; @8 is intentionally not surfaced here.
    page_cov5, page_cov10 = _page_coverage(5), _page_coverage(10)
    full_cov5, full_cov10 = _fully_covered(5), _fully_covered(10)

    # Write benchmarking log
    if architecture_version and grounded:
        benchmarks_path = Path("data/evals/benchmarks.jsonl")
        benchmarks_path.parent.mkdir(parents=True, exist_ok=True)

        # Group by type and subject
        groups = set((q_map[r.question_id].type, q_map[r.question_id].subject) for r in grounded)
        # Add overall for each type
        for t in {q.type for q in q_map.values()}:
            groups.add((t, "overall"))
        # Add overall for all types
        for s in {q.subject for q in q_map.values()}:
            groups.add(("overall", s))
        groups.add(("overall", "overall"))

        with benchmarks_path.open("a", encoding="utf-8") as f:
            for q_type, subject in groups:
                sub_grounded = [r for r in grounded if (q_type == "overall" or q_map[r.question_id].type == q_type) and (subject == "overall" or q_map[r.question_id].subject == subject)]
                if not sub_grounded:
                    continue
                sub_hits5 = sum(1 for r in sub_grounded if r.hit_at_k(_expected_keys(q_map[r.question_id]), 5))
                sub_hits8 = sum(1 for r in sub_grounded if r.hit_at_k(_expected_keys(q_map[r.question_id]), 8))
                sub_hits10 = sum(1 for r in sub_grounded if r.hit_at_k(_expected_keys(q_map[r.question_id]), 10))
                sub_page = [r for r in sub_grounded if q_map[r.question_id].expected_pages is not None]

                def _sub_page_cov(k: int, rows=sub_page) -> float | None:
                    if not rows:
                        return None
                    return sum(r.pages_coverage_at_k(_expected_keys(q_map[r.question_id]), q_map[r.question_id].expected_pages, k) for r in rows) / len(rows)

                def _sub_full_cov(k: int, rows=sub_page) -> float | None:
                    if not rows:
                        return None
                    return sum(1 for r in rows if r.fully_covered_at_k(_expected_keys(q_map[r.question_id]), q_map[r.question_id].expected_pages, k)) / len(rows)

                record = {
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "architecture_version": architecture_version,
                    "dataset_id": dataset_id,
                    "type": q_type,
                    "subject": subject,
                    "count": len(sub_grounded),
                    "recall@5": sub_hits5 / len(sub_grounded),
                    "recall@8": sub_hits8 / len(sub_grounded),
                    "recall@10": sub_hits10 / len(sub_grounded),
                    "page_count": len(sub_page),
                    "coverage@5": _sub_page_cov(5),
                    "fully_covered@5": _sub_full_cov(5),
                    "coverage@8": _sub_page_cov(8),
                    "fully_covered@8": _sub_full_cov(8),
                    "coverage@10": _sub_page_cov(10),
                    "fully_covered@10": _sub_full_cov(10),
                    # GRO-89: answer-accuracy fields
                    "answer_graded": sum(1 for r in sub_grounded if q_map[r.question_id].expected_answer and r.answer_correct is not None),
                    "answer_correct": sum(1 for r in sub_grounded if r.answer_correct is True),
                    "answer_accuracy": (
                        sum(1 for r in sub_grounded if r.answer_correct is True) /
                        sum(1 for r in sub_grounded if r.answer_correct is not None)
                        if any(r.answer_correct is not None for r in sub_grounded) else None
                    ),
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # GRO-89: Answer accuracy (only when at least some questions were graded)
    graded_results = [r for r in ok if r.answer_correct is not None]
    correct_results = [r for r in graded_results if r.answer_correct]
    answer_accuracy = len(correct_results) / len(graded_results) if graded_results else None

    # Confidence distribution
    strong = sum(
        1
        for r in ok
        if isinstance(r.confidence, (int, float)) and (_confidence_value(r.confidence) or 0) >= weak_confidence_threshold
    )
    weak = sum(
        1
        for r in ok
        if isinstance(r.confidence, (int, float)) and 0 < (_confidence_value(r.confidence) or 0) < weak_confidence_threshold
    )
    no_ctx = sum(1 for r in ok if _confidence_value(r.confidence) is None or _confidence_value(r.confidence) == 0)

    # Latency
    latencies = [r.latency_ms for r in ok]
    p50 = sorted(latencies)[len(latencies) // 2] if latencies else 0
    p95 = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0

    sep = "─" * 60
    print(f"\n{sep}")
    print(f"DIM AI Retrieval Eval — {dataset_id}")
    print(sep)
    print(f"  Questions:      {total} total, {len(ok)} ok, {len(errors)} errors")
    print()
    print("  Source-level recall (right book — lenient):")
    if grounded:
        print(f"    Recall@5:  {recall5:.2%}  ({hits5}/{len(grounded)})")
        print(f"    Recall@8:  {recall8:.2%}  ({hits8}/{len(grounded)})")
        print(f"    Recall@10: {recall10:.2%}  ({hits10}/{len(grounded)})")
        print(f"    Target:    {recall_target:.0%}")
    else:
        print("    (no ground-truth sources assigned yet — recall not measured)")
    print()
    print("  Page-level recall (right page ±1 — the meaningful signal):")
    if page_grounded:
        print(f"    Coverage@5:       {page_cov5:.2%}")
        print(f"    Fully-Covered@5:  {full_cov5:.2%}  ({sum(1 for r in page_grounded if r.fully_covered_at_k(_expected_keys(q_map[r.question_id]), q_map[r.question_id].expected_pages, 5))}/{len(page_grounded)})")
        print(f"    Coverage@10:      {page_cov10:.2%}")
        print(f"    Fully-Covered@10: {full_cov10:.2%}")
    else:
        print("    (no expected pages assigned yet — page recall not measured)")
    print()
    print("  Confidence distribution:")
    print(f"    Strong (≥{weak_confidence_threshold:.0%}): {strong}")
    print(f"    Weak   (<{weak_confidence_threshold:.0%}): {weak}")
    print(f"    No context:   {no_ctx}")
    print()
    print(f"  Latency (successful):  p50={p50:.0f}ms  p95={p95:.0f}ms")
    print()

    # GRO-89: Answer accuracy block
    if graded_results:
        print("  Answer correctness (BYOK grading):")
        print(f"    Graded:   {len(graded_results)} questions")
        print(f"    Correct:  {len(correct_results)}")
        print(f"    Accuracy: {answer_accuracy:.2%}")
        print()
        # Show per-question grading
        for r in ok:
            if r.answer_correct is not None:
                mark = "✓" if r.answer_correct else "✗"
                expected = q_map[r.question_id].expected_answer or "?"
                print(f"    {mark} [{r.question_id}] expected={expected!r:>12}  snippet={r.answer_snippet[:60]!r}")
        print()

    if errors:
        print("  Errors:")
        for r in errors:
            print(f"    [{r.question_id}] {r.error}")
        print()

    # Slow queries
    slow = sorted(ok, key=lambda r: r.latency_ms, reverse=True)[:5]
    print("  Slowest 5:")
    for r in slow:
        print(f"    {r.latency_ms:>7.0f}ms  [{r.question_id}] confidence={_confidence_label(r.confidence)} citations={len(r.citations)}")
    print(sep)

    # Pass/fail
    failed = False
    if errors:
        print("FAIL: retrieval errors occurred.")
        failed = True
    if grounded and recall5 is not None and recall5 < recall_target:
        print(f"FAIL: Recall@5 {recall5:.2%} is below target {recall_target:.0%}.")
        failed = True
    if not failed:
        print("PASS")
    print()
    return 1 if failed else 0


def _pct(value: float | None) -> str:
    """Format a 0..1 ratio as a percentage, or '—' when the metric is absent.

    Retrieval-only rows carry no answer-accuracy; answer-correctness rows may
    carry no page coverage. Either is legitimately ``None`` and must render as
    a dash, not crash an f-string ``.2%`` format.
    """
    if value is None:
        return "—"
    return f"{value:.2%}"


def render_markdown(data: list[dict]) -> str:
    """Render the versioned benchmark report from raw benchmark rows.

    Pure function (no IO) so it is deterministically testable. Surfaces both
    retrieval coverage and GRO-89 answer-correctness, keyed by
    ``architecture_version`` so any two versions are one glance apart (GRO-105).
    """
    # Group by (architecture_version, dataset_id, type, subject) and keep the latest
    latest = {}
    for row in data:
        key = (row["architecture_version"], row["dataset_id"], row.get("type", "overall"), row["subject"])
        latest[key] = row

    md_lines = [
        "# DIM AI Evaluation Results",
        "",
        "Versioned benchmark report (GRO-105), rendered from `data/evals/benchmarks.jsonl`.",
        "Do not hand-edit — regenerate with `python scripts/render_eval_report.py`.",
        "",
        "Columns: retrieval coverage (right page) + answer-correctness (GRO-89).",
        "`—` means the metric was not measured for that row.",
        "",
    ]

    datasets = sorted(set(k[1] for k in latest.keys()))
    for dataset in datasets:
        md_lines.append(f"## Dataset: `{dataset}`")
        md_lines.append("")

        archs = set(k[0] for k in latest.keys() if k[1] == dataset)
        for arch in sorted(archs, reverse=True):
            md_lines.append(f"### Architecture: `{arch}`")
            md_lines.append("")
            md_lines.append("| Type | Subject | Count | Recall@5 | Recall@10 | Cov@5 | Full-Cov@5 | Answer-Acc |")
            md_lines.append("|---|---|---|---|---|---|---|---|")

            # Sort subjects so overall is first
            subjects = [(k[2], k[3]) for k in latest.keys() if k[0] == arch and k[1] == dataset]
            subjects = sorted(subjects, key=lambda x: (x[0] != "overall", x[0], x[1] != "overall", x[1]))
            for q_type, subj in subjects:
                row = latest[(arch, dataset, q_type, subj)]
                count = row.get("count", 0)
                r5 = _pct(row.get("recall@5"))
                r10 = _pct(row.get("recall@10"))
                c5 = _pct(row.get("coverage@5", row.get("page_recall@5")))
                fc5 = _pct(row.get("fully_covered@5", row.get("page_recall@5")))
                acc = _pct(row.get("answer_accuracy"))
                md_lines.append(f"| {q_type} | {subj} | {count} | {r5} | {r10} | {c5} | {fc5} | {acc} |")

            md_lines.append("")

    return "\n".join(md_lines)


def main() -> None:
    benchmarks_path = Path("data/evals/benchmarks.jsonl")
    if not benchmarks_path.exists():
        print("No benchmarks found.")
        return

    data = []
    with open(benchmarks_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data.append(json.loads(line))

    out_path = Path("docs/EVAL_RESULTS.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(data))
    print(f"Report generated at {out_path}")

if __name__ == "__main__":
    main()

