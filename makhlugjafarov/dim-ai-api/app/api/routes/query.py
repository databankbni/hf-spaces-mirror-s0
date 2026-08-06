import json
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, SecretStr

from app.platform.config import Settings, get_settings
from app.identity.application.get_caller import get_optional_caller
from app.identity.domain.caller import CallerIdentity
from app.query.application.ask_question import (
    AskQuestionUseCase,
    QueryCommand,
    GenerationCommand,
    FilterCommand,
)

router = APIRouter(prefix="/api", tags=["query"])


class HistoryMessage(BaseModel):
    role: str
    content: str


class QueryFilters(BaseModel):
    grade: int | None = None
    subject: str | None = None
    bookId: str | None = None
    section: str | None = None
    limit: int | None = None


Provider = Literal["google", "openai", "anthropic"]


class GenerationRequest(BaseModel):
    provider: Provider
    model: str = Field(min_length=1, max_length=120)
    api_key: SecretStr = Field(min_length=1)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    history: list[HistoryMessage] = Field(default_factory=list)
    locale: str | None = None
    metadata: dict | None = None
    filters: QueryFilters | None = None
    subject: str | None = None
    questionType: str | None = Field(default=None, max_length=40)  # e.g. "mcq" (CP13)
    persona: str | None = Field(default=None, max_length=40)  # e.g. "coach" (CP13)
    generation: GenerationRequest | None = None


class CitationOut(BaseModel):
    chunkId: str
    page: int | None = None
    pageEnd: int | None = None
    source: str
    sourceId: str  # stable manifest document source_id (machine-stable citation key)
    excerpt: str
    sourceTier: int = 3  # 1=official_textbook … 5=student_telemetry
    sectionTitle: str | None = None


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    confidence: float | None = None
    responseTimeMs: int | None = None


def _map_request(request: QueryRequest, user_id: str | None = None) -> QueryCommand:
    generation_cmd = None
    if request.generation:
        generation_cmd = GenerationCommand(
            provider=request.generation.provider,
            model=request.generation.model,
            api_key=request.generation.api_key.get_secret_value(),
        )

    filter_cmd = None
    if request.filters:
        filter_cmd = FilterCommand(
            grade=request.filters.grade,
            subject=request.filters.subject,
            limit=request.filters.limit,
        )

    return QueryCommand(
        question=request.question,
        history=[{"role": m.role, "content": m.content} for m in request.history],
        locale=request.locale,
        filters=filter_cmd,
        subject=request.subject,
        generation=generation_cmd,
        user_id=user_id,
        question_type=request.questionType,
        persona=request.persona,
    )


@router.post("/query", response_model=QueryResponse)
def query(
    http_request: Request,
    request: QueryRequest,
    settings: Settings = Depends(get_settings),
    caller: CallerIdentity = Depends(get_optional_caller),
) -> QueryResponse:
    user_id = str(caller.user_id) if caller.user_id else None
    # Expose user_id on the ASGI scope so AccessLoggingMiddleware can read it.
    http_request.scope["user_id"] = user_id or "anonymous"

    command = _map_request(request, user_id=user_id)
    result = AskQuestionUseCase.execute(command, settings)

    return QueryResponse(
        answer=result.answer,
        citations=[
            CitationOut(
                chunkId=c.chunkId,
                page=c.page,
                pageEnd=c.pageEnd,
                source=c.source,
                sourceId=c.sourceId,
                excerpt=c.excerpt,
                sourceTier=c.sourceTier,
                sectionTitle=c.sectionTitle,
            ) for c in result.citations
        ],
        confidence=result.confidence,
        responseTimeMs=result.responseTimeMs,
    )


@router.post("/query/stream")
def query_stream(
    http_request: Request,
    request: QueryRequest,
    settings: Settings = Depends(get_settings),
    caller: CallerIdentity = Depends(get_optional_caller),
) -> StreamingResponse:
    user_id = str(caller.user_id) if caller.user_id else None
    http_request.scope["user_id"] = user_id or "anonymous"

    command = _map_request(request, user_id=user_id)
    result = AskQuestionUseCase.execute(command, settings)

    def _map_citations():
        return [
            {
                "chunkId": c.chunkId,
                "page": c.page,
                "pageEnd": c.pageEnd,
                "source": c.source,
                "sourceId": c.sourceId,
                "excerpt": c.excerpt,
                "sourceTier": c.sourceTier,
                "sectionTitle": c.sectionTitle,
            } for c in result.citations
        ]

    def event_stream():
        yield _stream_event(
            {
                "type": "metadata",
                "citations": _map_citations(),
                "confidence": result.confidence,
                "responseTimeMs": result.responseTimeMs,
            }
        )
        for chunk in _chunk_answer(result.answer):
            yield _stream_event({"type": "token", "text": chunk})
        yield _stream_event(
            {
                "type": "done",
                "answer": result.answer,
                "citations": _map_citations(),
                "confidence": result.confidence,
                "responseTimeMs": result.responseTimeMs,
            }
        )

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


def _chunk_answer(answer: str, max_chars: int = 80) -> list[str]:
    if len(answer) <= max_chars:
        return [answer]

    chunks: list[str] = []
    current = ""
    for word in answer.split(" "):
        candidate = f"{current} {word}" if current else word
        if len(candidate) > max_chars and current:
            chunks.append(current + " ")
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _stream_event(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"
