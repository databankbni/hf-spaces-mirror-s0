"""Content generation from a curriculum slice (GRO-158, utilise half).

The apex intent's pay-off: a stored, clean topic slice (breadcrumb + subtree +
prose) is handed to an LLM to *generate* study content — a summary, key points,
or a quiz — for one curriculum node. This module is pure: it turns a
:class:`~app.curriculum.domain.models.TopicSlice` into a grounded prompt and
shapes the model's text into a :class:`Lesson`. No I/O, no provider calls — those
live in the application layer so the prompts stay unit-testable.

Grounding is non-negotiable (the GRO-111 faithfulness contract): every prompt
binds the model to the slice text only and tells it to answer in Azerbaijani, the
language of the source books, refusing when the material is too thin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.curriculum.domain.models import TopicSlice

LessonKind = Literal["summary", "key_points", "quiz"]
LESSON_KINDS: tuple[LessonKind, ...] = ("summary", "key_points", "quiz")


@dataclass(frozen=True)
class LessonPromptSpec:
    """The provider-agnostic prompt for one content-generation request."""

    system_prompt: str
    instruction: str        # the "question" turn handed to the provider port
    max_tokens: int


@dataclass(frozen=True)
class Lesson:
    """Generated study content for one curriculum node, plus its provenance."""

    kind: LessonKind
    source_id: str
    subject: str | None
    node_path: str
    node_title: str
    breadcrumb: tuple[str, ...]
    page_start: int | None
    page_end: int | None
    grounded_chunk_count: int   # chunks from the slice the content was built on
    grounded_block_count: int   # typed blocks (tables/figures/formulas) in the slice
    context_truncated: bool     # slice prose was clipped by max_chars
    model: str
    content: str


# A node with no prose attached can't ground anything — generating from an empty
# slice would invite hallucination, so the use-case refuses before calling an LLM.
class EmptySliceError(Exception):
    """Raised when a slice carries no text to generate content from."""


_GROUNDING_RULES = (
    "Sən Azərbaycan DİM imtahanına hazırlaşan şagird üçün dərslik əsasında "
    "tədris materialı hazırlayan müəllimsən.\n"
    "Qaydalar:\n"
    "- YALNIZ aşağıda verilən dərslik mətnindən istifadə et. Mətndə olmayan "
    "faktı, tarixi və ya rəqəmi ƏLAVƏ ETMƏ.\n"
    "- Mətndəki cədvəllər, şəkil təsvirləri və düsturlar da mənbənin bir "
    "hissəsidir; uyğun olduqda onlardan istifadə et.\n"
    "- Cavabı Azərbaycan dilində yaz.\n"
    "- Əgər verilən mətn tələb olunan məzmunu hazırlamaq üçün kifayət deyilsə, "
    'bunu açıq şəkildə bildir ("Verilən mətn bu mövzunu əhatə etmir.") və '
    "uydurma.\n"
)

_KIND_INSTRUCTIONS: dict[LessonKind, str] = {
    "summary": (
        "Bu mövzunun aydın, mütəşəkkil xülasəsini hazırla. Əsas anlayışları "
        "məntiqi ardıcıllıqla izah et ki, şagird mövzunu ümumi şəkildə başa düşsün."
    ),
    "key_points": (
        "Bu mövzudan imtahan üçün ən vacib məqamları markerli siyahı (•) şəklində "
        "çıxar. Hər bənd qısa, dəqiq və yadda qalan olsun."
    ),
    "quiz": (
        "Bu mövzu üzrə 5 sual hazırla: hər biri 4 variantlı (A–D) test sualı olsun. "
        "Hər sualdan sonra düzgün cavabı və bir cümləlik izahı göstər. Suallar yalnız "
        "verilən mətnə əsaslansın."
    ),
}

_KIND_MAX_TOKENS: dict[LessonKind, int] = {
    "summary": 1200,
    "key_points": 900,
    "quiz": 1600,
}


def build_lesson_prompt(kind: LessonKind, slice_: TopicSlice) -> LessonPromptSpec:
    """Turn a topic slice into a grounded, kind-specific generation prompt."""
    if kind not in _KIND_INSTRUCTIONS:
        raise ValueError(f"unknown lesson kind: {kind!r}")

    topic = " > ".join(slice_.breadcrumb) if slice_.breadcrumb else slice_.node.title
    instruction = f"Mövzu: {topic}\n\n{_KIND_INSTRUCTIONS[kind]}"
    return LessonPromptSpec(
        system_prompt=_GROUNDING_RULES,
        instruction=instruction,
        max_tokens=_KIND_MAX_TOKENS[kind],
    )


def assemble_lesson(*, kind: LessonKind, slice_: TopicSlice, model: str, content: str) -> Lesson:
    """Pair generated ``content`` with the slice's provenance for the response."""
    return Lesson(
        kind=kind,
        source_id=slice_.source_id,
        subject=slice_.subject,
        node_path=slice_.node.node_path,
        node_title=slice_.node.title,
        breadcrumb=slice_.breadcrumb,
        page_start=slice_.page_start,
        page_end=slice_.page_end,
        grounded_chunk_count=slice_.chunk_count,
        grounded_block_count=slice_.block_count,
        context_truncated=slice_.truncated,
        model=model,
        content=content,
    )
