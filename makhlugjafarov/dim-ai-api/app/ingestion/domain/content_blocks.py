"""Pure domain logic for typed content blocks (tables / figures / formulas).

The heavy detection/extraction (DocLayout-YOLO region detection, img2table cell
OCR, the VLM figure captioner) lives in infrastructure and runs on Kaggle where
the page images and GPU are. This module holds only the DB-free, deterministic
decisions that shape those raw detections into :class:`ContentBlock`s — so they
are unit-testable without a PDF, a model, or a database:

* classify a table as real data vs a blank exercise worksheet (``fill_ratio``),
* pair a figure region with its nearest printed caption region (geometry),
* attach each block to the deepest curriculum node covering its page.

Keeping this pure mirrors ``curriculum.py`` (pure) vs ``ocr.py``/``got_ocr.py``
(heavy infra), and lets the Kaggle re-ingest kernel import the *same* rules the
tests pin, rather than re-deriving them.
"""

from __future__ import annotations

import math

from app.ingestion.domain.curriculum import resolve_node_for_page
from app.ingestion.domain.models import BlockKind, ContentBlock, CurriculumNode

# Fraction of non-empty cells at/above which a detected table is treated as real
# data rather than a blank fill-in worksheet. The GRO-79 spike showed ~half of
# geography "tables" are exercise scaffolds (headers only, empty body); this
# threshold keeps those out of the data path while still recording them.
DATA_TABLE_FILL_THRESHOLD = 0.35


def compute_fill_ratio(cells: list[str]) -> float:
    """Share of non-blank cells in a flattened table (0.0 when empty)."""
    if not cells:
        return 0.0
    nonempty = sum(1 for c in cells if c is not None and str(c).strip())
    return nonempty / len(cells)


def classify_table_kind(fill_ratio: float) -> BlockKind:
    """A table is ``data_table`` when filled enough, else ``exercise_template``."""
    return "data_table" if fill_ratio >= DATA_TABLE_FILL_THRESHOLD else "exercise_template"


def _center(bbox: list[float]) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def pair_caption_bbox(
    figure_bbox: list[float], caption_bboxes: list[list[float]]
) -> list[float] | None:
    """The caption region nearest a figure, preferring one *below* it.

    Textbook captions sit under the figure far more often than above, so a caption
    below is distance-discounted before picking the nearest. Returns ``None`` when
    there are no candidate caption regions. Pure geometry — shared by the Kaggle
    extractor and the tests so pairing can't silently diverge.
    """
    if not caption_bboxes:
        return None
    fx, fy = _center(figure_bbox)
    best: list[float] | None = None
    best_d = math.inf
    for cb in caption_bboxes:
        cx, cy = _center(cb)
        d = math.hypot(cx - fx, cy - fy)
        if cy >= fy:  # below the figure → preferred
            d *= 0.6
        if d < best_d:
            best, best_d = cb, d
    return best


# VLM figure descriptions are a best-effort enrichment (the printed caption is the
# authoritative text). The GRO-79 full-book run showed Qwen2-VL sometimes degenerates
# into token loops ("qızıl qızıl qızıl…") or refusals ("Üzgünüm…"). This guard drops
# only the *egregious* garbage; borderline-but-informative descriptions are kept.
_REFUSAL_PREFIXES = ("üzgünüm", "bağışlayın", "təəssüf", "sorry", "i cannot", "i'm sorry")
_MAX_CONSECUTIVE_REPEAT = 4


def is_degenerate_vlm_caption(text: str | None) -> bool:
    """True when a VLM description is junk (empty, a refusal, or a token loop)."""
    if text is None or len(text.split()) < 3:
        return True
    tokens = text.split()
    if text.strip().lower().startswith(_REFUSAL_PREFIXES):
        return True
    run = 1
    for prev, cur in zip(tokens, tokens[1:]):
        run = run + 1 if cur.lower() == prev.lower() else 1
        if run >= _MAX_CONSECUTIVE_REPEAT:
            return True
    return False


def sanitize_vlm_descriptions(blocks: list[ContentBlock]) -> int:
    """Null out degenerate ``vlm_description``s in place; return how many were cleared."""
    cleared = 0
    for b in blocks:
        if b.vlm_description is not None and is_degenerate_vlm_caption(b.vlm_description):
            b.vlm_description = None
            cleared += 1
    return cleared


def attach_blocks_to_nodes(
    blocks: list[ContentBlock], nodes: list[CurriculumNode]
) -> None:
    """Set each block's ``node_path`` to the deepest node covering its page.

    Mutates in place (the loader then maps ``node_path`` → the node row id for the
    FK, exactly as it does for sections/chunks). Blocks on pages no node covers
    (front matter) keep ``node_path = None`` and load unattached.
    """
    for block in blocks:
        node = resolve_node_for_page(nodes, block.page)
        block.node_path = node.node_path if node is not None else None
