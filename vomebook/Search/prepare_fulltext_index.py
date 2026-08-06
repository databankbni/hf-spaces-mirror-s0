#!/usr/bin/env python3
"""Activate a verified CCRD index generation from a mounted HF Storage Bucket."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
FULLTEXT_DIR = Path(os.environ.get("CCRD_FULLTEXT_DIR", str(BASE_DIR / "data/fulltext")))
BUCKET_DIR = os.environ.get("CCRD_INDEX_BUCKET_DIR", "").strip()
TOKENIZER_VERSION = "cjk-bigram-boundary-fts5-v6-snippet-anchors"
SOURCES = ("CCRD", "CW")
STATUS_PATH = FULLTEXT_DIR / "bucket-index-status.json"


def write_status(**payload: object) -> None:
    FULLTEXT_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATUS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(STATUS_PATH)


def validated_database(bucket: Path, source: str, details: object) -> Path:
    if not isinstance(details, dict):
        raise ValueError(f"{source}: missing manifest details")
    relative_path = details.get("path")
    expected_hash = details.get("sha256")
    expected_documents = details.get("documents")
    expected_fts_rows = details.get("fts_rows")
    expected_bytes = details.get("bytes")
    if not isinstance(relative_path, str) or not relative_path.startswith("generations/"):
        raise ValueError(f"{source}: invalid database path")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ValueError(f"{source}: invalid database hash")
    if not isinstance(expected_documents, int) or not isinstance(expected_fts_rows, int) or not isinstance(expected_bytes, int):
        raise ValueError(f"{source}: invalid document counts")

    path = (bucket / relative_path).resolve()
    if bucket not in path.parents or not path.is_file():
        raise ValueError(f"{source}: database is outside the bucket or missing")
    return path, expected_bytes


def copy_database(source: str, source_path: Path, expected_bytes: int) -> None:
    target = FULLTEXT_DIR / f"{source}.sqlite3"
    temporary = target.with_suffix(".sqlite3.bucket.tmp")
    temporary.unlink(missing_ok=True)
    with source_path.open("rb") as input_file, temporary.open("wb") as output_file:
        shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
        output_file.flush()
        os.fsync(output_file.fileno())
    if temporary.stat().st_size != expected_bytes:
        temporary.unlink(missing_ok=True)
        raise ValueError(f"{source}: copied database size mismatch")
    temporary.replace(target)


def main() -> int:
    if not BUCKET_DIR:
        write_status(state="disabled", reason="no_mount_path")
        return 1
    bucket = Path(BUCKET_DIR).resolve()
    manifest_path = bucket / "current.json"
    try:
        write_status(state="checking")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("format") != 1 or manifest.get("tokenizer_version") != TOKENIZER_VERSION:
            raise ValueError("invalid manifest version")
        databases = manifest.get("databases")
        if not isinstance(databases, dict):
            raise ValueError("missing databases manifest")
        paths = {source: validated_database(bucket, source, databases.get(source)) for source in SOURCES}
    except Exception as exc:
        write_status(
            state="unavailable",
            error=type(exc).__name__,
            detail=str(exc),
        )
        return 1

    FULLTEXT_DIR.mkdir(parents=True, exist_ok=True)
    for source, (path, expected_bytes) in paths.items():
        write_status(
            state="copying",
            source=source,
        )
        copy_database(source, path, expected_bytes)
    (FULLTEXT_DIR / "build-status.json").write_text(json.dumps({"state": "ready", "source": "bucket"}), encoding="utf-8")
    write_status(state="ready", sources=list(SOURCES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
