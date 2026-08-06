"""
run_fetcher.py — CLI entry point for Phase 1.1 (Fetcher only).

Usage:
    # Smoke test — small sample per source (fast, for validation)
    python -m src.ingestion.run_fetcher --mode smoke

    # Full fetch — production caps (slow)
    python -m src.ingestion.run_fetcher --mode full

    # Specific sources only
    python -m src.ingestion.run_fetcher --mode smoke --sources trustpilot,youtube
    python -m src.ingestion.run_fetcher --mode smoke --sources play_store,app_store

    # Dry run — print config without making any HTTP calls
    python -m src.ingestion.run_fetcher --mode smoke --dry-run

Outputs:
    data/raw/play_store/         — raw Play Store API responses
    data/raw/app_store/          — raw App Store RSS feed pages
    data/raw/reddit/             — manually curated Reddit entries
    data/raw/spotify_community/  — raw Spotify Community Forum pages
    data/raw/trustpilot/         — raw Trustpilot review pages
    data/raw/youtube/            — raw YouTube comment API responses

Run summary is printed to stdout when done.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging setup — configure before importing sub-modules
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_fetcher")


# ---------------------------------------------------------------------------
# Source registry
# ---------------------------------------------------------------------------
AVAILABLE_SOURCES = (
    "play_store",
    "app_store",
    "reddit",
    "spotify_community",
    "trustpilot",
    "youtube",
)


def _build_fetcher(source: str, mode: str):
    """Instantiate the correct fetcher for `source`."""
    if source == "play_store":
        from src.ingestion.fetchers.play_store import PlayStoreFetcher
        return PlayStoreFetcher(mode=mode)
    if source == "app_store":
        from src.ingestion.fetchers.app_store import AppStoreFetcher
        return AppStoreFetcher(mode=mode)
    if source == "reddit":
        from src.ingestion.fetchers.reddit import RedditFetcher
        return RedditFetcher(mode=mode)
    if source == "spotify_community":
        from src.ingestion.fetchers.spotify_community import SpotifyCommunityFetcher
        return SpotifyCommunityFetcher(mode=mode)
    if source == "trustpilot":
        from src.ingestion.fetchers.trustpilot import TrustpilotFetcher
        return TrustpilotFetcher(mode=mode)
    if source == "youtube":
        from src.ingestion.fetchers.youtube import YouTubeFetcher
        return YouTubeFetcher(mode=mode)
    raise ValueError(f"Unknown source: '{source}'")


# ---------------------------------------------------------------------------
# Main async runner
# ---------------------------------------------------------------------------

async def run(sources: list[str], mode: str) -> dict[str, list]:
    """Run all requested fetchers sequentially and return raw records."""
    results: dict[str, list] = {}

    for source in sources:
        logger.info("=" * 60)
        logger.info("Fetching source: %s (mode=%s)", source, mode)
        logger.info("=" * 60)
        t0 = time.monotonic()

        fetcher = _build_fetcher(source, mode)
        try:
            records = await fetcher.fetch()
        except Exception as exc:
            logger.error("Source '%s' failed: %s", source, exc, exc_info=True)
            records = []

        elapsed = time.monotonic() - t0
        logger.info(
            "Source '%s' complete: %d records in %.1f s",
            source, len(records), elapsed,
        )
        results[source] = records

    return results


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def print_summary(results: dict[str, list], mode: str, elapsed_s: float) -> None:
    """Print a human-readable run summary table."""
    from src.ingestion.config import get_caps
    caps = get_caps(mode)

    cap_map = {
        "play_store": caps.play_store,
        "app_store": caps.app_store,
        "reddit": caps.reddit,
        "spotify_community": caps.spotify_community,
        "trustpilot": caps.trustpilot,
        "youtube": caps.youtube,
    }

    total = sum(len(v) for v in results.values())

    print("\n" + "=" * 62)
    print(f"  FETCH SUMMARY  |  mode={mode}  |  elapsed={elapsed_s:.1f}s")
    print("=" * 62)
    print(f"  {'Source':<22}  {'Collected':>10}  {'Cap':>6}  {'Fill %':>7}")
    print("  " + "-" * 58)
    for source, records in results.items():
        cap = cap_map.get(source, "?")
        pct = (len(records) / cap * 100) if isinstance(cap, int) and cap > 0 else 0
        status = "OK  " if len(records) > 0 else "FAIL"
        print(f"  [{status}] {source:<21}  {len(records):>10}  {cap:>6}  {pct:>6.1f}%")
    print("  " + "-" * 58)
    print(f"  {'TOTAL':<22}  {total:>10}")
    print("=" * 62)
    print()

    if total == 0:
        print("  [WARNING] No records collected. Check logs above for errors.")
    else:
        from src.ingestion.config import RAW_DIR
        print(f"  Raw files saved to: {RAW_DIR}")
        print("  Next step: run the Extractor (Phase 1.2) on these raw files.")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 1.1 Fetcher — Spotify Review Discovery Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--mode",
        choices=("smoke", "full"),
        default="smoke",
        help="'smoke' = small sample for quick validation; 'full' = production caps (default: smoke)",
    )
    parser.add_argument(
        "--sources",
        default=",".join(AVAILABLE_SOURCES),
        help="Comma-separated list of sources to fetch (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print config and exit without making HTTP calls",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Parse sources
    sources_requested = [s.strip() for s in args.sources.split(",") if s.strip()]
    invalid = [s for s in sources_requested if s not in AVAILABLE_SOURCES]
    if invalid:
        parser.error(f"Unknown sources: {invalid}. Choose from: {list(AVAILABLE_SOURCES)}")

    # Dry run
    if args.dry_run:
        from src.ingestion.config import get_caps, get_cutoff_date, RAW_DIR
        caps = get_caps(args.mode)
        cutoff = get_cutoff_date()
        print("\n[DRY RUN] Configuration:")
        print(f"  Mode:    {args.mode}")
        print(f"  Sources: {sources_requested}")
        print(f"  Caps:")
        print(f"    play_store       = {caps.play_store}")
        print(f"    app_store        = {caps.app_store}")
        print(f"    reddit           = {caps.reddit} (manual curation)")
        print(f"    spotify_community= {caps.spotify_community}")
        print(f"    trustpilot       = {caps.trustpilot}")
        print(f"    youtube          = {caps.youtube}")
        print(f"  Cutoff:  {cutoff.strftime('%Y-%m-%d')} (4 months back)")
        print(f"  Output:  {RAW_DIR}")
        print("\nNo HTTP calls made (--dry-run). Remove flag to run.\n")
        sys.exit(0)

    # Run
    logger.info("Starting Phase 1.1 Fetcher  |  mode=%s  |  sources=%s", args.mode, sources_requested)
    t_start = time.monotonic()

    results = asyncio.run(run(sources_requested, args.mode))

    elapsed = time.monotonic() - t_start
    print_summary(results, args.mode, elapsed)


if __name__ == "__main__":
    main()
