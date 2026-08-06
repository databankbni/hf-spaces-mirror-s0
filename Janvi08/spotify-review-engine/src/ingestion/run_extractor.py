"""
run_extractor.py — CLI entry point for Phase 1.2 & 1.3 (Extractor and Cleaner).

Usage:
    # Run extractor on smoke-test raw data
    python -m src.ingestion.run_extractor --mode smoke

    # Run extractor on full-fetch raw data
    python -m src.ingestion.run_extractor --mode full

    # Specific sources only
    python -m src.ingestion.run_extractor --mode smoke --sources trustpilot,youtube
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dateutil import parser as du_parser

from src.ingestion.config import (
    RAW_DIR,
    OUTPUT_DIR,
    get_caps,
    get_cutoff_date,
)

AVAILABLE_SOURCES = (
    "play_store",
    "app_store",
    "reddit",
    "spotify_community",
    "trustpilot",
    "youtube",
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_extractor")


# ---------------------------------------------------------------------------
# Extractor registry
# ---------------------------------------------------------------------------
def _build_extractor(source: str):
    """Instantiate the correct extractor for `source`."""
    if source == "play_store":
        from src.ingestion.extractors.play_store import PlayStoreExtractor
        return PlayStoreExtractor()
    if source == "app_store":
        from src.ingestion.extractors.app_store import AppStoreExtractor
        return AppStoreExtractor()
    if source == "reddit":
        from src.ingestion.extractors.reddit import RedditExtractor
        return RedditExtractor()
    if source == "spotify_community":
        from src.ingestion.extractors.spotify_community import SpotifyCommunityExtractor
        return SpotifyCommunityExtractor()
    if source == "trustpilot":
        from src.ingestion.extractors.trustpilot import TrustpilotExtractor
        return TrustpilotExtractor()
    if source == "youtube":
        from src.ingestion.extractors.youtube import YouTubeExtractor
        return YouTubeExtractor()
    raise ValueError(f"Unknown source: '{source}'")


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------
def load_raw_data(source: str) -> list[dict[str, Any]]:
    """Load and combine all raw JSON/JSONL files for a given source.

    Skips 'meta.json' files.
    """
    source_dir = RAW_DIR / source
    if not source_dir.exists():
        logger.warning("Source directory %s does not exist", source_dir)
        return []

    combined_raw: list[dict] = []

    # Find JSON files
    for filepath in sorted(source_dir.glob("*.json")):
        if filepath.name == "meta.json":
            continue
        try:
            content = filepath.read_text(encoding="utf-8").strip()
            if not content:
                continue
            data = json.loads(content)
            if isinstance(data, list):
                combined_raw.extend(data)
            elif isinstance(data, dict):
                # Spotify Community Forum metadata stub page check
                # If it's a page metadata stub, check if we stored items in it.
                # If we saved result_items directly (which is a list), it falls under the list check above.
                combined_raw.append(data)
        except Exception as exc:
            logger.error("Failed to load raw JSON from %s: %s", filepath.name, exc)

    # Find JSONL files
    for filepath in sorted(source_dir.glob("*.jsonl")):
        try:
            content = filepath.read_text(encoding="utf-8").strip()
            if not content:
                continue
            for line_num, line in enumerate(content.splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    combined_raw.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    logger.warning("Invalid JSON at %s:%d — %s", filepath.name, line_num, exc)
        except Exception as exc:
            logger.error("Failed to load raw JSONL from %s: %s", filepath.name, exc)

    return combined_raw


# ---------------------------------------------------------------------------
# Pre-cleaner (Sub-Phase 1.3)
# ---------------------------------------------------------------------------
def normalise_text(t: str) -> str:
    """Strip null bytes, BOM markers, non-printable control characters, and white space."""
    if not t:
        return ""
    # Strip null bytes and BOM
    t = t.replace("\x00", "").replace("\ufeff", "")
    # Keep only printable characters and basic white space (newlines, tabs)
    t = "".join(char for char in t if char.isprintable() or char in "\n\r\t")
    return t.strip()


def validate_schema(record: dict[str, Any]) -> bool:
    """Validate that the record has all required fields with non-empty values when appropriate."""
    required_keys = {"source", "text", "rating", "date", "url", "thread_or_context"}
    # Check that all keys are present
    if not required_keys.issubset(record.keys()):
        return False
    # Source and Text must be non-empty strings
    if not record.get("source") or not isinstance(record.get("source"), str):
        return False
    if not record.get("text") or not isinstance(record.get("text"), str):
        return False
    return True


def clean_records(
    records: list[dict[str, Any]],
    cutoff: datetime,
    seen_hashes: set[str],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Apply lightweight pre-cleaning to the extracted records.

    - Text normalisation (UTF-8, BOM removal, strip control chars)
    - Empty-text removal
    - Date parsing & lookback validation (4-month window)
    - Schema validation
    - Deduplication (cross-source and within-source text hashing)
    """
    cleaned: list[dict[str, Any]] = []
    stats = {
        "input": len(records),
        "empty_text_removed": 0,
        "date_invalid_removed": 0,
        "out_of_window_removed": 0,
        "malformed_removed": 0,
        "duplicate_removed": 0,
    }

    for record in records:
        # Schema validation (pre-cleaning check)
        if not validate_schema(record):
            stats["malformed_removed"] += 1
            continue

        # Normalise text
        text = normalise_text(record["text"])
        if not text:
            stats["empty_text_removed"] += 1
            continue
        record["text"] = text

        # Date validation & lookback check
        date_str = record["date"]
        if not date_str:
            stats["date_invalid_removed"] += 1
            continue

        try:
            dt = du_parser.parse(str(date_str))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
        except Exception:
            stats["date_invalid_removed"] += 1
            continue

        # Enforce lookback window
        if dt < cutoff:
            stats["out_of_window_removed"] += 1
            continue

        # Update date string to normalized ISO string
        record["date"] = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Deduplication
        text_hash = hashlib.sha256(text.lower().encode("utf-8")).hexdigest()
        if text_hash in seen_hashes:
            stats["duplicate_removed"] += 1
            continue
        seen_hashes.add(text_hash)

        cleaned.append(record)

    return cleaned, stats


# ---------------------------------------------------------------------------
# CLI Runner
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 1.2/1.3 Extractor & Pre-Cleaner — Spotify Review Discovery Engine",
    )
    parser.add_argument(
        "--mode",
        choices=("smoke", "full"),
        default="smoke",
        help="Capping configuration to validate outputs (default: smoke)",
    )
    parser.add_argument(
        "--sources",
        default=",".join(AVAILABLE_SOURCES),
        help="Comma-separated list of sources to process (default: all)",
    )

    args = parser.parse_args()

    sources_requested = [s.strip() for s in args.sources.split(",") if s.strip()]
    invalid = [s for s in sources_requested if s not in AVAILABLE_SOURCES]
    if invalid:
        parser.error(f"Unknown sources: {invalid}. Choose from: {list(AVAILABLE_SOURCES)}")

    logger.info("Starting Phase 1.2 Extractor & Phase 1.3 Cleaner")
    logger.info("  Mode:    %s", args.mode)
    logger.info("  Sources: %s", sources_requested)

    t0 = time.monotonic()
    cutoff_date = get_cutoff_date()
    logger.info("  Cutoff date (4 months lookback): %s", cutoff_date.strftime("%Y-%m-%d"))

    all_extracted_records: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()

    source_stats: dict[str, dict[str, int]] = {}

    for source in sources_requested:
        logger.info("-" * 50)
        logger.info("Processing source: %s", source)

        # 1. Load raw files
        raw_data = load_raw_data(source)
        logger.info("  Loaded %d raw entries from data/raw/%s/", len(raw_data), source)

        if not raw_data:
            source_stats[source] = {"raw": 0, "extracted": 0}
            continue

        # 2. Extract
        try:
            extractor = _build_extractor(source)
            extracted_records = extractor.extract(raw_data)
            logger.info("  Extracted %d records matching unified schema", len(extracted_records))
        except Exception as exc:
            logger.error("  Extraction failed for source %s: %s", source, exc, exc_info=True)
            source_stats[source] = {"raw": len(raw_data), "extracted": 0, "error": 1}
            continue

        # 3. Clean
        cleaned_records, stats = clean_records(extracted_records, cutoff_date, seen_hashes)
        logger.info(
            "  Cleaner stats: input=%d, cleaned=%d, duplicates=%d, out-of-window=%d, malformed=%d",
            stats["input"],
            len(cleaned_records),
            stats["duplicate_removed"],
            stats["out_of_window_removed"],
            stats["malformed_removed"],
        )

        all_extracted_records.extend(cleaned_records)
        source_stats[source] = {
            "raw": len(raw_data),
            "extracted": len(cleaned_records),
            "duplicates": stats["duplicate_removed"],
            "out_of_window": stats["out_of_window_removed"],
            "malformed": stats["malformed_removed"],
            "empty": stats["empty_text_removed"],
            "date_invalid": stats["date_invalid_removed"],
        }

    # Sort final combined list by date descending (most recent first)
    all_extracted_records.sort(key=lambda x: x["date"], reverse=True)

    # Apply capping per source if necessary based on mode (caps was already checked in fetcher,
    # but since fetcher filter is soft or has duplicates, we can enforce caps here too).
    caps = get_caps(args.mode)
    cap_map = {
        "play_store": caps.play_store,
        "app_store": caps.app_store,
        "reddit": caps.reddit,
        "spotify_community": caps.spotify_community,
        "trustpilot": caps.trustpilot,
        "youtube": caps.youtube,
    }

    final_records: list[dict[str, Any]] = []
    source_counts: dict[str, int] = {s: 0 for s in AVAILABLE_SOURCES}

    for record in all_extracted_records:
        src = record["source"]
        cap = cap_map.get(src, 99999)
        if source_counts[src] < cap:
            final_records.append(record)
            source_counts[src] += 1

    # Write output JSONL
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "reviews_raw.jsonl"

    with open(output_file, "w", encoding="utf-8") as fh:
        for record in final_records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Construct and write meta.json
    total_duration = time.monotonic() - t0
    min_date = final_records[-1]["date"][:10] if final_records else "N/A"
    max_date = final_records[0]["date"][:10] if final_records else "N/A"

    meta_content = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date_range": f"{min_date} to {max_date}",
        "counts": source_counts,
        "total": len(final_records),
        "status": "success",
        "errors": [s for s, stats in source_stats.items() if "error" in stats],
        "duration_seconds": round(total_duration, 2),
    }

    meta_file = OUTPUT_DIR / "meta.json"
    with open(meta_file, "w", encoding="utf-8") as fh:
        json.dump(meta_content, fh, ensure_ascii=False, indent=2)

    logger.info("=" * 60)
    logger.info("EXTRACTION AND PRE-CLEANING COMPLETE")
    logger.info("=" * 60)
    logger.info("  Combined records:  %d", len(final_records))
    logger.info("  Output JSONL:      %s", output_file)
    logger.info("  Output meta:       %s", meta_file)
    logger.info("  Date range:        %s", meta_content["date_range"])
    logger.info("-" * 50)
    for src, count in source_counts.items():
        cap = cap_map.get(src, 0)
        logger.info("  %-20s: %d / %d (Cap)", src, count, cap)
    logger.info("-" * 50)
    logger.info("Total duration: %.2f seconds", total_duration)


if __name__ == "__main__":
    main()
