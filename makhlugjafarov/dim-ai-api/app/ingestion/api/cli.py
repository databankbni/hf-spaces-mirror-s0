import argparse
import json
import sys
from pathlib import Path

from app.ingestion.domain.manifest import load_manifest
from app.ingestion.application.corpus_coverage import coverage_summary, risky_sources

def _print_table(title: str, data: dict) -> None:
    print(f"\n  {title}")
    print("  " + "-" * 42)
    for key, count in data.items():
        print(f"  {str(key):<32} {count:>4}")


def corpus_coverage_main() -> int:
    parser = argparse.ArgumentParser(description="Corpus coverage audit")
    parser.add_argument("--manifest", required=True, help="Path to manifest YAML")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--allow-tbd", action="store_true", help="Load TBD/do_not_ingest entries for audit")
    args = parser.parse_args()

    try:
        manifest = load_manifest(
            Path(args.manifest),
            require_files=False,
            allow_tbd=True, # Ignoring allow_tbd arg as per old code where it hardcoded True
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    summary = coverage_summary(manifest.sources)
    risky = risky_sources(manifest.sources)

    if args.json:
        print(json.dumps({"summary": summary, "risky_sources": risky}, indent=2, ensure_ascii=False))
        return 1 if risky else 0

    print()
    print("=" * 48)
    print(f"  DIM AI Corpus Coverage — {manifest.corpus_version}")
    print("=" * 48)

    for section, data in summary.items():
        if isinstance(data, dict):
            _print_table(section, data)
        else:
            print(f"\n  {section}: {data}")

    if risky:
        print("\n" + "=" * 48)
        print("  ⚠  RISKY SOURCES (require attention before prod)")
        print("=" * 48)
        for entry in risky:
            print(f"\n  {entry['source_id']}  [{entry['title']}]")
            for reason in entry["reasons"]:
                print(f"    → {reason}")
        print()
        return 1

    print("\n  All sources are safe to ingest.\n")
    return 0
