"""Generate structured study tools from a curriculum node — flashcards & quizzes.

The structured sibling of :mod:`app.curriculum.application.generate_lesson`. Same
backbone-becomes-fuel path (resolve a topic slice → grounded prompt → BYOK
provider port), but the reply is parsed into typed cards/questions the mobile app
renders as interactive widgets, not prose.

Provider dispatch is shared with the answer path (``ProviderPolicy`` +
``call_provider``) so credential handling and faithfulness stay identical;
``get_topic_slice`` and ``call_provider`` are imported at module level so route
tests can patch them hermetically.
"""

from __future__ import annotations

from app.answer.domain.provider_policy import ProviderPolicy
from app.answer.infrastructure.providers import call_provider
from app.curriculum.application.get_topic_slice import get_topic_slice
from app.curriculum.domain.lesson import EmptySliceError, LessonPromptSpec
from app.curriculum.domain.models import TopicSlice
from app.curriculum.domain.study_tools import (
    FlashcardDeck,
    Quiz,
    assemble_deck,
    assemble_quiz,
    build_flashcards_prompt,
    build_quiz_prompt,
    parse_flashcards,
    parse_quiz,
)


def _resolve_slice(
    *,
    database_url: str,
    subject: str | None,
    source_id: str | None,
    node_path: str | None,
    node_id: str | None,
    node_title: str | None,
    include_descendants: bool,
    include_blocks: bool,
    max_chars: int,
    max_blocks: int,
) -> TopicSlice:
    """Resolve a topic slice and refuse to generate from an empty one.

    Raises :class:`~app.curriculum.domain.models.TopicSliceError` (no book/node)
    or :class:`EmptySliceError` (no prose to ground on) — mirrors
    ``generate_lesson`` so the two paths fail identically.
    """
    slice_ = get_topic_slice(
        database_url=database_url,
        subject=subject,
        source_id=source_id,
        node_path=node_path,
        node_id=node_id,
        node_title=node_title,
        include_descendants=include_descendants,
        include_blocks=include_blocks,
        max_chars=max_chars,
        max_blocks=max_blocks,
    )
    if not slice_.content.strip() or slice_.chunk_count == 0:
        raise EmptySliceError(
            f"node {slice_.node.node_path!r} has no text to generate study tools from"
        )
    return slice_


def _generate_text(
    *, prompt: LessonPromptSpec, slice_: TopicSlice, provider: str, model: str, api_key: str
) -> str:
    """Validate the provider/model pair and dispatch the grounded generation.

    Raises :class:`~app.answer.domain.errors.GenerationError` on a provider/model
    mismatch or an upstream LLM failure.
    """
    canonical_provider = ProviderPolicy.validate(model, provider)
    return call_provider(
        provider=canonical_provider,
        question=prompt.instruction,
        context_text=slice_.content,
        api_key=api_key,
        model=model,
        history=[],
        system_prompt=prompt.system_prompt,
        max_tokens=prompt.max_tokens,
    )


def generate_flashcards(
    *,
    database_url: str,
    provider: str,
    model: str,
    api_key: str,
    count: int = 12,
    subject: str | None = None,
    source_id: str | None = None,
    node_path: str | None = None,
    node_id: str | None = None,
    node_title: str | None = None,
    include_descendants: bool = True,
    include_blocks: bool = True,
    max_chars: int = 12000,
    max_blocks: int = 40,
) -> FlashcardDeck:
    """Resolve a topic and generate a grounded, structured flashcard deck.

    Also raises :class:`~app.curriculum.domain.study_tools.StudyToolParseError`
    when the model's reply can't be parsed into usable cards.
    """
    slice_ = _resolve_slice(
        database_url=database_url, subject=subject, source_id=source_id,
        node_path=node_path, node_id=node_id, node_title=node_title,
        include_descendants=include_descendants, include_blocks=include_blocks,
        max_chars=max_chars, max_blocks=max_blocks,
    )
    prompt = build_flashcards_prompt(slice_, count=count)
    raw = _generate_text(prompt=prompt, slice_=slice_, provider=provider, model=model, api_key=api_key)
    cards = parse_flashcards(raw)
    return assemble_deck(slice_=slice_, model=model, cards=cards)


def generate_quiz(
    *,
    database_url: str,
    provider: str,
    model: str,
    api_key: str,
    count: int = 5,
    subject: str | None = None,
    source_id: str | None = None,
    node_path: str | None = None,
    node_id: str | None = None,
    node_title: str | None = None,
    include_descendants: bool = True,
    include_blocks: bool = True,
    max_chars: int = 12000,
    max_blocks: int = 40,
) -> Quiz:
    """Resolve a topic and generate a grounded, structured multiple-choice quiz.

    Also raises :class:`~app.curriculum.domain.study_tools.StudyToolParseError`
    when the model's reply can't be parsed into usable questions.
    """
    slice_ = _resolve_slice(
        database_url=database_url, subject=subject, source_id=source_id,
        node_path=node_path, node_id=node_id, node_title=node_title,
        include_descendants=include_descendants, include_blocks=include_blocks,
        max_chars=max_chars, max_blocks=max_blocks,
    )
    prompt = build_quiz_prompt(slice_, count=count)
    raw = _generate_text(prompt=prompt, slice_=slice_, provider=provider, model=model, api_key=api_key)
    questions = parse_quiz(raw)
    return assemble_quiz(slice_=slice_, model=model, questions=questions)
