"""Tests for Phase 3 text chunker."""

import pytest

from src.embedding.config import ConfigError
from src.embedding.text_chunker import TextChunker, compute_parent_id


def _make_record(text: str) -> dict:
    return {
        "source": "play_store",
        "text": text,
        "rating": 4,
        "date": "2026-06-20T10:00:00Z",
        "url": "https://example.com",
        "thread_or_context": None,
        "lang": "en",
        "relevant": True,
        "relevance_status": "classified",
    }


def test_short_text_single_chunk():
    chunker = TextChunker()
    record = _make_record("Spotify recommendations feel repetitive lately.")
    chunks = chunker.chunk_record(record)

    assert len(chunks) == 1
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["chunk_total"] == 1
    assert chunks[0]["text"] == record["text"]
    assert chunks[0]["parent_id"] == compute_parent_id(record["text"])


def test_parent_id_is_stable():
    text = "Discover Weekly keeps repeating the same artists."
    assert compute_parent_id(text) == compute_parent_id(f"  {text.upper()}  ")


def test_overlap_must_be_less_than_chunk_size():
    with pytest.raises(ConfigError):
        TextChunker(chunk_size=100, overlap=100)


def test_long_text_produces_multiple_chunks_with_metadata():
    sentence = "Discover Weekly keeps playing the same songs every week. "
    long_text = sentence * 200
    chunker = TextChunker(chunk_size=64, overlap=8, max_chunks=20)
    chunks = chunker.chunk_record(_make_record(long_text))

    assert 1 < len(chunks) <= 20
    assert chunks[0]["chunk_total"] == len(chunks)
    assert {chunk["parent_id"] for chunk in chunks} == {chunks[0]["parent_id"]}
    assert [chunk["chunk_index"] for chunk in chunks] == list(range(len(chunks)))


def test_no_punctuation_uses_fallback_without_error():
    chunker = TextChunker(chunk_size=32, overlap=4)
    record = _make_record("word " * 500)
    chunks = chunker.chunk_record(record)
    assert len(chunks) >= 1
