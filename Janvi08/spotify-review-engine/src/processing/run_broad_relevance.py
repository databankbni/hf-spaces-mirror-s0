"""Re-classify relevant=false records with a broader discovery relevance definition."""

from __future__ import annotations

import argparse
import json
import logging
import time
from collections import Counter
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.processing.broad_relevance_filter import BroadRelevanceFilter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_broad_relevance")


def load_jsonl(filepath: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with open(filepath, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def save_jsonl(records: list[dict[str, Any]], filepath: Path) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def select_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Records originally marked irrelevant and successfully classified in Phase 2."""
    return [
        record
        for record in records
        if record.get("relevant") is False and record.get("relevance_status") == "classified"
    ]


def select_retry_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if record.get("relevant_broad_status") == "quota_exhausted"]


def compute_stats(records: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    candidate_ids = {id(record) for record in candidates}

    newly_broad_true_by_source: Counter[str] = Counter()
    broad_status_counts: Counter[str] = Counter()
    broad_value_counts: Counter[bool | None] = Counter()

    for record in records:
        status = record.get("relevant_broad_status")
        if status:
            broad_status_counts[status] += 1

        broad_value = record.get("relevant_broad")
        if id(record) in candidate_ids or status:
            broad_value_counts[broad_value] += 1

        if (
            id(record) in candidate_ids
            and record.get("relevant") is False
            and record.get("relevant_broad") is True
            and record.get("relevant_broad_status") == "classified"
        ):
            newly_broad_true_by_source[record.get("source", "unknown")] += 1

    return {
        "candidate_pool_size": len(candidates),
        "newly_relevant_broad_true": sum(newly_broad_true_by_source.values()),
        "newly_relevant_broad_true_by_source": dict(newly_broad_true_by_source),
        "relevant_broad_status_distribution": dict(broad_status_counts),
        "relevant_broad_value_distribution": {
            "true": broad_value_counts.get(True, 0),
            "false": broad_value_counts.get(False, 0),
            "null": broad_value_counts.get(None, 0),
        },
        "quota_exhausted_remaining": broad_status_counts.get("quota_exhausted", 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Broad relevance re-classification for previously irrelevant records",
    )
    parser.add_argument(
        "--mode",
        choices=("smoke", "full", "retry-exhausted-broad"),
        default="full",
        help="smoke=20 candidates, full=all candidates, retry-exhausted-broad=resume quota_exhausted",
    )
    parser.add_argument(
        "--input",
        type=str,
        default="data/output/reviews_clean.jsonl",
        help="Source dataset (ignored in retry mode)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/output/reviews_broad.jsonl",
        help="Output dataset with relevant_broad fields",
    )
    parser.add_argument(
        "--meta",
        type=str,
        default="data/output/broad_relevance_meta.json",
        help="Run summary metadata",
    )
    args = parser.parse_args()

    load_dotenv()

    output_path = Path(args.output)
    if args.mode == "retry-exhausted-broad":
        if not output_path.exists():
            logger.error("Output file %s not found for retry mode.", output_path)
            return
        records = load_jsonl(output_path)
        to_process = select_retry_candidates(records)
        logger.info("Retry mode: %d quota_exhausted records to resume.", len(to_process))
    else:
        input_path = Path(args.input)
        if not input_path.exists():
            logger.error("Input file %s not found.", input_path)
            return
        records = load_jsonl(input_path)
        to_process = select_candidates(records)
        logger.info(
            "Loaded %d records; %d candidates with relevant=false (classified).",
            len(records),
            len(to_process),
        )

    if args.mode == "smoke":
        to_process = to_process[:20]
        logger.info("Smoke mode: processing %d candidates.", len(to_process))

    if not to_process:
        logger.info("Nothing to process. Exiting.")
        return

    try:
        filterer = BroadRelevanceFilter()
    except ValueError as exc:
        logger.error(str(exc))
        logger.error("Cannot proceed without GROQ_API_KEY")
        return

    start_time = time.time()
    batch_size = filterer.batch_size
    total_batches = (len(to_process) + batch_size - 1) // batch_size
    quota_exhausted = False

    logger.info(
        "Starting broad relevance classification | batch_size=%d delay=%.1fs batches=%d",
        batch_size,
        filterer.batch_delay,
        total_batches,
    )

    for batch_index in range(0, len(to_process), batch_size):
        batch = to_process[batch_index : batch_index + batch_size]
        batch_number = batch_index // batch_size + 1
        logger.info("Processing batch %d/%d", batch_number, total_batches)

        quota_exhausted = filterer.process_batch(batch)
        if quota_exhausted:
            remaining = to_process[batch_index + batch_size :]
            logger.warning(
                "Quota exhausted at batch %d. Marking %d remaining records as quota_exhausted.",
                batch_number,
                len(remaining),
            )
            for record in remaining:
                record["relevant_broad"] = None
                record["relevant_broad_status"] = "quota_exhausted"
            break

    duration = time.time() - start_time
    candidates = select_candidates(records)
    stats = compute_stats(records, candidates)

    save_jsonl(records, output_path)
    logger.info("Saved %d records to %s", len(records), output_path)

    meta = {
        "processed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": args.mode,
        "input": str(args.input) if args.mode != "retry-exhausted-broad" else str(output_path),
        "output": str(output_path),
        "quota_exhausted_mid_run": quota_exhausted,
        "duration_seconds": round(duration, 2),
        **stats,
    }

    meta_path = Path(args.meta)
    with open(meta_path, "w", encoding="utf-8") as handle:
        json.dump(meta, handle, indent=2)
    logger.info("Saved meta to %s", meta_path)

    logger.info("--- Broad Relevance Summary ---")
    logger.info(
        "Newly marked relevant_broad=true: %d",
        stats["newly_relevant_broad_true"],
    )
    for source, count in sorted(stats["newly_relevant_broad_true_by_source"].items()):
        logger.info("  %s: %d", source, count)
    logger.info("Quota exhausted remaining: %d", stats["quota_exhausted_remaining"])
    logger.info("Broad classification complete.")


if __name__ == "__main__":
    main()
