from __future__ import annotations

import argparse
import json
from pathlib import Path

from underdog_lab.data.audit import load, normalize, summarize


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, default=Path("data/scenarios/train.jsonl"))
    parser.add_argument("--validation", type=Path, default=Path("data/scenarios/validation.jsonl"))
    parser.add_argument("--test", type=Path, default=Path("data/scenarios/test.jsonl"))
    args = parser.parse_args()

    splits = {
        "train": load(args.train),
        "validation": load(args.validation),
        "test": load(args.test),
    }
    report = {name: summarize(rows) for name, rows in splits.items()}
    normalized = {
        name: {normalize(row["text"]) for row in rows} for name, rows in splits.items()
    }
    overlaps = {
        "train_validation": len(normalized["train"] & normalized["validation"]),
        "train_test": len(normalized["train"] & normalized["test"]),
        "validation_test": len(normalized["validation"] & normalized["test"]),
    }
    report["normalized_overlap"] = overlaps
    print(json.dumps(report, indent=2))

    failures = []
    for name, summary in report.items():
        if name == "normalized_overlap":
            continue
        if summary["unique_texts"] != summary["rows"]:
            failures.append(f"{name} contains literal duplicate texts")
        if summary["multi_factor"] == 0:
            failures.append(f"{name} lacks multi-factor examples")
        if summary["unsupported"] == 0:
            failures.append(f"{name} lacks unsupported examples")
        if summary["ambiguous"] == 0:
            failures.append(f"{name} lacks ambiguous examples")
    if any(overlaps.values()):
        failures.append(f"normalized split overlap detected: {overlaps}")
    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
