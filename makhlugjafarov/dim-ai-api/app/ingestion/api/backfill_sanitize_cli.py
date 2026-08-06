import argparse
import json
import sys
from pathlib import Path

from app.ingestion.domain.sanitize import sanitize_ocr_text

def _diff_summary(original: list[dict], cleaned: list[dict]) -> list[dict]:
    """Return a list of changed pages with before/after text."""
    changes = []
    for orig, clean in zip(original, cleaned):
        orig_text = orig.get("text", "")
        clean_text = clean.get("text", "")
        if orig_text != clean_text:
            changes.append(
                {
                    "page_number": orig.get("page_number"),
                    "before": orig_text[:200],
                    "after": clean_text[:200],
                }
            )
    return changes


def backfill(input_path: Path, output_path: Path) -> None:
    print(f"Reading {input_path} …")
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: could not read input file: {exc}", file=sys.stderr)
        sys.exit(1)

    pages = data.get("pages", [])
    if not pages:
        print("WARNING: no pages found in input file.", file=sys.stderr)

    cleaned_pages = []
    for entry in pages:
        raw_text = entry.get("text", "")
        cleaned_text = sanitize_ocr_text(raw_text)
        cleaned_pages.append({**entry, "text": cleaned_text})

    changes = _diff_summary(pages, cleaned_pages)

    print("\nSanitize summary:")
    print(f"  Total pages:    {len(pages)}")
    print(f"  Changed pages:  {len(changes)}")
    print(f"  Unchanged:      {len(pages) - len(changes)}")

    if changes:
        print("\n  First 5 changed pages (before/after preview):")
        for change in changes[:5]:
            print(f"\n  [Page {change['page_number']}]")
            print(f"    BEFORE: {change['before']!r}")
            print(f"    AFTER:  {change['after']!r}")

    cleaned_data = {**data, "pages": cleaned_pages}
    output_path.write_text(
        json.dumps(cleaned_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nCleaned JSON written to {output_path}")
    print(
        "\nNOTE: Opus to run the prod backfill of the affected rows after merge.\n"
        "Do NOT run the loader against prod until the sanitized JSON has been reviewed."
    )


def backfill_sanitize_main() -> None:
    parser = argparse.ArgumentParser(description="Offline OCR sanitizer backfill (GRO-88)")
    parser.add_argument("input", type=Path, help="Path to the pages JSON artifact")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path (default: <input>_sanitized.json)",
    )
    args = parser.parse_args()

    input_path: Path = args.input
    if not input_path.exists():
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_path: Path = args.out or input_path.with_stem(input_path.stem + "_sanitized")
    backfill(input_path, output_path)

