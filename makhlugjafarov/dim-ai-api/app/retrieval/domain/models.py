from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.retrieval.domain.context_packer import PackedContext

ChatMode = Literal["subject_tutor", "dim_coach"]

class RetrievalError(RuntimeError):
    """Raised when retrieval cannot safely run."""

@dataclass(frozen=True)
class RetrievalFilters:
    subject: str | None = None
    grade: int | None = None
    language: str | None = None

    @property
    def has_filters(self) -> bool:
        return bool(self.subject or self.grade is not None or self.language)

@dataclass(frozen=True)
class Citation:
    document_id: str
    source_id: str
    title: str
    page_start: int
    page_end: int
    citation_label: str
    source_tier: int = 3
    # Section fields — populated when the chunk belongs to a section_block.
    # Nullable so orphan chunks (section_block_id IS NULL) degrade to page citation.
    section_block_id: str | None = None
    section_title: str | None = None

@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    content: str
    score: float
    subject: str
    grade: int | None
    language: str
    citation: Citation
    metadata: dict[str, object] = field(default_factory=dict)
    # Nullable FK to curriculum_nodes — populated when the chunk was tagged at
    # ingestion (GRO-224 / S5a). None means structural augmentation must skip or
    # fall back to title matching; the live corpus is ~92 % tagged (literature ~59 %).
    curriculum_node_id: str | None = None

@dataclass(frozen=True)
class RetrievalResult:
    query: str
    chunks: list[RetrievedChunk]
    weak_context: bool
    filters: RetrievalFilters
    filters_relaxed: bool = False
    tier_conflict: bool = False
    candidates: list[RetrievedChunk] = field(default_factory=list)
    query_embedding_model_id: str = ""
    # The single packed context produced during retrieval (GRO-217/S2). Optional so
    # results assembled in tests without going through packing stay valid; the live
    # path always sets it, which is what lets the query layer drop its second pack.
    packed: PackedContext | None = None

    @property
    def citations(self) -> list[Citation]:
        seen: set[tuple] = set()
        citations: list[Citation] = []
        for chunk in self.chunks:
            c = chunk.citation
            # Deduplicate by section when present; otherwise by page span.
            # This collapses multiple chunks from the same section into one citation.
            key: tuple = (
                (c.document_id, c.section_block_id)
                if c.section_block_id
                else (c.document_id, c.page_start, c.page_end)
            )
            if key in seen:
                continue
            seen.add(key)
            citations.append(c)
        return citations
