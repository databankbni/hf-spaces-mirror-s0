from __future__ import annotations
from app.platform.embeddings import TextEmbedder
from app.platform.vectors import _vector_literal
from app.retrieval.domain.models import RetrievalFilters, RetrievedChunk
from app.retrieval.infrastructure.chunk_rows import (
    CHUNK_COLUMNS_SQL,
    DOC_STATUS_CLAUSES,
    chunk_from_row,
    subject_filter_clauses,
)
import re

def _is_math_junk(content: str) -> bool:
    text = re.sub(r'\$\$.*?\$\$', '', content, flags=re.DOTALL)
    text = re.sub(r'\$.*?\$', '', text, flags=re.DOTALL)
    text = re.sub(r'\\\[.*?\\\]', '', text, flags=re.DOTALL)
    text = re.sub(r'\\\(.*?\\\)', '', text, flags=re.DOTALL)
    text = re.sub(r'\\[a-zA-Z]+', '', text)
    words = re.findall(r'\b[^\W\d_]+\b', text)
    words = [w for w in words if len(w) > 1]
    nl_len = sum(len(w) for w in words)
    return nl_len < 50

def _search_chunks(
    connection,
    *,
    query_embedding: list[float],
    embedder: TextEmbedder,
    filters: RetrievalFilters,
    limit: int,
) -> list[RetrievedChunk]:
    clauses = ["ce.embedding_model_id = %s", *DOC_STATUS_CLAUSES]
    params: list[object] = [embedder.spec.id]
    subject_clauses, subject_params = subject_filter_clauses(filters)
    clauses.extend(subject_clauses)
    params.extend(subject_params)

    vector = _vector_literal(query_embedding)
    # Math over-fetches 4x then backfills (see junk filter below). Keyed on the
    # canonical subject id 'mathematics' — the value the corpus stores and the
    # query layer now passes after canonicalising the 'riyaziyyat' alias (GRO-146).
    query_limit = limit * 4 if filters.subject == 'mathematics' else limit
    params = [vector, *params, vector, query_limit]
    where_sql = " and ".join(clauses)

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            select
{CHUNK_COLUMNS_SQL},
              1 - (ce.embedding <=> %s::vector) as score
            from public.chunk_embeddings ce
            join public.chunks c on c.id = ce.chunk_id
            join public.documents d on d.id = c.document_id
            left join public.section_blocks sb on sb.id = c.section_block_id
            where {where_sql}
            order by ce.embedding <=> %s::vector asc, d.source_tier asc
            limit %s
            """,
            params,
        )
        rows = cursor.fetchall()

    if filters.subject == 'mathematics':
        survivors = []
        filtered_out = []
        for row in rows:
            if not _is_math_junk(row["content"]):
                survivors.append(row)
            else:
                filtered_out.append(row)
            if len(survivors) == limit:
                break

        if len(survivors) < limit:
            survivors.extend(filtered_out[:limit - len(survivors)])

        rows = survivors

    return [chunk_from_row(row, score=row["score"]) for row in rows]
