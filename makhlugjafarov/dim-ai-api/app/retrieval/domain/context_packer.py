from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.retrieval.domain.models import RetrievedChunk

# GRO-156: the TOC curriculum tree's breadcrumb (clean, named, real hierarchy) is
# preferred; the older section-network path is the fallback for chunks ingested
# before the curriculum tree existed (it degrades, never breaks).
_CURRICULUM_PATH_TITLES_KEY = "curriculum_path_titles"
_SECTION_PATH_TITLES_KEY = "section_path_titles"
_MAX_BREADCRUMB_CHARS = 240

# GRO-217 (S2) — observable, non-destructive packing.
#
# The v1 packer stopped at the first chunk that overflowed the budget (`break`),
# silently discarding that chunk *and every chunk behind it* — including smaller
# ones that would have fit and, in the measured Newton case, the only chunk in the
# top-k slice that stated the third law. v2 removes every silent outcome: within
# the top-k slice a chunk is either packed whole, tail-trimmed at a sentence
# boundary (with an explicit marker), or dropped — and any trim/drop/dedupe is
# surfaced on the returned `PackedContext` so the caller and traces can see it.
#
# `_MIN_TRIM_CONTENT_CHARS`: a chunk that does not fit whole is tail-trimmed only
# when at least this many of its leading content characters survive. Below the
# floor the surviving fragment is too small to carry a coherent idea, so the chunk
# is dropped *with a signal* instead of packing a stub. Chosen for signal quality;
# the hard budget itself (`max_chars`) is re-derived in S6, not here.
_MIN_TRIM_CONTENT_CHARS = 500
_TRUNCATION_MARKER = " […mətn kontekst büdcəsinə görə kəsildi]"

# Sentence terminators (Latin + common quote/bracket closers) followed by
# whitespace — the boundary a tail-trim snaps back to so it never cuts mid-clause.
_SENTENCE_BOUNDARY = re.compile(r"[.!?…][\"'»)\]]?\s")


@dataclass(frozen=True)
class PackedContext:
    """The context actually assembled for the model, plus what packing did to it.

    `chunks` are the top-k chunks that contributed content (whole or tail-trimmed),
    in rank order. The observability fields make every non-whole outcome explicit:
    `truncated_chunk_ids` were tail-trimmed, `dropped_chunk_ids` did not fit at all,
    `duplicate_chunk_ids` were removed before packing. `truncated` is the roll-up
    "something in the top-k slice did not reach the model intact" flag.
    """

    text: str
    chunks: list[RetrievedChunk]
    truncated: bool = False
    truncated_chunk_ids: tuple[str, ...] = ()
    dropped_chunk_ids: tuple[str, ...] = ()
    duplicate_chunk_ids: tuple[str, ...] = field(default_factory=tuple)


def _pack_context(chunks: list[RetrievedChunk], *, max_chars: int) -> PackedContext:
    deduped, duplicate_ids = _dedupe(chunks)

    selected: list[RetrievedChunk] = []
    parts: list[str] = []
    used_chars = 0
    truncated_ids: list[str] = []
    dropped_ids: list[str] = []

    for chunk in deduped:
        header = _chunk_header(chunk, index=len(parts) + 1)
        content = chunk.content.strip()
        separator = 2 if parts else 0  # the "\n\n" that joins parts
        # header + "\n" + content is the rendered part; +separator joins it on.
        whole_size = separator + len(header) + 1 + len(content)

        if used_chars + whole_size <= max_chars:
            parts.append(f"{header}\n{content}")
            selected.append(chunk)
            used_chars += whole_size
            continue

        # Does not fit whole → tail-trim to whatever content room remains, but only
        # if a meaningful fragment survives; otherwise drop it (never silently).
        content_room = max_chars - used_chars - separator - len(header) - 1 - len(_TRUNCATION_MARKER)
        if content_room >= _MIN_TRIM_CONTENT_CHARS:
            trimmed = _sentence_trim(content, content_room)
            rendered = f"{header}\n{trimmed}{_TRUNCATION_MARKER}"
            parts.append(rendered)
            selected.append(chunk)
            used_chars += separator + len(header) + 1 + len(trimmed) + len(_TRUNCATION_MARKER)
            truncated_ids.append(chunk.chunk_id)
            continue

        dropped_ids.append(chunk.chunk_id)

    return PackedContext(
        text="\n\n".join(parts),
        chunks=selected,
        truncated=bool(truncated_ids or dropped_ids),
        truncated_chunk_ids=tuple(truncated_ids),
        dropped_chunk_ids=tuple(dropped_ids),
        duplicate_chunk_ids=tuple(duplicate_ids),
    )


def _dedupe(
    chunks: list[RetrievedChunk],
) -> tuple[list[RetrievedChunk], list[str]]:
    """Drop repeat chunk_ids and near-identical content before packing, preserving
    rank order. Near-identical = same whitespace/case-folded content fingerprint,
    which collapses the same passage re-surfaced under a different chunk_id."""
    seen_ids: set[str] = set()
    seen_fingerprints: set[str] = set()
    kept: list[RetrievedChunk] = []
    duplicates: list[str] = []

    for chunk in chunks:
        fingerprint = _content_fingerprint(chunk.content)
        if chunk.chunk_id in seen_ids or fingerprint in seen_fingerprints:
            duplicates.append(chunk.chunk_id)
            continue
        seen_ids.add(chunk.chunk_id)
        seen_fingerprints.add(fingerprint)
        kept.append(chunk)

    return kept, duplicates


def _content_fingerprint(content: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", content).split()).casefold()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _sentence_trim(content: str, max_len: int) -> str:
    """Longest prefix of `content` no longer than `max_len`, snapped back to the
    last sentence boundary when one sits far enough in to stay meaningful; else to
    the last word boundary; else a hard cut. Never returns more than `max_len`."""
    if len(content) <= max_len:
        return content

    window = content[:max_len]
    boundaries = list(_SENTENCE_BOUNDARY.finditer(window))
    if boundaries and boundaries[-1].end() >= _MIN_TRIM_CONTENT_CHARS:
        return window[: boundaries[-1].end()].rstrip()

    last_space = window.rfind(" ")
    if last_space >= _MIN_TRIM_CONTENT_CHARS:
        return window[:last_space].rstrip()

    return window.rstrip()


def _chunk_header(chunk: RetrievedChunk, *, index: int) -> str:
    """The citation label line plus optional section breadcrumb — everything in a
    packed part except the content body."""
    citation = chunk.citation
    if citation.page_start == citation.page_end:
        label = f"[{index}] {citation.citation_label}, səh. {citation.page_start}"
    else:
        label = (
            f"[{index}] {citation.citation_label}, "
            f"səh. {citation.page_start}-{citation.page_end}"
        )

    lines = [label]
    breadcrumb = _section_breadcrumb(chunk)
    if breadcrumb:
        lines.append(f"Bölmə: {breadcrumb}")
    return "\n".join(lines)


def _section_breadcrumb(chunk: RetrievedChunk) -> str | None:
    raw_titles = chunk.metadata.get(_CURRICULUM_PATH_TITLES_KEY)
    if not isinstance(raw_titles, list):
        raw_titles = chunk.metadata.get(_SECTION_PATH_TITLES_KEY)
    if not isinstance(raw_titles, list):
        return None

    titles: list[str] = []
    for raw_title in raw_titles:
        if not isinstance(raw_title, str):
            continue
        title = raw_title.strip()
        if not title or (titles and titles[-1] == title):
            continue
        titles.append(title)

    if not titles:
        return None

    breadcrumb = " > ".join(titles)
    if len(breadcrumb) <= _MAX_BREADCRUMB_CHARS:
        return breadcrumb
    return breadcrumb[: _MAX_BREADCRUMB_CHARS - 3].rstrip() + "..."
