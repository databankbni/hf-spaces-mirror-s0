from time import perf_counter
from dataclasses import dataclass
from fastapi import HTTPException
from app.platform.config import Settings
from app.platform.embeddings import EmbeddingError, get_bge_m3_embedder
from app.retrieval.domain.models import RetrievalFilters, RetrievalError
from app.answer.domain.errors import GenerationError
from app.retrieval.application.retrieve_context import retrieve_context
import psycopg
from app.retrieval.infrastructure.traces import store_interaction
from app.retrieval.domain.context_packer import _pack_context
from app.answer.application.generate_answer import generate_answer
from app.answer.domain.prompt_policy import INSUFFICIENT_CONTEXT_MESSAGE
from app.answer.domain.provider_policy import detect_provider
from app.query.domain.subject_selector import (
    SubjectSelector,
    canonical_subject,
    retrieval_subject,
    retrieval_top_k,
)
from app.platform.observability.query_trace import QueryTrace

@dataclass
class GenerationCommand:
    provider: str
    model: str
    api_key: str

@dataclass
class FilterCommand:
    grade: int | None
    subject: str | None
    limit: int | None

@dataclass
class QueryCommand:
    question: str
    history: list[dict]
    locale: str | None
    filters: FilterCommand | None
    subject: str | None
    generation: GenerationCommand | None
    user_id: str | None = None  # JWT-derived caller identity (None = anonymous)
    question_type: str | None = None  # e.g. "mcq" — selects a prompt policy (CP13)
    persona: str | None = None  # e.g. "coach" — selects a prompt policy (CP13)

@dataclass
class CitationResult:
    chunkId: str
    page: int | None
    source: str
    sourceId: str
    excerpt: str
    sourceTier: int
    # Section fields — None for orphan chunks (section_block_id IS NULL).
    # FE must fall back to `page` citation when these are absent.
    pageEnd: int | None = None
    sectionTitle: str | None = None

@dataclass
class QueryResult:
    answer: str
    citations: list[CitationResult]
    confidence: float | None
    responseTimeMs: int | None

class AskQuestionUseCase:
    @staticmethod
    def _resolve_generation_credentials(command: QueryCommand, settings: Settings) -> tuple[str, str] | None:
        if command.generation:
            try:
                detected_provider = detect_provider(command.generation.model)
            except GenerationError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            if detected_provider != command.generation.provider:
                raise HTTPException(
                    status_code=400,
                    detail=f"Selected provider does not match model prefix; detected {detected_provider}.",
                )
            return command.generation.api_key, command.generation.model

        try:
            provider = detect_provider(settings.default_llm_model)
        except GenerationError:
            return None
        key_map = {
            "google": settings.gemini_api_key,
            "anthropic": settings.anthropic_api_key,
            "openai": settings.openai_api_key,
        }
        secret = key_map.get(provider)
        return (secret.get_secret_value(), settings.default_llm_model) if secret else None

    @staticmethod
    def execute(command: QueryCommand, settings: Settings) -> QueryResult:
        if not settings.database_url:
            raise HTTPException(status_code=503, detail="Database is not configured")

        generation_credentials = AskQuestionUseCase._resolve_generation_credentials(command, settings)

        started = perf_counter()

        subject_selection = SubjectSelector.from_request(command.subject, command.filters)
        language = command.locale or "az"
        # Canonical subject id for the DB filter: the corpus stores canonical ids
        # (``mathematics``, not the ``riyaziyyat`` alias), so an aliased request
        # must be normalised here or ``c.subject = %s`` matches zero rows (GRO-146).
        retrieval_subject_id = retrieval_subject(subject_selection.subject)

        try:
            retrieve_start = perf_counter()
            result = retrieve_context(
                database_url=settings.database_url,
                query=command.question,
                embedder=get_bge_m3_embedder(),
                filters=RetrievalFilters(subject=retrieval_subject_id, grade=subject_selection.grade, language=language),
                mode="subject_tutor" if retrieval_subject_id else "dim_coach",
                top_k=command.filters.limit if (command.filters and command.filters.limit) else retrieval_top_k(subject_selection.subject),
            )
            retrieve_ms = int((perf_counter() - retrieve_start) * 1000)
        except (EmbeddingError, RetrievalError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        # GRO-217 (S2): retrieval packs the context exactly once and hands it back
        # on the result. Reuse it here — the previous second `_pack_context` call
        # was a redundant re-pack over already-packed chunks. The fallback only
        # fires for results assembled without packing (e.g. in tests).
        pack_start = perf_counter()
        context = result.packed if result.packed is not None else _pack_context(
            result.chunks, max_chars=12000
        )
        pack_ms = int((perf_counter() - pack_start) * 1000)

        generate_ms = 0
        used_provider = None
        used_model = None

        if generation_credentials:
            api_key, model = generation_credentials
            used_provider = detect_provider(model)  # Re-detect for logging
            used_model = model
            try:
                gen_start = perf_counter()
                answer = generate_answer(
                    question=command.question,
                    context=context,
                    api_key=api_key,
                    model=model,
                    history=command.history,
                    tier_conflict=result.tier_conflict,
                    # GRO-111: thread the weak-context signal into the live (BYOK)
                    # path. Previously the guardrail only gated the keyless branch,
                    # so the real product generated confidently from off-topic chunks.
                    weak_context=result.weak_context,
                    # Prompt-policy selection: canonicalised so frontend aliases
                    # ("math") activate the right policy. Retrieval above uses the
                    # same canonical id (retrieval_subject_id) — both now agree.
                    subject=canonical_subject(subject_selection.subject),
                    question_type=command.question_type,
                    persona=command.persona,
                )
                generate_ms = int((perf_counter() - gen_start) * 1000)
            except GenerationError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
        else:
            if result.weak_context or not context.chunks:
                answer = INSUFFICIENT_CONTEXT_MESSAGE
            else:
                pages = ", ".join(str(c.citation.page_start) for c in context.chunks[:3])
                answer = (
                    f"Dərslikdə bu suala uyğun parçalar tapıldı (səh. {pages}). "
                    "Tam cavab üçün LLM API açarı tələb olunur."
                )

        citations = [
            CitationResult(
                chunkId=chunk.chunk_id,
                page=chunk.citation.page_start,
                pageEnd=chunk.citation.page_end if chunk.citation.page_end != chunk.citation.page_start else None,
                source=chunk.citation.citation_label,
                sourceId=chunk.citation.source_id,
                excerpt=chunk.content.strip()[:500],
                sourceTier=chunk.citation.source_tier,
                sectionTitle=chunk.citation.section_title,
            )
            for chunk in context.chunks
        ]

        elapsed_ms = int((perf_counter() - started) * 1000)
        top_score = context.chunks[0].score if context.chunks else 0.0

        QueryTrace(
            question=command.question,
            retrieve_ms=retrieve_ms,
            pack_ms=pack_ms,
            generate_ms=generate_ms,
            total_ms=elapsed_ms,
            top_score=top_score,
            chunk_ids=[c.chunk_id for c in context.chunks],
            tier_conflict=result.tier_conflict,
            confidence=round(top_score, 4) if context.chunks else None,
            provider=used_provider,
            model=used_model,
            weak_context=result.weak_context,
            user_id=command.user_id,
            context_truncated=context.truncated,
            truncated_chunk_ids=list(context.truncated_chunk_ids),
            dropped_chunk_ids=list(context.dropped_chunk_ids),
        ).emit()

        try:
            with psycopg.connect(settings.database_url, connect_timeout=5) as conn:
                store_interaction(
                    conn,
                    user_id=command.user_id,
                    conversation_id=None,
                    query=command.question,
                    mode="subject_tutor",
                    query_embedding_model_id=result.query_embedding_model_id,
                    filters=result.filters,
                    candidates=result.candidates,
                    selected=context.chunks,
                    weak_context=result.weak_context,
                    filters_relaxed=result.filters_relaxed,
                    confidence=round(top_score, 4) if context.chunks else None,
                    answer=answer,
                    provider=used_provider,
                    model=used_model,
                    latency_retrieve_ms=retrieve_ms,
                    latency_pack_ms=pack_ms,
                    latency_generate_ms=generate_ms,
                    latency_total_ms=elapsed_ms,
                )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Failed to store interaction telemetry: %s", exc)

        return QueryResult(
            answer=answer,
            citations=citations,
            confidence=round(top_score, 4) if context.chunks else None,
            responseTimeMs=elapsed_ms,
        )
