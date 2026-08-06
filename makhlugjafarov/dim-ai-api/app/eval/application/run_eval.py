from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import httpx
    import yaml
except ImportError:
    print(
        "Missing dependencies. Install with:\n"
        "  pip install httpx pyyaml\n"
        "Or activate the API venv: . apps/api/.venv/bin/activate",
        file=sys.stderr,
    )
    sys.exit(1)

from app.eval.domain.metrics import EvalQuestion, EvalResult, _confidence_value
from app.eval.infrastructure.api_client import evaluate_question
from app.eval.application.render_report import build_review_queue, report


def load_eval_file(path: Path) -> tuple[str, list[EvalQuestion]]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    dataset_id = data.get("dataset_id", path.stem)
    questions = []
    for raw in data.get("questions", []):
        expected = raw.get("expected") or {}
        questions.append(
            EvalQuestion(
                id=raw["id"],
                question=raw["question"],
                type=raw.get("type", "factual"),
                subject=raw.get("subject"),
                grade=raw.get("grade"),
                language=raw.get("language", "az"),
                expected_source_id=expected.get("source_id"),
                expected_source_label=expected.get("source_label"),
                expected_page=expected.get("page"),
                expected_pages=expected.get("pages") or ([expected.get("page")] if expected.get("page") is not None else None),
                expected_answer=expected.get("answer"),  # GRO-89
                tags=raw.get("tags", []),
            )
        )
    return dataset_id, questions


def run_eval(
    questions: list[EvalQuestion],
    api_url: str,
    top_k: int = 10,
    recall_target: float = 0.5,
    byok_key: str | None = None,
    byok_model: str | None = None,
) -> list[EvalResult]:
    results: list[EvalResult] = []
    client = httpx.Client(timeout=120.0)

    for i, q in enumerate(questions):
        print(f"Evaluating {i+1}/{len(questions)}: {q.id}...", flush=True)
        result = evaluate_question(
            q=q,
            api_url=api_url,
            top_k=top_k,
            client=client,
            byok_key=byok_key,
            byok_model=byok_model,
        )
        results.append(result)
        time.sleep(3.0) # Base delay between requests

    client.close()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="DIM AI retrieval eval runner")
    parser.add_argument(
        "--eval-file",
        default="data/evals/dim_eval_set.example.yaml",
        help="Path to eval YAML (default: data/evals/dim_eval_set.example.yaml)",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="Base URL of the running API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Max citations to retrieve per question (default: 10)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Run only the first N questions for a quick smoke gate",
    )
    parser.add_argument(
        "--recall-target",
        type=float,
        default=0.5,
        help="Minimum Recall@5 to pass (default: 0.5)",
    )
    parser.add_argument(
        "--json-output",
        help="Write full results as JSON to this file",
    )
    parser.add_argument(
        "--review-output",
        help="Write weak/error/slow questions as a manual-review JSON queue",
    )
    parser.add_argument(
        "--weak-confidence-threshold",
        type=float,
        default=0.6,
        help="Confidence below this 0-1 threshold is queued for review (default: 0.6)",
    )
    parser.add_argument(
        "--slow-ms",
        type=float,
        default=10000,
        help="Latency at or above this value is queued for review (default: 10000)",
    )
    parser.add_argument(
        "--version",
        type=str,
        help="Architecture version for benchmark logging (e.g., dense_v1)",
    )
    # GRO-89: BYOK args for answer-correctness grading
    parser.add_argument(
        "--byok-model",
        type=str,
        default=None,
        help="LLM model name for BYOK generation (e.g., gemini-1.5-flash, gpt-4o-mini). "
             "When set together with --byok-key, the eval sends the generation block and "
             "grades answers against expected.answer.",
    )
    parser.add_argument(
        "--byok-key",
        type=str,
        default=None,
        help="BYOK API key. Alternatively set DIM_EVAL_BYOK_KEY env var. "
             "Key is never written to logs or output files.",
    )
    args = parser.parse_args()

    eval_path = Path(args.eval_file)
    if not eval_path.exists():
        print(f"Eval file not found: {eval_path}", file=sys.stderr)
        sys.exit(1)

    dataset_id, questions = load_eval_file(eval_path)
    if args.limit is not None:
        if args.limit <= 0:
            print("--limit must be greater than 0", file=sys.stderr)
            sys.exit(1)
        questions = questions[: args.limit]
    print(f"Loaded {len(questions)} questions from {eval_path}")
    print(f"Running against {args.api_url} …")

    # GRO-89: resolve BYOK key (CLI flag > env var)
    byok_key: str | None = args.byok_key or __import__("os").environ.get("DIM_EVAL_BYOK_KEY")
    if byok_key and args.byok_model:
        print(f"BYOK grading enabled: model={args.byok_model} (key redacted)")
    elif byok_key and not args.byok_model:
        print("WARNING: --byok-key set but --byok-model is missing; grading disabled.", file=sys.stderr)
        byok_key = None

    results = run_eval(
        questions,
        args.api_url,
        top_k=args.top_k,
        recall_target=args.recall_target,
        byok_key=byok_key,
        byok_model=args.byok_model,
    )

    if args.json_output:
        output = [
            {
                "id": r.question_id,
                "latency_ms": r.latency_ms,
                "confidence": _confidence_value(r.confidence),
                "citations": r.citations,
                "answer_snippet": r.answer_snippet,
                "error": r.error,
                "answer_correct": r.answer_correct,  # GRO-89
            }
            for r in results
        ]
        Path(args.json_output).write_text(json.dumps(output, ensure_ascii=False, indent=2))
        print(f"Results written to {args.json_output}")

    if args.review_output:
        review_queue = build_review_queue(
            questions,
            results,
            weak_confidence_threshold=args.weak_confidence_threshold,
            slow_ms=args.slow_ms,
        )
        Path(args.review_output).write_text(
            json.dumps([item.__dict__ for item in review_queue], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Review queue written to {args.review_output} ({len(review_queue)} items)")

    exit_code = report(
        dataset_id,
        questions,
        results,
        recall_target=args.recall_target,
        weak_confidence_threshold=args.weak_confidence_threshold,
        architecture_version=args.version,
    )
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
