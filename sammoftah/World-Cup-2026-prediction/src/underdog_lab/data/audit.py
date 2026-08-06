from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


TEAM_PATTERN = re.compile(
    r"\b(?:Canada|Mexico|Norway|Sweden|Senegal|Nigeria|Australia|New Zealand|"
    r"Colombia|Ecuador|Poland|Austria|Tunisia|Algeria|South Africa|Ghana)\b",
    re.IGNORECASE,
)


def load(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", TEAM_PATTERN.sub("<TEAM>", text).lower()).strip()


def summarize(rows: list[dict]) -> dict:
    texts = [row["text"] for row in rows]
    case_types = Counter(row.get("case_type", "unknown") for row in rows)
    return {
        "rows": len(rows),
        "unique_texts": len(set(texts)),
        "unique_normalized_texts": len({normalize(text) for text in texts}),
        "case_types": dict(case_types),
        "multi_factor": sum(len(row["expected"]["factors"]) > 1 for row in rows),
        "unsupported": sum(bool(row["expected"]["unsupported_claims"]) for row in rows),
        "ambiguous": sum(bool(row["expected"]["ambiguities"]) for row in rows),
    }
