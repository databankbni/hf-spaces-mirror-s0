"""Shared chunk-row plumbing for the retrieval channels (GRO-218 / S3a).

The dense (`postgres_retriever`) and lexical (`postgres_lexical`) channels select
the same chunk/document/section columns and build the same `RetrievedChunk`; the
only per-channel difference is the score expression and the ranking clause. This
module owns the parts they share — the document-status filter, the optional
subject/grade/language filters, the common `SELECT` column list, and the row →
`RetrievedChunk` mapping — so the two channels return byte-identical chunk objects
for the same row and neither drifts from the other.
"""

from __future__ import annotations

from app.platform.text_quality import sanitize_section_title
from app.retrieval.domain.models import Citation, RetrievalFilters, RetrievedChunk

# Applied by every channel: only ready, legally-ingestible, non-quarantined chunks.
DOC_STATUS_CLAUSES = (
    "d.status = 'ready'",
    "d.legal_status != 'do_not_ingest'",
    "coalesce((c.metadata->>'quarantined')::boolean, false) = false",
)

# The chunk/document/section columns both channels read. `chunk_from_row` depends
# on exactly these names; a channel's SELECT must project them (plus its score).
CHUNK_COLUMNS_SQL = """
              c.id            as chunk_id,
              c.content,
              c.page_start,
              c.page_end,
              c.subject,
              c.grade,
              c.language,
              c.metadata,
              c.curriculum_node_id,
              d.id            as document_id,
              d.source_id,
              d.title,
              d.citation_label,
              d.source_tier,
              sb.id           as section_block_id,
              sb.section_title,
              sb.page_start   as section_page_start,
              sb.page_end     as section_page_end
"""


def subject_filter_clauses(filters: RetrievalFilters) -> tuple[list[str], list[object]]:
    """Optional subject/grade/language predicates + their bind params, in order."""
    clauses: list[str] = []
    params: list[object] = []
    if filters.subject:
        clauses.append("c.subject = %s")
        params.append(filters.subject)
    if filters.grade is not None:
        clauses.append("c.grade = %s")
        params.append(filters.grade)
    if filters.language:
        clauses.append("c.language = %s")
        params.append(filters.language)
    return clauses, params


def chunk_from_row(row: dict, *, score: float) -> RetrievedChunk:
    """Build a `RetrievedChunk` from a row projecting `CHUNK_COLUMNS_SQL`.

    The score is passed in because each channel computes it differently (dense
    cosine similarity vs a lexical rank); everything else is identical.
    """
    node_id = row.get("curriculum_node_id")
    return RetrievedChunk(
        chunk_id=str(row["chunk_id"]),
        content=row["content"],
        score=float(score),
        subject=row["subject"],
        grade=row["grade"],
        language=row["language"],
        metadata=row["metadata"] or {},
        curriculum_node_id=str(node_id) if node_id else None,
        citation=Citation(
            document_id=str(row["document_id"]),
            source_id=row["source_id"],
            title=row["title"],
            # Use the parent section's page span when present — the true start/end
            # of the section, not just the chunk fragment's page.
            page_start=row["section_page_start"] if row["section_page_start"] is not None else row["page_start"],
            page_end=row["section_page_end"] if row["section_page_end"] is not None else row["page_end"],
            citation_label=row["citation_label"],
            source_tier=int(row["source_tier"]),
            section_block_id=str(row["section_block_id"]) if row["section_block_id"] else None,
            # OCR heading detection stores garble for many sections; a junk title
            # becomes None so the citation degrades to its page span.
            section_title=sanitize_section_title(row["section_title"]),
        ),
    )
