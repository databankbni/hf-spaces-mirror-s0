"""Structured study tools from a curriculum slice — flashcards & quizzes.

The companion to :mod:`app.curriculum.domain.lesson`. ``lesson`` produces *prose*
(summary / key points) the client renders as text. The mobile app, however, needs
**structured** artefacts it can render as interactive widgets — flip-cards and
tappable multiple-choice questions. A free-text Azerbaijani blob cannot be turned
into reliable cards, so this module:

1. builds a grounded prompt that demands **strict JSON only** (no markdown, no
   commentary), in Azerbaijani, bound to the slice text (the GRO-111 faithfulness
   contract); and
2. parses the model's reply *tolerantly* — stripping code fences and surrounding
   prose, accepting common key/answer spellings — into validated dataclasses.

Everything here is pure (no I/O, no provider calls): the orchestration lives in
the application layer so the prompts and — crucially — the parser stay
exhaustively unit-testable. The parser is the reliability core: LLM JSON is
routinely fenced, prefixed with prose, or answers questions with a letter instead
of an index, and the client must never see any of that.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.curriculum.domain.lesson import LessonPromptSpec
from app.curriculum.domain.models import TopicSlice


# --- errors ----------------------------------------------------------------


class StudyToolParseError(Exception):
    """Raised when the model's reply cannot be parsed into usable study items.

    This is an *upstream* failure (the model produced unusable output), distinct
    from a resolution failure (no book/node) or an empty slice; the route maps it
    to a 502 so the client can offer a retry rather than treat it as user error.
    """


# --- domain types ----------------------------------------------------------


@dataclass(frozen=True)
class Flashcard:
    """One two-sided study card. ``front`` prompts recall; ``back`` is the answer."""

    front: str
    back: str


@dataclass(frozen=True)
class FlashcardDeck:
    """A generated deck for one curriculum node, plus its provenance."""

    source_id: str
    subject: str | None
    node_path: str
    node_title: str
    breadcrumb: tuple[str, ...]
    page_start: int | None
    page_end: int | None
    grounded_chunk_count: int
    grounded_block_count: int
    context_truncated: bool
    model: str
    cards: tuple[Flashcard, ...]


@dataclass(frozen=True)
class QuizQuestion:
    """One multiple-choice question with a known correct option and a rationale."""

    prompt: str
    options: tuple[str, ...]
    correct_index: int            # 0-based index into ``options``
    explanation: str              # may be empty if the model omitted one


@dataclass(frozen=True)
class Quiz:
    """A generated quiz for one curriculum node, plus its provenance."""

    source_id: str
    subject: str | None
    node_path: str
    node_title: str
    breadcrumb: tuple[str, ...]
    page_start: int | None
    page_end: int | None
    grounded_chunk_count: int
    grounded_block_count: int
    context_truncated: bool
    model: str
    questions: tuple[QuizQuestion, ...]


# --- prompt building -------------------------------------------------------

# Grounding mirrors lesson._GROUNDING_RULES (faithfulness contract) but adds the
# hard requirement that the reply be *machine-readable JSON only* — the single
# most common failure is the model wrapping JSON in prose or ```json fences.
_JSON_GROUNDING_RULES = (
    "Sən Azərbaycan DİM imtahanına hazırlaşan şagird üçün dərslik əsasında "
    "interaktiv tədris materialı hazırlayan müəllimsən.\n"
    "Qaydalar:\n"
    "- YALNIZ aşağıda verilən dərslik mətnindən istifadə et. Mətndə olmayan "
    "faktı, tarixi və ya rəqəmi ƏLAVƏ ETMƏ.\n"
    "- Bütün mətn (suallar, cavablar, izahlar) Azərbaycan dilində olsun.\n"
    "- ÇOX VACİB: Cavabını YALNIZ etibarlı JSON formatında ver. Heç bir "
    "izahedici mətn, başlıq və ya markdown kod bloku (```) ƏLAVƏ ETMƏ. "
    "Cavab birbaşa JSON ilə başlamalıdır.\n"
)

_FLASHCARDS_INSTRUCTION = (
    "Bu mövzu üzrə {count} ədəd fleş-kart hazırla. Hər kart bir anlayışı və ya "
    "faktı yoxlasın.\n"
    'JSON formatı: bir massiv, hər element {{"front": "...", "back": "..."}} '
    'şəklində. "front" qısa sual və ya termin, "back" isə dəqiq cavab olsun.\n'
    'Nümunə: [{{"front": "Mitoz nədir?", "back": "Hüceyrə bölünməsidir."}}]'
)

_QUIZ_INSTRUCTION = (
    "Bu mövzu üzrə {count} ədəd çoxvariantlı test sualı hazırla.\n"
    "JSON formatı: bir massiv, hər element "
    '{{"question": "...", "options": ["A variantı", "B variantı", '
    '"C variantı", "D variantı"], "correct_index": 0, "explanation": "..."}} '
    'şəklində. "options" 4 variant olsun, "correct_index" düzgün variantın '
    'sıfırdan başlayan indeksi (0–3), "explanation" isə bir cümləlik izah olsun.'
)

_FLASHCARDS_MAX_TOKENS = 2000
_QUIZ_MAX_TOKENS = 2200


def _topic(slice_: TopicSlice) -> str:
    return " > ".join(slice_.breadcrumb) if slice_.breadcrumb else slice_.node.title


def build_flashcards_prompt(slice_: TopicSlice, *, count: int) -> LessonPromptSpec:
    """Grounded, JSON-only prompt for a flashcard deck of ``count`` cards."""
    instruction = (
        f"Mövzu: {_topic(slice_)}\n\n"
        + _FLASHCARDS_INSTRUCTION.format(count=count)
    )
    return LessonPromptSpec(
        system_prompt=_JSON_GROUNDING_RULES,
        instruction=instruction,
        max_tokens=_FLASHCARDS_MAX_TOKENS,
    )


def build_quiz_prompt(slice_: TopicSlice, *, count: int) -> LessonPromptSpec:
    """Grounded, JSON-only prompt for a quiz of ``count`` MCQ questions."""
    instruction = (
        f"Mövzu: {_topic(slice_)}\n\n"
        + _QUIZ_INSTRUCTION.format(count=count)
    )
    return LessonPromptSpec(
        system_prompt=_JSON_GROUNDING_RULES,
        instruction=instruction,
        max_tokens=_QUIZ_MAX_TOKENS,
    )


# --- parsing (the reliability core) ----------------------------------------

_FENCE_OPEN = re.compile(r"^```[a-zA-Z0-9]*\s*\n?")
_FENCE_CLOSE = re.compile(r"\n?```\s*$")


def _extract_json_array(raw: str) -> list:
    """Pull a JSON array out of a model reply that may be fenced or prose-wrapped.

    Handles the three routine LLM deviations from "JSON only": a ```json fence, a
    sentence of preamble before the array, and trailing commentary after it. Finds
    the outermost ``[ … ]`` span and parses it. Raises :class:`StudyToolParseError`
    if no array can be recovered.
    """
    if not raw or not raw.strip():
        raise StudyToolParseError("model returned an empty reply")

    text = raw.strip()
    text = _FENCE_OPEN.sub("", text)
    text = _FENCE_CLOSE.sub("", text).strip()

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise StudyToolParseError("no JSON array found in model output")

    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise StudyToolParseError(f"model output was not valid JSON: {exc.msg}") from exc

    if not isinstance(parsed, list):
        raise StudyToolParseError("model output JSON was not an array")
    return parsed


def _first_str(item: dict, keys: tuple[str, ...]) -> str:
    """First non-empty string value among ``keys`` (case-insensitive), else ''."""
    lowered = {k.lower(): v for k, v in item.items()}
    for key in keys:
        value = lowered.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def parse_flashcards(raw: str) -> tuple[Flashcard, ...]:
    """Parse a model reply into validated flashcards.

    Accepts the common key spellings (``front``/``term``/``question`` and
    ``back``/``definition``/``answer``). Items missing either side are skipped; a
    reply yielding no usable card raises :class:`StudyToolParseError` so the route
    can return a clean 502 rather than an empty deck.
    """
    cards: list[Flashcard] = []
    for item in _extract_json_array(raw):
        if not isinstance(item, dict):
            continue
        front = _first_str(item, ("front", "term", "question", "q"))
        back = _first_str(item, ("back", "definition", "answer", "a"))
        if front and back:
            cards.append(Flashcard(front=front, back=back))

    if not cards:
        raise StudyToolParseError("no valid flashcards in model output")
    return tuple(cards)


def _coerce_correct_index(value, options: list[str]) -> int | None:
    """Resolve a model's answer field to a 0-based option index, or ``None``.

    Tolerates the three forms models actually emit: an integer index, a letter
    (``"A"``–``"D"`` / ``"a"``), or the full text of the correct option.
    """
    if isinstance(value, bool):  # bool is an int subclass — reject explicitly
        return None
    if isinstance(value, int):
        return value if 0 <= value < len(options) else None
    if isinstance(value, str):
        token = value.strip()
        if len(token) == 1 and token.upper().isalpha():
            idx = ord(token.upper()) - ord("A")
            return idx if 0 <= idx < len(options) else None
        if token.isdigit():
            idx = int(token)
            return idx if 0 <= idx < len(options) else None
        for i, opt in enumerate(options):
            if opt.strip() == token:
                return i
    return None


def parse_quiz(raw: str) -> tuple[QuizQuestion, ...]:
    """Parse a model reply into validated multiple-choice questions.

    Each kept question has a non-empty prompt, at least two string options, and a
    correct index that resolves into range (accepting int / letter / option-text
    answers). Malformed questions are skipped; an all-malformed reply raises
    :class:`StudyToolParseError`.
    """
    questions: list[QuizQuestion] = []
    for item in _extract_json_array(raw):
        if not isinstance(item, dict):
            continue
        prompt = _first_str(item, ("question", "prompt", "q"))
        lowered = {k.lower(): v for k, v in item.items()}
        raw_options = lowered.get("options") or lowered.get("choices") or lowered.get("answers")
        if not prompt or not isinstance(raw_options, list):
            continue
        options = [o.strip() for o in raw_options if isinstance(o, str) and o.strip()]
        if len(options) < 2:
            continue

        answer_value = None
        for key in ("correct_index", "correctindex", "answer_index", "answer", "correct", "correct_option"):
            if key in lowered:
                answer_value = lowered[key]
                break
        correct_index = _coerce_correct_index(answer_value, options)
        if correct_index is None:
            continue

        explanation = _first_str(item, ("explanation", "rationale", "reason", "izah"))
        questions.append(
            QuizQuestion(
                prompt=prompt,
                options=tuple(options),
                correct_index=correct_index,
                explanation=explanation,
            )
        )

    if not questions:
        raise StudyToolParseError("no valid quiz questions in model output")
    return tuple(questions)


# --- assembly --------------------------------------------------------------


def assemble_deck(*, slice_: TopicSlice, model: str, cards: tuple[Flashcard, ...]) -> FlashcardDeck:
    """Pair parsed cards with the slice's provenance for the response."""
    return FlashcardDeck(
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
        cards=cards,
    )


def assemble_quiz(*, slice_: TopicSlice, model: str, questions: tuple[QuizQuestion, ...]) -> Quiz:
    """Pair parsed questions with the slice's provenance for the response."""
    return Quiz(
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
        questions=questions,
    )
