"""Phase 3 CLI — chunk, embed, and index relevant review records."""

from __future__ import annotations

import argparse
import json
import logging
import time
from collections import Counter
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.embedding.config import (
    DEFAULT_CHUNKS_OUTPUT,
    DEFAULT_INPUT,
    DEFAULT_META_OUTPUT,
    EMBEDDING_MODEL,
)
from src.embedding.embedder import BGEEmbedder
from src.embedding.text_chunker import TextChunker
from src.embedding.vector_store import ReviewVectorStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_phase3")


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


def filter_records(
    records: list[dict[str, Any]],
    *,
    english_only: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Keep only records suitable for embedding."""
    stats = Counter()
    filtered: list[dict[str, Any]] = []

    for record in records:
        stats["input_total"] += 1

        if record.get("relevance_status") != "classified":
            stats["skipped_unclassified"] += 1
            continue

        if record.get("relevant") is not True:
            stats["skipped_irrelevant"] += 1
            continue

        if english_only and record.get("lang") != "en":
            stats["skipped_non_english"] += 1
            continue

        text = (record.get("text") or "").strip()
        if not text:
            stats["skipped_empty_text"] += 1
            continue

        filtered.append(record)
        stats["selected"] += 1

    return filtered, dict(stats)


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3: Embedding & Indexing")
    parser.add_argument("--mode", choices=("smoke", "full"), default="smoke")
    parser.add_argument("--input", type=str, default=str(DEFAULT_INPUT))
    parser.add_argument("--chunks-output", type=str, default=str(DEFAULT_CHUNKS_OUTPUT))
    parser.add_argument("--meta", type=str, default=str(DEFAULT_META_OUTPUT))
    parser.add_argument("--chroma-path", type=str, default="data/index/chroma")
    parser.add_argument("--reset-index", action="store_true", help="Delete and rebuild the Chroma collection")
    parser.add_argument("--all-langs", action="store_true", help="Embed non-English records too")
    args = parser.parse_args()
    load_dotenv()

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("Input file not found: %s", input_path)
        return

    start_time = time.time()
    logger.info("Starting Phase 3 | mode=%s", args.mode)

    records = load_jsonl(input_path)
    logger.info("Loaded %d records from %s", len(records), input_path)

    selected, filter_stats = filter_records(records, english_only=not args.all_langs)
    logger.info(
        "Selected %d records for embedding (skipped: %d unclassified, %d irrelevant, %d non-English, %d empty)",
        filter_stats.get("selected", 0),
        filter_stats.get("skipped_unclassified", 0),
        filter_stats.get("skipped_irrelevant", 0),
        filter_stats.get("skipped_non_english", 0),
        filter_stats.get("skipped_empty_text", 0),
    )

    if args.mode == "smoke":
        selected = selected[:20]
        logger.info("Smoke mode: truncating to %d records", len(selected))

    if not selected:
        logger.error("No records selected for embedding. Exiting.")
        return

    chunker = TextChunker()
    chunks = chunker.chunk(selected)
    logger.info("Produced %d chunks from %d records", len(chunks), len(selected))

    save_jsonl(chunks, Path(args.chunks_output))
    logger.info("Saved chunks to %s", args.chunks_output)

    embedder = BGEEmbedder()
    texts = [chunk.get("text", "") for chunk in chunks]
    embeddings = embedder.embed_texts(texts)

    vector_store = ReviewVectorStore(
        persist_path=args.chroma_path,
        reset=args.reset_index or args.mode == "smoke",
    )
    indexed_count = vector_store.upsert_chunks(chunks, embeddings)
    logger.info("Indexed %d chunks in ChromaDB (%s)", indexed_count, args.chroma_path)

    source_counts = Counter(chunk.get("source", "unknown") for chunk in chunks)
    multi_chunk_records = sum(1 for record in selected if len(chunker.chunk_record(record)) > 1)
    duration = time.time() - start_time

    embedding_dim = len(embeddings[0]) if embeddings else 0

    meta = {
        "indexed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": args.mode,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimensions": embedding_dim,
        "filter_stats": filter_stats,
        "records_selected": len(selected),
        "chunks_created": len(chunks),
        "chunks_indexed": indexed_count,
        "vector_store_count": vector_store.count(),
        "multi_chunk_records": multi_chunk_records,
        "source_distribution": dict(source_counts),
        "chroma_path": args.chroma_path,
        "chunks_output": args.chunks_output,
        "duration_seconds": round(duration, 2),
    }

    meta_path = Path(args.meta)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as handle:
        json.dump(meta, handle, indent=2)

    logger.info("Saved meta to %s", meta_path)
    logger.info("Phase 3 complete in %.1fs", duration)


if __name__ == "__main__":
    main()
