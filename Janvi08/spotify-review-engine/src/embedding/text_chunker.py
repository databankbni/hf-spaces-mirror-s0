"""Sentence-boundary text chunker for review embedding."""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

import tiktoken

from src.embedding.config import (
    CHUNK_OVERLAP_TOKENS,
    CHUNK_SIZE_TOKENS,
    MAX_CHUNKS_PER_RECORD,
    validate_chunk_config,
)

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_ENCODER: tiktoken.Encoding | None | bool = None


def _get_encoder() -> tiktoken.Encoding | None:
    global _ENCODER
    if _ENCODER is None:
        try:
            _ENCODER = tiktoken.get_encoding("cl100k_base")
        except Exception as exc:
            logger.warning("tiktoken unavailable (%s); using word-count fallback", exc)
            _ENCODER = False
    return _ENCODER if _ENCODER is not False else None


def compute_parent_id(text: str) -> str:
    """SHA-256 hash linking a chunk back to its parent review record."""
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def _count_tokens(text: str) -> int:
    encoder = _get_encoder()
    if encoder is not None:
        return len(encoder.encode(text))
    return max(len(text.split()), 1)


def _split_sentences(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []

    try:
        import nltk

        try:
            nltk.data.find("tokenizers/punkt")
        except LookupError:
            nltk.download("punkt_tab", quiet=True)
        sentences = nltk.sent_tokenize(stripped)
        if sentences:
            return sentences
    except Exception:
        logger.debug("NLTK sentence tokenization unavailable; using regex fallback")

    parts = _SENTENCE_SPLIT_RE.split(stripped)
    return [part for part in parts if part.strip()] or [stripped]


def _char_fallback_chunks(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Character-based fallback when sentence boundaries cannot be detected."""
    approx_chars = max(chunk_size * 4, 1)
    overlap_chars = max(overlap * 4, 0)
    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len and len(chunks) < MAX_CHUNKS_PER_RECORD:
        end = min(start + approx_chars, text_len)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_len:
            break
        start = max(end - overlap_chars, start + 1)

    return chunks


def _pack_sentences_into_chunks(
    sentences: list[str],
    chunk_size: int,
    overlap: int,
) -> list[str]:
    if not sentences:
        return []

    total_tokens = _count_tokens(" ".join(sentences))
    if total_tokens <= chunk_size:
        return [" ".join(sentences)]

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for sentence in sentences:
        sentence_tokens = _count_tokens(sentence)

        if sentence_tokens > chunk_size:
            if current:
                chunks.append(" ".join(current))
                current = []
                current_tokens = 0
            if len(chunks) >= MAX_CHUNKS_PER_RECORD:
                break
            chunks.append(sentence[: chunk_size * 4])
            continue

        if current and current_tokens + sentence_tokens > chunk_size:
            chunks.append(" ".join(current))
            if len(chunks) >= MAX_CHUNKS_PER_RECORD:
                break

            overlap_sentences: list[str] = []
            overlap_tokens = 0
            for prev in reversed(current):
                prev_tokens = _count_tokens(prev)
                if overlap_tokens + prev_tokens > overlap:
                    break
                overlap_sentences.insert(0, prev)
                overlap_tokens += prev_tokens

            current = overlap_sentences
            current_tokens = overlap_tokens

        current.append(sentence)
        current_tokens += sentence_tokens

    if current and len(chunks) < MAX_CHUNKS_PER_RECORD:
        chunks.append(" ".join(current))

    return chunks[:MAX_CHUNKS_PER_RECORD]


class TextChunker:
    """Split review records into token-bounded chunks with sentence-aware boundaries."""

    def __init__(
        self,
        chunk_size: int = CHUNK_SIZE_TOKENS,
        overlap: int = CHUNK_OVERLAP_TOKENS,
        max_chunks: int = MAX_CHUNKS_PER_RECORD,
    ) -> None:
        validate_chunk_config(chunk_size, overlap)
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.max_chunks = max_chunks

    def chunk_record(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        text = (record.get("text") or "").strip()
        if not text:
            return []

        parent_id = compute_parent_id(text)
        sentences = _split_sentences(text)

        if len(sentences) <= 1 and _count_tokens(text) > self.chunk_size:
            raw_chunks = _char_fallback_chunks(text, self.chunk_size, self.overlap)
        else:
            raw_chunks = _pack_sentences_into_chunks(sentences, self.chunk_size, self.overlap)
            if not raw_chunks:
                raw_chunks = _char_fallback_chunks(text, self.chunk_size, self.overlap)

        raw_chunks = raw_chunks[: self.max_chunks]
        chunk_total = len(raw_chunks)
        chunked_records: list[dict[str, Any]] = []

        for index, chunk_text in enumerate(raw_chunks):
            chunk_record = {
                **record,
                "text": chunk_text,
                "parent_id": parent_id,
                "chunk_index": index,
                "chunk_total": chunk_total,
                "chunk_id": f"{parent_id}_{index}",
            }
            chunked_records.append(chunk_record)

        return chunked_records

    def chunk(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        all_chunks: list[dict[str, Any]] = []
        for record in records:
            all_chunks.extend(self.chunk_record(record))
        return all_chunks
