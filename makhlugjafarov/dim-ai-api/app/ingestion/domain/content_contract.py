"""
ContentContract — what a SubjectPipeline promises to emit (GRO-78 CP6).

Each SubjectPipeline declares a ContentContract so downstream stages
(retrieval, generation, KaTeX rendering) can rely on the shape of the content
a subject produces, instead of guessing. This is declarative metadata — it does
not by itself change parsing/chunking/retrieval behavior.

Today only the emitted *content type* differs by subject:
  - History / Geography → prose (Azerbaijani text)
  - Math               → LaTeX-bearing text (formulas survive OCR via GOT-OCR-2.0)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ContentType(str, Enum):
    """The dominant content shape a pipeline emits."""

    PROSE = "prose"
    LATEX = "latex"
    TABLE_MARKDOWN = "table_markdown"


@dataclass(frozen=True)
class ContentContract:
    """Immutable declaration of what a SubjectPipeline emits.

    Attributes:
        content_type: dominant content shape (prose / latex / table_markdown).
        emits_latex: True when chunks may contain LaTeX that must be preserved
            verbatim through chunking and rendered with KaTeX in the UI.
        description: human-readable note for docs / debugging.
    """

    content_type: ContentType
    emits_latex: bool = False
    description: str = ""


# Reusable canonical contracts (shared so pipelines don't redefine them).
PROSE_CONTRACT = ContentContract(
    content_type=ContentType.PROSE,
    emits_latex=False,
    description="Azerbaijani prose textbook content.",
)

LATEX_CONTRACT = ContentContract(
    content_type=ContentType.LATEX,
    emits_latex=True,
    description="Math content with LaTeX formulas preserved for KaTeX rendering.",
)
