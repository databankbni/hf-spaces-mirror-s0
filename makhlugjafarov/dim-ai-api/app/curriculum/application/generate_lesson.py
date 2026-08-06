"""Generate study content from a curriculum node (GRO-158, utilise half).

The end-to-end "backbone becomes fuel" path: resolve a topic slice from the
stored TOC-spine tree, build a grounded prompt, and dispatch it through the same
BYOK provider port the answer path uses. Keeping the provider dispatch shared
(``ProviderPolicy`` + ``call_provider``) means content generation inherits the
faithfulness/credential handling already proven for answers.
"""

from __future__ import annotations

from app.answer.domain.provider_policy import ProviderPolicy
from app.answer.infrastructure.providers import call_provider
from app.curriculum.application.get_topic_slice import get_topic_slice
from app.curriculum.domain.lesson import (
    EmptySliceError,
    Lesson,
    LessonKind,
    assemble_lesson,
    build_lesson_prompt,
)


def generate_lesson(
    *,
    database_url: str,
    kind: LessonKind,
    provider: str,
    model: str,
    api_key: str,
    subject: str | None = None,
    source_id: str | None = None,
    node_path: str | None = None,
    node_id: str | None = None,
    node_title: str | None = None,
    include_descendants: bool = True,
    include_blocks: bool = True,
    max_chars: int = 12000,
    max_blocks: int = 40,
) -> Lesson:
    """Resolve a topic slice and generate ``kind`` content grounded in it.

    Raises :class:`~app.curriculum.domain.models.TopicSliceError` if the book/node
    can't be resolved, :class:`EmptySliceError` if the node has no prose to ground
    on, and :class:`~app.answer.domain.errors.GenerationError` on a provider/model
    mismatch or upstream LLM failure.
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
            f"node {slice_.node.node_path!r} has no text to generate content from"
        )

    prompt = build_lesson_prompt(kind, slice_)
    canonical_provider = ProviderPolicy.validate(model, provider)

    content = call_provider(
        provider=canonical_provider,
        question=prompt.instruction,
        context_text=slice_.content,
        api_key=api_key,
        model=model,
        history=[],
        system_prompt=prompt.system_prompt,
        max_tokens=prompt.max_tokens,
    )

    return assemble_lesson(kind=kind, slice_=slice_, model=model, content=content)
