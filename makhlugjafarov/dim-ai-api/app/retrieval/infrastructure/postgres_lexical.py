"""Lexical retrieval channel over the already-deployed Postgres indexes (GRO-218
/ S3a, PRD §3.2). No migration — these assets ship in the initial schema and are
live (2,806/2,806 chunks): `chunks.search_vector` (`to_tsvector('simple', content)`,
generated) with a GIN index, and a `gin_trgm_ops` index on `content`.

Two variants behind one port (`search_lexical`):

* **fts** — full-text search over `search_vector`. The query text is reduced to
  its `'simple'` lexemes and OR-combined, so any shared term makes a chunk a
  candidate; `ts_rank_cd` then orders by matched-term density. OR (not the
  AND-style `websearch_to_tsquery`) is deliberate: this is a *recall* channel and
  RRF supplies precision. Honest limitation carried from the PRD: `'simple'` does
  no Azerbaijani stemming, so agglutinative suffixed forms won't match a root
  token via FTS.
* **trigram** — `word_similarity(query, content)` over the trigram index, the
  fuzzy fallback for misspelled/OCR-mangled rare terms. Measured in S3a to be slow
  (~0.5 s) and low-yield for whole-question inputs (EXPLAIN in the issue), so it is
  **not** wired into the default serving path — kept behind this port for the
  measurement and for later per-term use, never assumed to help.

Both variants return the same `RetrievedChunk` shape as the dense channel (shared
`chunk_rows`), differing only in the score they carry (a lexical rank, not cosine).
"""

from __future__ import annotations

from typing import Literal

from app.retrieval.domain.models import RetrievalFilters, RetrievedChunk
from app.retrieval.infrastructure.chunk_rows import (
    CHUNK_COLUMNS_SQL,
    DOC_STATUS_CLAUSES,
    chunk_from_row,
    subject_filter_clauses,
)

LexicalVariant = Literal["fts", "trigram"]


def search_lexical(
    connection,
    *,
    query: str,
    filters: RetrievalFilters,
    limit: int,
    variant: LexicalVariant = "fts",
) -> list[RetrievedChunk]:
    """Retrieve up to `limit` chunks lexically for `query` under the same filters
    as the dense channel. Returns `[]` for a blank query (nothing to match on)."""
    if not query or not query.strip():
        return []
    if variant == "fts":
        return _search_fts(connection, query=query, filters=filters, limit=limit)
    if variant == "trigram":
        return _search_trigram(connection, query=query, filters=filters, limit=limit)
    raise ValueError(f"unknown lexical variant: {variant!r}")


def _search_fts(
    connection, *, query: str, filters: RetrievalFilters, limit: int
) -> list[RetrievedChunk]:
    subject_clauses, subject_params = subject_filter_clauses(filters)
    where_sql = " and ".join([*DOC_STATUS_CLAUSES, "c.search_vector @@ q.query", *subject_clauses])
    # Params in textual order: the CTE's to_tsvector(query), then the subject
    # filters (q.query is a CTE column, not a bind), then the limit.
    params = [query, *subject_params, limit]

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            with q as (
                select to_tsquery('simple', string_agg(lexeme, ' | ')) as query
                from unnest(to_tsvector('simple', %s)) as t(lexeme)
            )
            select
{CHUNK_COLUMNS_SQL},
              ts_rank_cd(c.search_vector, q.query) as score
            from public.chunks c
            join public.documents d on d.id = c.document_id
            left join public.section_blocks sb on sb.id = c.section_block_id
            cross join q
            where {where_sql}
            order by ts_rank_cd(c.search_vector, q.query) desc, d.source_tier asc
            limit %s
            """,
            params,
        )
        rows = cursor.fetchall()

    return [chunk_from_row(row, score=row["score"]) for row in rows]


def _search_trigram(
    connection, *, query: str, filters: RetrievalFilters, limit: int
) -> list[RetrievedChunk]:
    subject_clauses, subject_params = subject_filter_clauses(filters)
    # `%s <%% c.content`: the trigram word-similarity operator (`<%`), with `%`
    # doubled to survive psycopg parameter substitution.
    where_sql = " and ".join([*DOC_STATUS_CLAUSES, "%s <%% c.content", *subject_clauses])
    params = [query, query, *subject_params, query, limit]

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            select
{CHUNK_COLUMNS_SQL},
              word_similarity(%s, c.content) as score
            from public.chunks c
            join public.documents d on d.id = c.document_id
            left join public.section_blocks sb on sb.id = c.section_block_id
            where {where_sql}
            order by word_similarity(%s, c.content) desc, d.source_tier asc
            limit %s
            """,
            params,
        )
        rows = cursor.fetchall()

    return [chunk_from_row(row, score=row["score"]) for row in rows]
