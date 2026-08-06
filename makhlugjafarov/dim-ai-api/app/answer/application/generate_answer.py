"""
Answer application — generate_answer use-case.

Orchestration:
  1. If no chunks, return the standard weak-context fallback string.
  2. Resolve a PromptPolicy from the registry (subject, question_type, persona).
  3. Call policy.build_plan(..., tier_conflict=...) → PromptPlan.
  4. Detect provider from model name.
  5. Dispatch through the provider port (call_provider) with the plan's
     system_prompt and max_tokens.

This function is the CP1 seam that AskQuestionUseCase calls; its signature is
kept compatible with the old rag.generation.generate_answer.
"""
from __future__ import annotations

from app.answer.domain.errors import GenerationError  # noqa: F401 (re-exported)
from app.answer.domain.prompt_policy import (
    INSUFFICIENT_CONTEXT_MESSAGE,
    PromptPlan,
    get_registry,
)
from app.answer.domain.provider_policy import detect_provider
from app.answer.infrastructure.providers import call_provider
from app.retrieval.domain.context_packer import PackedContext
from app.retrieval.domain.query_intent import is_enumeration_intent

_ENUMERATION_ANSWER_SUFFIX = (
    "\n\n[Cavab formatı: bütün maddələri tam siyahı kimi yaz; hər maddəni yeni sətirdə ver; "
    "heç birini buraxma; sonda [N] sitatı əlavə et.]"
)


def generate_answer(
    *,
    question: str,
    context: PackedContext,
    api_key: str,
    model: str,
    history: list[dict[str, str]] | None = None,
    tier_conflict: bool = False,
    weak_context: bool = False,
    # Extension points for future policies (not activated in CP4)
    subject: str | None = None,
    question_type: str | None = None,
    persona: str | None = None,
) -> str:
    """
    Generate an LLM answer for a student question given packed retrieval context.

    ``weak_context`` (top retrieval score below the weak-context threshold) is
    threaded into the prompt policy so the model verifies relevance before
    answering — the live failure mode (GRO-111) was the BYOK path generating
    confidently from off-topic chunks because this signal was dropped here.
    """
    if not context.chunks:
        return INSUFFICIENT_CONTEXT_MESSAGE

    history = history or []

    # Step 1 — resolve policy
    registry = get_registry()
    policy = registry.resolve(subject, question_type, persona)

    # Step 2 — build plan
    plan: PromptPlan = policy.build_plan(
        subject=subject,
        question_type=question_type,
        persona=persona,
        tier_conflict=tier_conflict,
        weak_context=weak_context,
    )

    # Step 3 — detect provider
    provider = detect_provider(model)

    enumeration = is_enumeration_intent(question)
    question_for_llm = question
    if enumeration:
        question_for_llm = question + _ENUMERATION_ANSWER_SUFFIX

    # Step 4 — dispatch through provider port
    return call_provider(
        provider=provider,
        question=question_for_llm,
        context_text=context.text,
        api_key=api_key,
        model=model,
        history=history,
        system_prompt=plan.system_prompt,
        max_tokens=plan.max_tokens,
        enumeration=enumeration,
    )
