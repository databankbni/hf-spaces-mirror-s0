from collections.abc import Iterable
from dataclasses import dataclass, field
from hashlib import sha256

from app.ingestion.domain.curriculum import (
    CURRICULUM_NODE_PATH_KEY,
    CURRICULUM_PATH_TITLES_KEY,
    extract_curriculum_nodes,
    node_title_path,
    resolve_node_for_page,
)
from app.ingestion.domain.models import (
    Block,
    Chunk,
    CurriculumNode,
    ManifestSource,
    ParsedDocument,
    ParsedPage,
    SectionBlock,
)
from app.ingestion.domain.section_network import (
    LOGICAL_SECTION_ID_KEY,
    NETWORK_DEPTH_KEY,
    PARENT_SECTION_ID_KEY,
    SECTION_LEVEL_KEY,
    SECTION_PATH_IDS_KEY,
    SECTION_PATH_TITLES_KEY,
    annotate_section_network,
)


DEFAULT_MAX_CHARS = 1800
DEFAULT_OVERLAP_CHARS = 200
DEFAULT_MAX_SECTION_PAGES = 6
DEFAULT_MAX_SECTION_CHARS = DEFAULT_MAX_CHARS * 6


@dataclass(frozen=True)
class _SectionSlice:
    blocks: list[Block]
    floor_index: int
    floor_total: int


@dataclass(frozen=True)
class _BlockTextSpan:
    start: int
    end: int
    page: int


@dataclass(frozen=True)
class _TextPiece:
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class ChunkingResult:
    chunks: list[Chunk]
    duplicate_chunks_skipped: int
    sections: list[SectionBlock] = field(default_factory=list)
    # Segmentation v4 (GRO-156): the book's TOC-derived curriculum tree, and the
    # sections/chunks above carry ``curriculum_node_path`` in metadata linking
    # them to it. Empty when the TOC did not parse (flat-section degradation).
    curriculum_nodes: list[CurriculumNode] = field(default_factory=list)
    # Segmentation v3 (GRO-145) diagnostics: how many section boundaries the
    # book's own TOC declared, and what share of them a detected heading also
    # landed on. ``None`` agreement means the book had no parseable TOC (the cut
    # set came from headings alone). Readiness v2 WARNs on low agreement.
    toc_anchor_count: int = 0
    toc_detected_agreement: float | None = None


class _DocumentSegmenter:
    """Stateful segmenter to break documents into sections and chunks."""
    
    def __init__(
        self,
        source: ManifestSource,
        max_chars: int,
        overlap_chars: int,
        max_section_pages: int,
        max_section_chars: int,
        never_split_types: set[str],
    ):
        self.source = source
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars
        self.max_section_pages = max_section_pages
        self.max_section_chars = max_section_chars
        self.never_split_types = never_split_types

        self.chunks: list[Chunk] = []
        self.sections: list[SectionBlock] = []
        self.seen_hashes: set[str] = set()
        self.duplicate_chunks_skipped = 0

    def finalize_section(
        self,
        blocks: list[Block],
        title: str | None,
        *,
        level: int | None = None,
        source_signal: str = "orphan",
    ) -> None:
        if not blocks:
            return

        # Filter blocks by front matter / page offset
        valid_blocks = []
        for b in blocks:
            printed = b.page - self.source.page_offset
            if printed >= 1:
                valid_blocks.append(b)

        if not valid_blocks:
            return

        logical_section_id = _logical_section_id(self.source.source_id, valid_blocks, title)
        for section_slice in self._subdivide_section(valid_blocks):
            metadata: dict[str, object] = {
                LOGICAL_SECTION_ID_KEY: logical_section_id,
                SECTION_LEVEL_KEY: _normalize_section_level(level),
                "section_source": source_signal,
            }
            if section_slice.floor_total > 1:
                metadata.update({
                    "segmentation_floor": True,
                    "floor_index": section_slice.floor_index,
                    "floor_total": section_slice.floor_total,
                    "max_section_pages": self.max_section_pages,
                    "max_section_chars": self.max_section_chars,
                    "synthetic_continuation": section_slice.floor_index > 1,
                })
                if title:
                    metadata["source_title"] = title
            self._append_section(section_slice.blocks, title, metadata)

    def _subdivide_section(self, valid_blocks: list[Block]) -> list[_SectionSlice]:
        slices: list[list[Block]] = []
        current: list[Block] = []
        current_start_printed_page: int | None = None
        current_chars = 0

        for block in valid_blocks:
            text_len = len(block.text.strip())
            printed_page = block.page - self.source.page_offset

            if current_start_printed_page is None:
                current_start_printed_page = printed_page

            prospective_pages = printed_page - current_start_printed_page + 1
            prospective_chars = current_chars + (2 if current_chars and text_len else 0) + text_len
            exceeds_pages = (
                self.max_section_pages > 0
                and prospective_pages > self.max_section_pages
            )
            exceeds_chars = (
                self.max_section_chars > 0
                and current_chars > 0
                and prospective_chars > self.max_section_chars
            )

            if current and (exceeds_pages or exceeds_chars):
                slices.append(current)
                current = [block]
                current_start_printed_page = printed_page
                current_chars = text_len
                continue

            current.append(block)
            current_chars = prospective_chars

        if current:
            slices.append(current)

        floor_total = len(slices)
        return [
            _SectionSlice(blocks=section_blocks, floor_index=index, floor_total=floor_total)
            for index, section_blocks in enumerate(slices, start=1)
        ]

    def _append_section(
        self,
        valid_blocks: list[Block],
        title: str | None,
        metadata: dict[str, object],
    ) -> None:
        page_start = min(b.page for b in valid_blocks) - self.source.page_offset
        page_end = max(b.page for b in valid_blocks) - self.source.page_offset

        # Join block texts for the overall section content
        content = "\n\n".join(b.text.strip() for b in valid_blocks if b.text.strip())
        if not content:
            return

        content_hash = build_content_hash(self.source.source_id, content)
        section_id = f"sec-{sha256((self.source.source_id + content).encode('utf-8')).hexdigest()[:16]}"

        # Write-time title gating (GRO-145): never store OCR garble as a title.
        # ``sanitize_section_title`` returns the cleaned title or None — a NULL
        # title degrades to a page-span citation downstream. This is the single
        # chokepoint, so chunk metadata (which reads ``section.section_title``)
        # inherits the gated value too. GRO-140's display-time sanitization
        # stays as defense-in-depth.
        from app.platform.text_quality import sanitize_section_title

        section = SectionBlock(
            id=section_id,
            document_id=self.source.source_id,
            ordinal=len(self.sections) + 1,
            section_title=sanitize_section_title(title),
            page_start=page_start,
            page_end=page_end,
            content=content,
            content_hash=content_hash,
            extraction_method="segment_document",
            metadata=metadata,
        )
        self.sections.append(section)

        # Now chunk within the section
        self._chunk_section(section, valid_blocks)

    def _chunk_section(self, section: SectionBlock, blocks: list[Block]) -> None:
        current_text_blocks: list[Block] = []
        
        for b in blocks:
            if b.type in self.never_split_types:
                # Flush accumulated text blocks first
                self._flush_text_blocks(current_text_blocks, section)
                current_text_blocks = []
                
                # Flush this block as an isolated chunk
                self._flush_isolated_block(b, section)
            else:
                current_text_blocks.append(b)
                
        # Flush any remaining text blocks
        self._flush_text_blocks(current_text_blocks, section)

    def _flush_text_blocks(self, text_blocks: list[Block], section: SectionBlock) -> None:
        if not text_blocks:
            return

        chunk_content, text_spans = _join_text_blocks_with_spans(text_blocks)
        if not chunk_content:
            return
            
        fallback_page_start = min(b.page for b in text_blocks) - self.source.page_offset
        fallback_page_end = max(b.page for b in text_blocks) - self.source.page_offset

        for piece in _split_text_with_offsets(
            chunk_content,
            max_chars=self.max_chars,
            overlap_chars=self.overlap_chars,
        ):
            piece_content = piece.text.strip()
            if not piece_content:
                continue

            chunk_page_start, chunk_page_end, used_fallback = _page_span_for_piece(
                piece,
                text_spans,
                page_offset=self.source.page_offset,
                fallback=(fallback_page_start, fallback_page_end),
            )

            chunk_hash = build_content_hash(self.source.source_id, piece_content)
            if chunk_hash in self.seen_hashes:
                self.duplicate_chunks_skipped += 1
                continue

            self.seen_hashes.add(chunk_hash)
            metadata = _chunk_network_metadata(section)
            if section.section_title:
                metadata["section_title"] = section.section_title
            if used_fallback:
                metadata["page_span_fallback"] = True
                
            self.chunks.append(
                Chunk(
                    source_id=self.source.source_id,
                    chunk_index=len(self.chunks),
                    page_start=chunk_page_start,
                    page_end=chunk_page_end,
                    content=piece_content,
                    content_hash=chunk_hash,
                    subject=self.source.subject,
                    grade=self.source.grade,
                    language=self.source.language,
                    source_category=self.source.source_category,
                    section_block_id=section.id,
                    metadata=metadata,
                )
            )

    def _flush_isolated_block(self, b: Block, section: SectionBlock) -> None:
        isolated_content = b.text.strip()
        if not isolated_content:
            return
            
        chunk_hash = build_content_hash(self.source.source_id, isolated_content)
        if chunk_hash in self.seen_hashes:
            self.duplicate_chunks_skipped += 1
            return
            
        self.seen_hashes.add(chunk_hash)
        
        metadata = {"isolated_block": True, "block_type": b.type, **_chunk_network_metadata(section)}
        if section.section_title:
            metadata["section_title"] = section.section_title
            
        self.chunks.append(
            Chunk(
                source_id=self.source.source_id,
                chunk_index=len(self.chunks),
                page_start=b.page - self.source.page_offset,
                page_end=b.page - self.source.page_offset,
                content=isolated_content,
                content_hash=chunk_hash,
                subject=self.source.subject,
                grade=self.source.grade,
                language=self.source.language,
                source_category=self.source.source_category,
                section_block_id=section.id,
                metadata=metadata,
            )
        )


def segment_document_with_stats(
    document: ParsedDocument,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    max_section_pages: int = DEFAULT_MAX_SECTION_PAGES,
    max_section_chars: int = DEFAULT_MAX_SECTION_CHARS,
    never_split_types: set[str] | None = None,
) -> ChunkingResult:
    """Segment a parsed document into sections and chunks."""
    source = document.source
    if never_split_types is None:
        never_split_types = set()
    
    # Fallback for documents that have no blocks (e.g. plain text, or OCR pipeline lacking layout).
    if not document.blocks and document.pages:
        return chunk_pages_with_stats(
            source,
            document.pages,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )

    segmenter = _DocumentSegmenter(
        source=source,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
        max_section_pages=max_section_pages,
        max_section_chars=max_section_chars,
        never_split_types=never_split_types,
    )

    # Segmentation v3 (GRO-145): the book's TOC declares authoritative section
    # boundaries (printed-page coordinates, same space as ``block.page -
    # page_offset``). We cut a new section on a detected heading OR a TOC anchor
    # (union of cuts); when both coincide, the cleaner TOC title wins — headings
    # refine within anchors, never override them. No parseable TOC ⇒ anchors is
    # empty and behaviour falls back to the original heading-only split.
    from app.ingestion.domain.toc_anchor import extract_toc_anchors

    anchors = extract_toc_anchors(document)
    anchor_idx = 0
    toc_cut_pages: set[int] = set()
    heading_cut_pages: set[int] = set()

    current_section_blocks: list[Block] = []
    current_section_title: str | None = None
    current_section_level: int | None = None
    current_section_signal = "orphan"

    sorted_blocks = sorted(document.blocks, key=lambda b: (b.page, b.reading_order))

    for block in sorted_blocks:
        printed_page = block.page - source.page_offset

        # Fire every TOC anchor whose printed page we have now reached. Anchors
        # for pages with no extracted blocks collapse onto the next block.
        toc_fired = False
        toc_raw_title: str | None = None
        toc_level: int | None = None
        while anchor_idx < len(anchors) and anchors[anchor_idx].printed_page <= printed_page:
            toc_fired = True
            toc_raw_title = anchors[anchor_idx].raw_title
            toc_level = anchors[anchor_idx].level
            anchor_idx += 1

        is_heading = block.type == "heading"
        if is_heading:
            heading_cut_pages.add(printed_page)
        if toc_fired:
            toc_cut_pages.add(printed_page)

        if is_heading or toc_fired:
            segmenter.finalize_section(
                current_section_blocks,
                current_section_title,
                level=current_section_level,
                source_signal=current_section_signal,
            )
            current_section_blocks = [block]
            current_section_title = _choose_section_title(toc_raw_title, block if is_heading else None)
            current_section_level = _choose_section_level(toc_level, block if is_heading else None)
            current_section_signal = _section_signal(toc_fired, is_heading)
        else:
            current_section_blocks.append(block)

    segmenter.finalize_section(
        current_section_blocks,
        current_section_title,
        level=current_section_level,
        source_signal=current_section_signal,
    )
    annotate_section_network(segmenter.sections)
    _propagate_section_network_to_chunks(segmenter.chunks, segmenter.sections)

    # Segmentation v4 (GRO-156): link sections/chunks to the TOC curriculum tree.
    curriculum_nodes = extract_curriculum_nodes(document)
    if curriculum_nodes:
        _attach_curriculum_nodes(segmenter.sections, segmenter.chunks, curriculum_nodes)

    agreement: float | None = None
    if toc_cut_pages:
        agreement = len(toc_cut_pages & heading_cut_pages) / len(toc_cut_pages)

    return ChunkingResult(
        chunks=segmenter.chunks,
        duplicate_chunks_skipped=segmenter.duplicate_chunks_skipped,
        sections=segmenter.sections,
        curriculum_nodes=curriculum_nodes,
        toc_anchor_count=len(anchors),
        toc_detected_agreement=agreement,
    )


def _attach_curriculum_nodes(
    sections: list[SectionBlock],
    chunks: list[Chunk],
    nodes: list[CurriculumNode],
) -> None:
    """Tag each section with its deepest containing node; chunks inherit it.

    A section maps to the most specific topic covering its first page. Its chunks
    take the *same* node (a chunk belongs to its section's topic), so section and
    chunk citations stay consistent. The node path (for the FK) and its breadcrumb
    (root → leaf titles, for the retrieval citation) are both materialised here.
    Purely additive: no content changes, and a section over a page no node covers
    simply carries no tag.
    """
    section_tags: dict[str | None, tuple[str, list[str]]] = {}
    for section in sections:
        node = resolve_node_for_page(nodes, section.page_start)
        if node is not None:
            titles = node_title_path(nodes, node)
            section.metadata[CURRICULUM_NODE_PATH_KEY] = node.node_path
            section.metadata[CURRICULUM_PATH_TITLES_KEY] = titles
            section_tags[section.id] = (node.node_path, titles)
    for chunk in chunks:
        tag = section_tags.get(chunk.section_block_id)
        if tag is not None:
            node_path, titles = tag
            chunk.metadata[CURRICULUM_NODE_PATH_KEY] = node_path
            chunk.metadata[CURRICULUM_PATH_TITLES_KEY] = titles


def _choose_section_title(toc_raw_title: str | None, heading_block: Block | None) -> str | None:
    """Pick the raw title for a section cut; ``finalize_section`` gates it.

    TOC titles win when readable (they are short and consistent, so they survive
    sanitization more often than body headings). If the TOC title is garble but
    a detected heading coincides, fall back to the heading text — that maximises
    title keep-rate without letting the heading override the TOC's *cut*.
    """
    from app.platform.text_quality import sanitize_section_title

    if toc_raw_title is not None:
        if sanitize_section_title(toc_raw_title) is not None:
            return toc_raw_title
        if heading_block is not None:
            return heading_block.text.strip()
        return toc_raw_title  # sanitizes to None → page-span citation
    return heading_block.text.strip() if heading_block is not None else None


def _choose_section_level(toc_level: int | None, heading_block: Block | None) -> int:
    if toc_level is not None:
        return _normalize_section_level(toc_level)
    if heading_block is None:
        return 1
    return _normalize_section_level(heading_block.level)


def _normalize_section_level(level: int | None) -> int:
    if level is None:
        return 1
    return max(1, min(level, 6))


def _section_signal(toc_fired: bool, is_heading: bool) -> str:
    if toc_fired and is_heading:
        return "toc+heading"
    if toc_fired:
        return "toc"
    if is_heading:
        return "heading"
    return "orphan"


def _logical_section_id(source_id: str, valid_blocks: list[Block], title: str | None) -> str:
    first = valid_blocks[0]
    seed = f"{source_id}:{title or ''}:{first.page}:{first.reading_order}:{len(valid_blocks)}"
    return f"logical-{sha256(seed.encode('utf-8')).hexdigest()[:16]}"


def _chunk_network_metadata(section: SectionBlock) -> dict[str, object]:
    metadata: dict[str, object] = {}
    for key in (
        SECTION_LEVEL_KEY,
        PARENT_SECTION_ID_KEY,
        SECTION_PATH_IDS_KEY,
        SECTION_PATH_TITLES_KEY,
        NETWORK_DEPTH_KEY,
    ):
        if key in section.metadata:
            metadata[key] = section.metadata[key]
    return metadata


def _propagate_section_network_to_chunks(chunks: list[Chunk], sections: list[SectionBlock]) -> None:
    sections_by_id = {section.id: section for section in sections if section.id}
    for chunk in chunks:
        if chunk.section_block_id is None:
            continue
        section = sections_by_id.get(chunk.section_block_id)
        if section is None:
            continue
        chunk.metadata.update(_chunk_network_metadata(section))


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


def build_content_hash(source_id: str, content: str) -> str:
    normalized = " ".join(content.split())
    return sha256(f"{source_id}:dim-page-section-v1:{normalized}".encode("utf-8")).hexdigest()


def _join_text_blocks_with_spans(blocks: list[Block]) -> tuple[str, list[_BlockTextSpan]]:
    parts: list[str] = []
    spans: list[_BlockTextSpan] = []
    cursor = 0

    for block in blocks:
        text = block.text.strip()
        if not text:
            continue

        if parts:
            parts.append("\n\n")
            cursor += 2

        start = cursor
        parts.append(text)
        cursor += len(text)
        spans.append(_BlockTextSpan(start=start, end=cursor, page=block.page))

    return "".join(parts), spans


def _page_span_for_piece(
    piece: _TextPiece,
    spans: list[_BlockTextSpan],
    *,
    page_offset: int,
    fallback: tuple[int, int],
) -> tuple[int, int, bool]:
    pages = [
        span.page - page_offset
        for span in spans
        if span.start < piece.end and piece.start < span.end
    ]
    valid_pages = [page for page in pages if page >= 1]
    if not valid_pages:
        return fallback[0], fallback[1], True
    return min(valid_pages), max(valid_pages), False


def _split_text_with_offsets(text: str, *, max_chars: int, overlap_chars: int) -> list[_TextPiece]:
    normalized = "\n\n".join(part.strip() for part in text.split("\n\n") if part.strip())
    if len(normalized) <= max_chars:
        return [_TextPiece(text=normalized, start=0, end=len(normalized))] if normalized else []

    chunks: list[_TextPiece] = []
    start = 0
    while start < len(normalized):
        end = min(start + max_chars, len(normalized))
        if end < len(normalized):
            paragraph_break = normalized.rfind("\n\n", start, end)
            if paragraph_break > start + max_chars // 2:
                end = paragraph_break

        raw_piece = normalized[start:end]
        leading_trim = len(raw_piece) - len(raw_piece.lstrip())
        stripped_piece = raw_piece.strip()
        piece_start = start + leading_trim
        piece_end = piece_start + len(stripped_piece)
        chunks.append(_TextPiece(text=stripped_piece, start=piece_start, end=piece_end))

        if end >= len(normalized):
            break
        start = max(end - overlap_chars, start + 1)
    return chunks


def _split_text(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    return [
        piece.text
        for piece in _split_text_with_offsets(
            text,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )
    ]
