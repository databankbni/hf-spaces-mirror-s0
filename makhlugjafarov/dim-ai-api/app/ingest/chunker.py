from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256

from app.ingest.models import Chunk, ManifestSource, ParsedPage


DEFAULT_MAX_CHARS = 1800
DEFAULT_OVERLAP_CHARS = 200


@dataclass(frozen=True)
class ChunkingResult:
    chunks: list[Chunk]
    duplicate_chunks_skipped: int


def chunk_pages(
    source: ManifestSource,
    pages: Iterable[ParsedPage],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[Chunk]:
    return chunk_pages_with_stats(
        source,
        pages,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
    ).chunks


def chunk_pages_with_stats(
    source: ManifestSource,
    pages: Iterable[ParsedPage],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> ChunkingResult:
    chunks: list[Chunk] = []
    seen_hashes: set[str] = set()
    duplicate_chunks_skipped = 0

    for page in pages:
        # Map the PDF page index to the page number printed on the page — that is
        # what a student flips to, so it is what we cite. Front matter (printed < 1)
        # is cover/anthem/contents, not exam content: skip it.
        printed_page = page.page_number - source.page_offset
        if printed_page < 1:
            continue

        for piece in _split_text(page.text, max_chars=max_chars, overlap_chars=overlap_chars):
            content = piece.strip()
            if not content:
                continue

            content_hash = build_content_hash(source.source_id, content)
            if content_hash in seen_hashes:
                duplicate_chunks_skipped += 1
                continue

            seen_hashes.add(content_hash)
            chunks.append(
                Chunk(
                    source_id=source.source_id,
                    chunk_index=len(chunks),
                    page_start=printed_page,
                    page_end=printed_page,
                    content=content,
                    content_hash=content_hash,
                    subject=source.subject,
                    grade=source.grade,
                    language=source.language,
                    source_category=source.source_category,
                    metadata={"parser_page_number": page.page_number, "printed_page": printed_page},
                )
            )

    return ChunkingResult(chunks=chunks, duplicate_chunks_skipped=duplicate_chunks_skipped)


def build_content_hash(source_id: str, content: str) -> str:
    normalized = " ".join(content.split())
    return sha256(f"{source_id}:dim-page-section-v1:{normalized}".encode("utf-8")).hexdigest()


def _split_text(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    normalized = "\n\n".join(part.strip() for part in text.split("\n\n") if part.strip())
    if len(normalized) <= max_chars:
        return [normalized] if normalized else []

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + max_chars, len(normalized))
        if end < len(normalized):
            paragraph_break = normalized.rfind("\n\n", start, end)
            if paragraph_break > start + max_chars // 2:
                end = paragraph_break
        chunks.append(normalized[start:end].strip())
        if end >= len(normalized):
            break
        start = max(end - overlap_chars, start + 1)
    return chunks
