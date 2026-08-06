"""Select and render typed content blocks into an LLM-ready form (GRO-79, Phase 5).

The curriculum read-contract surfaces the typed non-prose layer (tables / figures /
formulas) attached to a node alongside its prose. This module is the *judgement*
half: which blocks are worth showing and how to phrase them. It is pure (no DB, no
I/O) so the rules the corpus-wide load taught us are unit-tested, not buried in SQL.

Rules, distilled from loading all 7 books (see GRO-79 evidence):
- **Figures:** the printed ``caption`` is authoritative; the VLM ``description`` is
  low-trust enrichment, used only when there is no caption *and* it is not a
  degenerate loop/refusal.
- **VLM loops:** the ingestion sanitizer drops token-level loops but misses
  *phrase*-level ones ("bir masalı işıqlayır × N"), so we guard those here too.
- **Tables:** only useful with rendered ``markdown``. In **literature** the layout
  detector mis-types poetry columns and multi-column prose as tables, so literature
  tables are demoted (kept structurally, excluded from the grounding body).
- **Formulas:** most carry no captured text → drop the empty ones.
"""

from __future__ import annotations

from app.curriculum.domain.models import BlockView

# AZ labels so the model reads the artefact in the source language of the books.
_LABELS = {
    "data_table": "Cədvəl",
    "exercise_template": "Tapşırıq cədvəli",
    "figure": "Şəkil",
    "formula": "Düstur",
}

_MIN_DESCRIPTION_WORDS = 3
_REFUSAL_PREFIXES = ("üzgünüm", "bağışlayın", "təəssüf", "sorry", "i cannot", "i'm sorry")
# A phrase repeated this many times in a row is a VLM degeneration, not content.
_MAX_PHRASE_REPEAT = 3
_LITERATURE_SUBJECTS = frozenset({"literature", "adabiyyat", "ədəbiyyat"})


def _is_degenerate_description(text: str) -> bool:
    """True for VLM output that is a refusal or a phrase-level repetition loop.

    Complements the ingestion-side token-level guard: catches multi-word cycles
    such as "bir masalı işıqlayır bir masalı işıqlayır …" that repeat a window of
    words rather than a single token.
    """
    stripped = text.strip()
    if len(stripped.split()) < _MIN_DESCRIPTION_WORDS:
        return True
    if stripped.lower().startswith(_REFUSAL_PREFIXES):
        return True
    tokens = stripped.lower().split()
    # Look for a repeating phrase window of length 1..4 covering a long run.
    for window in range(1, 5):
        if len(tokens) < window * (_MAX_PHRASE_REPEAT + 1):
            continue
        for start in range(len(tokens) - window * (_MAX_PHRASE_REPEAT + 1) + 1):
            phrase = tokens[start : start + window]
            repeats = 1
            pos = start + window
            while tokens[pos : pos + window] == phrase:
                repeats += 1
                pos += window
            if repeats > _MAX_PHRASE_REPEAT:
                return True
    return False


def figure_text(block: BlockView) -> str | None:
    """The best available text for a figure: printed caption, else usable VLM text."""
    if block.caption and block.caption.strip():
        return block.caption.strip()
    if block.description and not _is_degenerate_description(block.description):
        return block.description.strip()
    return None


def is_renderable(block: BlockView, *, subject: str | None) -> bool:
    """Whether a block carries trustworthy payload worth grounding on."""
    if block.kind in ("data_table", "exercise_template"):
        if subject and subject.lower() in _LITERATURE_SUBJECTS:
            return False  # literature "tables" are mostly poetry/prose false positives
        return bool(block.markdown and block.markdown.strip())
    if block.kind == "figure":
        return figure_text(block) is not None
    if block.kind == "formula":
        return bool((block.markdown and block.markdown.strip()) or (block.caption and block.caption.strip()))
    return False


def render_block(block: BlockView) -> str:
    """Render one renderable block to a labelled markdown snippet.

    Assumes :func:`is_renderable` already passed for ``block``'s subject.
    """
    label = _LABELS.get(block.kind, block.kind)
    page = f" (səh. {block.page})" if block.page is not None else ""
    if block.kind in ("data_table", "exercise_template"):
        head = f"**{label}{page}:** {block.caption.strip()}" if block.caption and block.caption.strip() else f"**{label}{page}:**"
        return f"{head}\n{block.markdown.strip()}"
    if block.kind == "figure":
        return f"**{label}{page}:** {figure_text(block)}"
    # formula
    body = (block.markdown or block.caption or "").strip()
    return f"**{label}{page}:** {body}"
