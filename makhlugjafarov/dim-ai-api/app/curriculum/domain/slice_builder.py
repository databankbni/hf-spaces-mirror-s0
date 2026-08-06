"""Pure assembly of a :class:`TopicSlice` from already-fetched tree rows.

Kept free of any DB so it is unit-testable in isolation: the infrastructure layer
runs the recursive CTEs and hands this function plain :class:`NodeView` rows plus
a ``node_path → [chunk text]`` map; this function decides ordering, the breadcrumb,
the page span, and renders the LLM-ready body.
"""

from __future__ import annotations

from app.curriculum.domain.block_render import is_renderable, render_block
from app.curriculum.domain.models import BlockView, NodeView, TopicSlice

# Heading that introduces the typed non-prose layer (tables/figures/formulas).
_BLOCKS_HEADING = "\n\n## Cədvəllər, şəkillər və düsturlar"


def _natural_key(node_path: str) -> list[int]:
    """Sort key so ``"1.2"`` precedes ``"1.10"`` (ordinal segments, not text)."""
    out: list[int] = []
    for part in node_path.split("."):
        try:
            out.append(int(part))
        except ValueError:
            out.append(0)
    return out


def _page_span(nodes: list[NodeView]) -> tuple[int | None, int | None]:
    starts = [n.page_start for n in nodes if n.page_start is not None]
    ends = [n.page_end for n in nodes if n.page_end is not None]
    return (min(starts) if starts else None, max(ends) if ends else None)


def _heading(item: NodeView, node: NodeView) -> str:
    """Markdown heading for ``item`` relative to the slice root ``node``.

    The root reads as ``##``; each level deeper adds a ``#`` (capped at 6) so the
    rendered slice mirrors the book's own nesting.
    """
    depth = min(2 + max(item.level - node.level, 0), 6)
    return "#" * depth + " " + item.title


def build_topic_slice(
    *,
    source_id: str,
    subject: str | None,
    node: NodeView,
    ancestors: list[NodeView],
    descendants: list[NodeView],
    chunks_by_node_path: dict[str, list[str]],
    blocks_by_node_path: dict[str, list[BlockView]] | None = None,
    include_descendants: bool = True,
    max_chars: int = 12000,
    max_blocks: int = 40,
) -> TopicSlice:
    """Assemble the LLM-ready slice for ``node`` and (optionally) its subtree.

    ``ancestors`` must be ordered root → parent; ``descendants`` is the raw subtree
    (re-sorted here into syllabus order). ``chunks_by_node_path`` maps a node's
    ``node_path`` to its chunk texts in chunk order. Rendering emits whole chunks
    only: the first chunk that would cross ``max_chars`` stops the body and sets
    ``truncated`` — a module never receives a half-sentence.
    """
    ordered_descendants = sorted(descendants, key=lambda n: _natural_key(n.node_path))
    included = [node, *ordered_descendants] if include_descendants else [node]

    breadcrumb = tuple(a.title for a in ancestors) + (node.title,)
    page_start, page_end = _page_span(included)

    # A top breadcrumb line orients the model; then each node is a heading followed
    # by its chunk text, in syllabus order.
    parts: list[str] = ["# " + " > ".join(breadcrumb)]
    used = len(parts[0])
    chunk_count = 0
    truncated = False
    fully_rendered: set[str] = set()

    for item in included:
        texts = chunks_by_node_path.get(item.node_path, [])
        if not texts:
            continue
        if truncated:
            break
        heading = "\n\n" + _heading(item, node)
        if used + len(heading) > max_chars:
            truncated = True
            break
        parts.append(heading)
        used += len(heading)
        emitted = 0
        for text in texts:
            piece = "\n" + text
            if used + len(piece) > max_chars:
                truncated = True
                break
            parts.append(piece)
            used += len(piece)
            chunk_count += 1
            emitted += 1
        if emitted == len(texts):
            fully_rendered.add(item.node_path)

    # A node is "omitted" if it carries text that did not fully make the budget —
    # so a caller can re-fetch those node_paths with a higher cap or on their own.
    omitted = tuple(
        item.node_path
        for item in included
        if chunks_by_node_path.get(item.node_path) and item.node_path not in fully_rendered
    )

    # The typed non-prose layer is appended after the prose so grounding text stays
    # primary; blocks share the same char budget and a block cap, and only those
    # actually rendered are reported (so the structured `blocks` match `content`).
    rendered_blocks: list[BlockView] = []
    if blocks_by_node_path:
        renderable = [
            b
            for item in included
            for b in blocks_by_node_path.get(item.node_path, [])
            if is_renderable(b, subject=subject)
        ][:max_blocks]
        if renderable and used + len(_BLOCKS_HEADING) <= max_chars:
            parts.append(_BLOCKS_HEADING)
            used += len(_BLOCKS_HEADING)
            for block in renderable:
                snippet = "\n\n" + render_block(block)
                if used + len(snippet) > max_chars:
                    break
                parts.append(snippet)
                used += len(snippet)
                rendered_blocks.append(block)

    return TopicSlice(
        source_id=source_id,
        subject=subject,
        node=node,
        breadcrumb=breadcrumb,
        ancestors=tuple(ancestors),
        descendants=tuple(ordered_descendants),
        page_start=page_start,
        page_end=page_end,
        chunk_count=chunk_count,
        content="".join(parts),
        truncated=truncated,
        omitted_node_paths=omitted,
        block_count=len(rendered_blocks),
        blocks=tuple(rendered_blocks),
    )
