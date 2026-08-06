"""Load extracted content blocks (tables / figures / formulas) into Postgres.

GRO-79 (Phase 4). The heavy detection/extraction/VLM runs offline on Kaggle and
emits a JSON artifact of typed blocks (see ``dim-geo-blocks-ingest-kernel``). This
is the thin, DB-side counterpart that the local writer calls: it attaches each
block to the deepest existing ``curriculum_node`` covering its page (reusing the
*same* pure :func:`attach_blocks_to_nodes` the unit tests pin) and writes the rows.

It is ADDITIVE and idempotent per document: it never touches chunks/embeddings or
``corpus_version``; re-running replaces only this document's ``content_blocks`` rows
(delete-then-insert), so a partial Kaggle artifact can be reloaded safely.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import psycopg

from app.ingestion.domain.content_blocks import (
    attach_blocks_to_nodes,
    sanitize_vlm_descriptions,
)
from app.ingestion.domain.models import ContentBlock, CurriculumNode


@dataclass(frozen=True)
class ContentBlockLoadResult:
    document_id: str
    blocks_inserted: int
    blocks_attached: int          # blocks that resolved to a curriculum node
    blocks_orphaned: int          # blocks on pages no node covers (front matter)
    nodes_available: int


def _load_nodes(cur: psycopg.Cursor, document_id: str) -> tuple[list[CurriculumNode], dict[str, str]]:
    """Existing curriculum nodes as domain objects + a node_path -> row-id map."""
    cur.execute(
        "select id, node_path, level, ordinal, title, page_start, page_end "
        "from curriculum_nodes where document_id = %s",
        (document_id,),
    )
    nodes: list[CurriculumNode] = []
    id_by_path: dict[str, str] = {}
    for row in cur.fetchall():
        node_id, node_path, level, ordinal, title, page_start, page_end = row
        id_by_path[node_path] = str(node_id)
        nodes.append(
            CurriculumNode(
                node_path=node_path,
                parent_path=node_path.rsplit(".", 1)[0] if "." in node_path else None,
                level=level,
                ordinal=ordinal,
                title=title,
                raw_title=title,  # DB keeps only the cleaned title; raw is not persisted
                page_start=page_start,
                page_end=page_end,
            )
        )
    return nodes, id_by_path


def load_content_blocks_to_postgres(
    *, database_url: str, source_id: str, blocks: list[ContentBlock], replace: bool = True
) -> ContentBlockLoadResult:
    """Attach blocks to the document's curriculum tree and persist them.

    Raises ``LookupError`` if ``source_id`` has no document row (the tree/chunks must
    already be ingested — blocks are an enrichment layered on top).
    """
    with psycopg.connect(database_url, connect_timeout=15) as conn, conn.cursor() as cur:
        cur.execute("select id from documents where source_id = %s", (source_id,))
        row = cur.fetchone()
        if row is None:
            raise LookupError(f"no document row for source_id={source_id!r}; ingest it first")
        document_id = str(row[0])

        nodes, id_by_path = _load_nodes(cur, document_id)
        attach_blocks_to_nodes(blocks, nodes)  # sets block.node_path in place (tested logic)

        if replace:
            cur.execute("delete from content_blocks where document_id = %s", (document_id,))

        attached = orphaned = 0
        for b in blocks:
            node_id = id_by_path.get(b.node_path) if b.node_path else None
            if node_id is not None:
                attached += 1
            else:
                orphaned += 1
            cur.execute(
                """
                insert into content_blocks (
                    document_id, curriculum_node_id, ordinal, kind, page, bbox,
                    markdown, n_rows, n_cols, fill_ratio, caption, vlm_description,
                    detection_confidence, extraction_method, metadata
                ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    document_id, node_id, b.ordinal, b.kind, b.page,
                    json.dumps(b.bbox) if b.bbox is not None else None,
                    b.markdown, b.n_rows, b.n_cols, b.fill_ratio, b.caption,
                    b.vlm_description, b.detection_confidence, b.extraction_method,
                    json.dumps(b.metadata or {}),
                ),
            )
        conn.commit()

    return ContentBlockLoadResult(
        document_id=document_id,
        blocks_inserted=len(blocks),
        blocks_attached=attached,
        blocks_orphaned=orphaned,
        nodes_available=len(nodes),
    )


def content_blocks_from_artifact(payload: dict) -> tuple[str, list[ContentBlock]]:
    """Parse a Kaggle extraction artifact into (source_id, ContentBlocks).

    Tolerant of the kernel's extra per-block keys (``crop_file`` etc.): only the
    model's own fields are consumed.
    """
    source_id = payload["source_id"]
    fields = set(ContentBlock.model_fields) - {"source_id"}
    blocks = [
        ContentBlock(source_id=source_id, **{k: v for k, v in raw.items() if k in fields})
        for raw in payload.get("blocks", [])
    ]
    sanitize_vlm_descriptions(blocks)  # drop degenerate VLM loops/refusals; keep printed caption
    return source_id, blocks
