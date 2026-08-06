"""Postgres reads for the curriculum topic-slice contract (GRO-158).

All structural traversal is pushed into the database via recursive CTEs — the
``curriculum_nodes`` self-FK plus ``curriculum_nodes_tree_idx`` make the ancestor
walk and subtree expansion cheap, and Postgres is the right place to do them.
This module returns plain :class:`NodeView` rows and a ``node_path → [text]`` chunk
map; the pure :mod:`slice_builder` does the assembly.
"""

from __future__ import annotations

from app.curriculum.domain.models import (
    BlockView,
    CatalogEntry,
    NodeView,
    OutlineNode,
    TopicSliceError,
    is_browsable,
)
from app.curriculum.domain.text_fold import az_fold


def _row_to_node(row) -> NodeView:
    return NodeView(
        node_id=str(row["id"]),
        node_path=row["node_path"],
        level=row["level"],
        title=row["title"],
        page_start=row["page_start"],
        page_end=row["page_end"],
    )


def resolve_document(connection, *, source_id: str | None, subject: str | None) -> dict:
    """Resolve the document to read from, by ``source_id`` or canonical ``subject``.

    A ``subject`` that maps to more than one book with a curriculum tree is
    ambiguous and raises — the caller must disambiguate with a ``source_id``.
    """
    with connection.cursor() as cur:
        if source_id:
            cur.execute(
                "select id, source_id, subject from public.documents where source_id = %s",
                (source_id,),
            )
            row = cur.fetchone()
            if not row:
                raise TopicSliceError(f"no document with source_id={source_id!r}")
            return row
        if subject:
            cur.execute(
                """
                select d.id, d.source_id, d.subject
                  from public.documents d
                 where d.subject = %s
                   and exists (select 1 from public.curriculum_nodes n where n.document_id = d.id)
                 order by d.source_id
                """,
                (subject,),
            )
            rows = cur.fetchall()
            if not rows:
                raise TopicSliceError(f"no document with a curriculum tree for subject={subject!r}")
            if len(rows) > 1:
                ids = ", ".join(r["source_id"] for r in rows)
                raise TopicSliceError(
                    f"subject={subject!r} is ambiguous ({ids}); pass an explicit source_id"
                )
            return rows[0]
    raise TopicSliceError("resolve_document requires source_id or subject")


def resolve_node(
    connection,
    *,
    document_id,
    node_path: str | None = None,
    node_id: str | None = None,
    node_title: str | None = None,
) -> NodeView:
    """Resolve the target node within a document by path, id, or title (ILIKE).

    Title resolution returns the highest, earliest match (shortest ``node_path``)
    so an ambiguous title lands on the broadest matching topic rather than a deep
    leaf.
    """
    with connection.cursor() as cur:
        if node_id:
            cur.execute(
                "select id, node_path, level, title, page_start, page_end "
                "from public.curriculum_nodes where document_id = %s and id = %s",
                (document_id, node_id),
            )
        elif node_path:
            cur.execute(
                "select id, node_path, level, title, page_start, page_end "
                "from public.curriculum_nodes where document_id = %s and node_path = %s",
                (document_id, node_path),
            )
        elif node_title:
            return _resolve_by_title(cur, document_id=document_id, node_title=node_title)
        else:
            raise TopicSliceError("resolve_node requires node_path, node_id, or node_title")
        row = cur.fetchone()
    if not row:
        raise TopicSliceError("no curriculum node matched the given selector")
    return _row_to_node(row)


def _resolve_by_title(cur, *, document_id, node_title: str) -> NodeView:
    """Diacritic-/case-insensitive title match, broadest (shortest path) first.

    Azerbaijani titles carry diacritics and the dotted/dotless I that SQL ``ILIKE``
    and naive casefolding mishandle, so we fold both sides in Python over the
    book's node set (tens of rows). The broadest match wins so an ambiguous term
    lands on the containing topic rather than a deep leaf.
    """
    cur.execute(
        "select id, node_path, level, title, page_start, page_end "
        "from public.curriculum_nodes where document_id = %s",
        (document_id,),
    )
    needle = az_fold(node_title)
    matches = [r for r in cur.fetchall() if needle in az_fold(r["title"])]
    if not matches:
        raise TopicSliceError(f"no curriculum node title matched {node_title!r}")
    best = min(matches, key=lambda r: (len(r["node_path"]), r["node_path"]))
    return _row_to_node(best)


def fetch_ancestors(connection, *, node_id: str) -> list[NodeView]:
    """Ancestors ordered root → parent (the node itself excluded)."""
    with connection.cursor() as cur:
        cur.execute(
            """
            with recursive up as (
                select id, parent_id, node_path, level, title, page_start, page_end, 0 as d
                  from public.curriculum_nodes where id = %s
                union all
                select p.id, p.parent_id, p.node_path, p.level, p.title,
                       p.page_start, p.page_end, up.d + 1
                  from public.curriculum_nodes p
                  join up on p.id = up.parent_id
            )
            select id, node_path, level, title, page_start, page_end
              from up where id != %s order by d desc
            """,
            (node_id, node_id),
        )
        return [_row_to_node(r) for r in cur.fetchall()]


def fetch_subtree(connection, *, node_id: str) -> list[NodeView]:
    """The node plus all its descendants (caller separates node vs descendants)."""
    with connection.cursor() as cur:
        cur.execute(
            """
            with recursive down as (
                select id, parent_id, node_path, level, title, page_start, page_end
                  from public.curriculum_nodes where id = %s
                union all
                select c.id, c.parent_id, c.node_path, c.level, c.title,
                       c.page_start, c.page_end
                  from public.curriculum_nodes c
                  join down on c.parent_id = down.id
            )
            select id, node_path, level, title, page_start, page_end
              from down order by string_to_array(node_path, '.')::int[]
            """,
            (node_id,),
        )
        return [_row_to_node(r) for r in cur.fetchall()]


def fetch_chunks_by_node_path(connection, *, node_ids: list[str]) -> dict[str, list[str]]:
    """Map ``node_path → [chunk text]`` for the given subtree node ids, in order."""
    if not node_ids:
        return {}
    with connection.cursor() as cur:
        cur.execute(
            """
            select n.node_path, c.content
              from public.chunks c
              join public.curriculum_nodes n on n.id = c.curriculum_node_id
             where c.curriculum_node_id = any(%s)
             order by string_to_array(n.node_path, '.')::int[], c.chunk_index
            """,
            (node_ids,),
        )
        out: dict[str, list[str]] = {}
        for row in cur.fetchall():
            out.setdefault(row["node_path"], []).append(row["content"])
    return out


def fetch_blocks_by_node_path(connection, *, node_ids: list[str]) -> dict[str, list[BlockView]]:
    """Map ``node_path → [BlockView]`` for the given subtree node ids.

    Ordered by page then ordinal so a block's reading order mirrors the book; the
    pure :mod:`block_render` layer then decides which to keep and how to phrase them.
    """
    if not node_ids:
        return {}
    with connection.cursor() as cur:
        cur.execute(
            """
            select n.node_path, cb.kind, cb.page, cb.caption, cb.vlm_description,
                   cb.markdown, cb.n_rows, cb.n_cols, cb.fill_ratio
              from public.content_blocks cb
              join public.curriculum_nodes n on n.id = cb.curriculum_node_id
             where cb.curriculum_node_id = any(%s)
             order by string_to_array(n.node_path, '.')::int[],
                      cb.page nulls last, cb.ordinal
            """,
            (node_ids,),
        )
        out: dict[str, list[BlockView]] = {}
        for row in cur.fetchall():
            out.setdefault(row["node_path"], []).append(
                BlockView(
                    node_path=row["node_path"],
                    kind=row["kind"],
                    page=row["page"],
                    caption=row["caption"],
                    description=row["vlm_description"],
                    markdown=row["markdown"],
                    n_rows=row["n_rows"],
                    n_cols=row["n_cols"],
                    fill_ratio=float(row["fill_ratio"]) if row["fill_ratio"] is not None else None,
                )
            )
    return out


def _block_counts_by_node_id(connection, *, document_id) -> dict:
    """``node_id → block_count`` for a document (counted separately to avoid a
    cartesian blow-up with the chunk join in :func:`fetch_outline_nodes`)."""
    with connection.cursor() as cur:
        cur.execute(
            "select curriculum_node_id, count(*) c from public.content_blocks "
            "where document_id = %s and curriculum_node_id is not null "
            "group by curriculum_node_id",
            (document_id,),
        )
        return {row["curriculum_node_id"]: row["c"] for row in cur.fetchall()}


def fetch_outline_nodes(connection, *, document_id) -> list[OutlineNode]:
    """Every node in the document, syllabus order, with direct chunk counts.

    The per-node chunk count and ``has_children`` flag let a navigating module see
    where the text actually lives without pulling any prose.
    """
    with connection.cursor() as cur:
        cur.execute(
            """
            select
              n.id, n.parent_id, n.node_path, n.level, n.title,
              n.page_start, n.page_end,
              count(c.id) as chunk_count
              from public.curriculum_nodes n
              left join public.chunks c on c.curriculum_node_id = n.id
             where n.document_id = %s
             group by n.id
             order by string_to_array(n.node_path, '.')::int[]
            """,
            (document_id,),
        )
        rows = cur.fetchall()
    parent_ids = {r["parent_id"] for r in rows if r["parent_id"] is not None}
    block_counts = _block_counts_by_node_id(connection, document_id=document_id)
    return [
        OutlineNode(
            node_path=r["node_path"],
            level=r["level"],
            title=r["title"],
            page_start=r["page_start"],
            page_end=r["page_end"],
            chunk_count=r["chunk_count"],
            has_children=r["id"] in parent_ids,
            block_count=block_counts.get(r["id"], 0),
        )
        for r in rows
    ]


def fetch_catalog(connection) -> list[CatalogEntry]:
    """Every non-archived book with its node and chunk counts (catalog read).

    Counts are computed with correlated sub-selects rather than joins so the two
    independent fan-outs (nodes, chunks) can't multiply into a cartesian product.
    ``browsable`` is derived in the pure domain rule :func:`is_browsable` (clean
    source + a real tree) — the flag the Home screen uses to split courses from
    ask-only subjects.
    """
    with connection.cursor() as cur:
        cur.execute(
            """
            select
              d.source_id, d.title, d.subject, d.grade, d.language, d.source_type,
              (select count(*) from public.curriculum_nodes n
                 where n.document_id = d.id) as node_count,
              (select count(*) from public.chunks c
                 where c.document_id = d.id) as chunk_count
              from public.documents d
             where d.status <> 'archived'
             order by d.subject nulls last, d.grade nulls last, d.source_id
            """
        )
        rows = cur.fetchall()
    return [
        CatalogEntry(
            source_id=r["source_id"],
            title=r["title"],
            subject=r["subject"],
            grade=r["grade"],
            language=r["language"],
            source_type=r["source_type"],
            node_count=r["node_count"],
            chunk_count=r["chunk_count"],
            browsable=is_browsable(r["source_type"], r["node_count"]),
        )
        for r in rows
    ]


def count_document_chunks(connection, *, document_id) -> tuple[int, int]:
    """Return ``(total_chunks, tagged_chunks)`` for a document's coverage read."""
    with connection.cursor() as cur:
        cur.execute(
            "select count(*) c, count(curriculum_node_id) t "
            "from public.chunks where document_id = %s",
            (document_id,),
        )
        row = cur.fetchone()
    return row["c"], row["t"]
