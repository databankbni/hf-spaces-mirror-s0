"""HTTP routes for the curriculum context (GRO-158).

The thin transport layer over the application orchestrators:

- ``GET  /api/curriculum/outline`` — navigate a book's curriculum tree.
- ``GET  /api/curriculum/slice``   — pull an LLM-ready topic slice.
- ``POST /api/curriculum/lesson``  — generate study content from a slice (BYOK).

This is where the stored TOC-spine tree (GRO-156) becomes consumable over HTTP —
both the read half of the apex intent (outline/slice) and its first pay-off
(lesson generation). All structure/assembly/generation lives in the application +
domain layers; this module only maps params in and dataclasses out, translating
:class:`TopicSliceError` / :class:`GenerationError` into honest HTTP status codes.
"""

from __future__ import annotations

from typing import Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, SecretStr

from app.answer.domain.errors import GenerationError
from app.answer.domain.provider_policy import ProviderPolicy
from app.curriculum.application.get_catalog import get_catalog
from app.curriculum.application.get_curriculum_outline import get_curriculum_outline
from app.curriculum.application.get_topic_slice import get_topic_slice
from app.curriculum.application.generate_lesson import generate_lesson
from app.curriculum.application.generate_study_tools import (
    generate_flashcards,
    generate_quiz,
)
from app.curriculum.domain.lesson import EmptySliceError, Lesson, LessonKind
from app.curriculum.domain.models import (
    BlockView,
    CatalogEntry,
    CurriculumOutline,
    NodeView,
    OutlineNode,
    TopicSlice,
    TopicSliceError,
)
from app.curriculum.domain.study_tools import (
    Flashcard,
    FlashcardDeck,
    Quiz,
    QuizQuestion,
    StudyToolParseError,
)
from app.platform.config import Settings, get_settings

router = APIRouter(prefix="/api/curriculum", tags=["curriculum"])


# --- Response models -------------------------------------------------------


class NodeOut(BaseModel):
    nodeId: str
    nodePath: str
    level: int
    title: str
    pageStart: int | None = None
    pageEnd: int | None = None

    @classmethod
    def of(cls, node: NodeView) -> "NodeOut":
        return cls(
            nodeId=node.node_id,
            nodePath=node.node_path,
            level=node.level,
            title=node.title,
            pageStart=node.page_start,
            pageEnd=node.page_end,
        )


class OutlineNodeOut(BaseModel):
    nodePath: str
    level: int
    title: str
    pageStart: int | None = None
    pageEnd: int | None = None
    chunkCount: int
    hasChildren: bool
    blockCount: int = 0

    @classmethod
    def of(cls, node: OutlineNode) -> "OutlineNodeOut":
        return cls(
            nodePath=node.node_path,
            level=node.level,
            title=node.title,
            pageStart=node.page_start,
            pageEnd=node.page_end,
            chunkCount=node.chunk_count,
            hasChildren=node.has_children,
            blockCount=node.block_count,
        )


class BlockOut(BaseModel):
    """A typed non-prose artefact for native rendering by the client."""

    kind: str
    nodePath: str
    page: int | None = None
    caption: str | None = None
    description: str | None = None
    markdown: str | None = None
    nRows: int | None = None
    nCols: int | None = None

    @classmethod
    def of(cls, block: BlockView) -> "BlockOut":
        return cls(
            kind=block.kind,
            nodePath=block.node_path,
            page=block.page,
            caption=block.caption,
            description=block.description,
            markdown=block.markdown,
            nRows=block.n_rows,
            nCols=block.n_cols,
        )


class CurriculumOutlineResponse(BaseModel):
    sourceId: str
    subject: str | None = None
    nodeCount: int
    maxDepth: int
    totalChunks: int
    taggedChunks: int
    nodes: list[OutlineNodeOut]
    rendered: str | None = None

    @classmethod
    def of(cls, outline: CurriculumOutline, *, include_rendered: bool) -> "CurriculumOutlineResponse":
        return cls(
            sourceId=outline.source_id,
            subject=outline.subject,
            nodeCount=outline.node_count,
            maxDepth=outline.max_depth,
            totalChunks=outline.total_chunks,
            taggedChunks=outline.tagged_chunks,
            nodes=[OutlineNodeOut.of(n) for n in outline.nodes],
            rendered=outline.render() if include_rendered else None,
        )


class CatalogEntryOut(BaseModel):
    sourceId: str
    title: str
    subject: str | None = None
    grade: int | None = None
    language: str | None = None
    sourceType: str | None = None
    nodeCount: int
    chunkCount: int
    browsable: bool

    @classmethod
    def of(cls, entry: CatalogEntry) -> "CatalogEntryOut":
        return cls(
            sourceId=entry.source_id,
            title=entry.title,
            subject=entry.subject,
            grade=entry.grade,
            language=entry.language,
            sourceType=entry.source_type,
            nodeCount=entry.node_count,
            chunkCount=entry.chunk_count,
            browsable=entry.browsable,
        )


class CatalogResponse(BaseModel):
    books: list[CatalogEntryOut]


class TopicSliceResponse(BaseModel):
    sourceId: str
    subject: str | None = None
    node: NodeOut
    breadcrumb: list[str]
    ancestors: list[NodeOut]
    descendants: list[NodeOut]
    pageStart: int | None = None
    pageEnd: int | None = None
    chunkCount: int
    content: str
    truncated: bool
    omittedNodePaths: list[str]
    blockCount: int = 0
    blocks: list[BlockOut] = []

    @classmethod
    def of(cls, slice_: TopicSlice) -> "TopicSliceResponse":
        return cls(
            sourceId=slice_.source_id,
            subject=slice_.subject,
            node=NodeOut.of(slice_.node),
            breadcrumb=list(slice_.breadcrumb),
            ancestors=[NodeOut.of(n) for n in slice_.ancestors],
            descendants=[NodeOut.of(n) for n in slice_.descendants],
            pageStart=slice_.page_start,
            pageEnd=slice_.page_end,
            chunkCount=slice_.chunk_count,
            content=slice_.content,
            truncated=slice_.truncated,
            omittedNodePaths=list(slice_.omitted_node_paths),
            blockCount=slice_.block_count,
            blocks=[BlockOut.of(b) for b in slice_.blocks],
        )


# --- Error mapping ---------------------------------------------------------


def _require_database_url(settings: Settings) -> str:
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="curriculum database is not configured")
    return settings.database_url


def _raise_for_slice_error(exc: TopicSliceError) -> NoReturn:
    """Translate a resolution failure into an honest HTTP status.

    Connection failures are infrastructure (503); an ambiguous subject is a
    caller-resolvable conflict (409); everything else is a missing book/node (404).
    """
    message = str(exc)
    if "database connection failed" in message:
        raise HTTPException(status_code=503, detail=message) from exc
    if "is ambiguous" in message:
        raise HTTPException(status_code=409, detail=message) from exc
    raise HTTPException(status_code=404, detail=message) from exc


# --- Routes ----------------------------------------------------------------


@router.get("/outline", response_model=CurriculumOutlineResponse)
def outline(
    subject: str | None = Query(default=None, description="canonical subject (aliases folded)"),
    source_id: str | None = Query(default=None, description="manifest document source_id (preferred)"),
    render: bool = Query(default=False, description="include an LLM-ready indented text outline"),
    settings: Settings = Depends(get_settings),
) -> CurriculumOutlineResponse:
    """Map a book's whole curriculum tree — the navigable syllabus a module reads."""
    if not (subject or source_id):
        raise HTTPException(status_code=400, detail="outline requires subject or source_id")
    database_url = _require_database_url(settings)
    try:
        result = get_curriculum_outline(
            database_url=database_url, subject=subject, source_id=source_id
        )
    except TopicSliceError as exc:
        _raise_for_slice_error(exc)
    return CurriculumOutlineResponse.of(result, include_rendered=render)


@router.get("/catalog", response_model=CatalogResponse)
def catalog(settings: Settings = Depends(get_settings)) -> CatalogResponse:
    """List every ingested book the app can study — the Home screen's source.

    Each entry says whether it is a browsable course (``hasCurriculum``) or an
    ask-only subject, so the client never offers an outline for a book with none.
    """
    database_url = _require_database_url(settings)
    try:
        entries = get_catalog(database_url=database_url)
    except TopicSliceError as exc:
        _raise_for_slice_error(exc)
    return CatalogResponse(books=[CatalogEntryOut.of(e) for e in entries])


@router.get("/slice", response_model=TopicSliceResponse)
def slice_(
    subject: str | None = Query(default=None, description="canonical subject (aliases folded)"),
    source_id: str | None = Query(default=None, description="manifest document source_id (preferred)"),
    node_path: str | None = Query(default=None, description="dotted node path, e.g. '1.4.1'"),
    node_id: str | None = Query(default=None, description="curriculum node uuid"),
    node_title: str | None = Query(default=None, description="topic title (diacritic/case-folded)"),
    include_descendants: bool = Query(default=True, description="fold the subtree's text into content"),
    include_blocks: bool = Query(default=True, description="append attached tables/figures/formulas"),
    max_chars: int = Query(default=12000, ge=500, le=200000, description="content size budget"),
    max_blocks: int = Query(default=40, ge=0, le=500, description="max typed blocks to include"),
    settings: Settings = Depends(get_settings),
) -> TopicSliceResponse:
    """Resolve one topic to an LLM-ready slice: breadcrumb + subtree + prose + blocks."""
    if not (subject or source_id):
        raise HTTPException(status_code=400, detail="slice requires subject or source_id")
    if not (node_path or node_id or node_title):
        raise HTTPException(
            status_code=400, detail="slice requires node_path, node_id, or node_title"
        )
    database_url = _require_database_url(settings)
    try:
        result = get_topic_slice(
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
    except TopicSliceError as exc:
        _raise_for_slice_error(exc)
    return TopicSliceResponse.of(result)


# --- lesson (content generation) -------------------------------------------

Provider = Literal["google", "openai", "anthropic"]


class GenerationRequest(BaseModel):
    provider: Provider
    model: str = Field(min_length=1, max_length=120)
    api_key: SecretStr = Field(min_length=1)


class LessonRequest(BaseModel):
    subject: str | None = None
    sourceId: str | None = None
    nodePath: str | None = None
    nodeId: str | None = None
    nodeTitle: str | None = None
    kind: LessonKind = "summary"
    includeDescendants: bool = True
    includeBlocks: bool = True
    maxChars: int = Field(default=12000, ge=500, le=200000)
    maxBlocks: int = Field(default=40, ge=0, le=500)
    generation: GenerationRequest


class LessonResponse(BaseModel):
    kind: LessonKind
    sourceId: str
    subject: str | None = None
    nodePath: str
    nodeTitle: str
    breadcrumb: list[str]
    pageStart: int | None = None
    pageEnd: int | None = None
    groundedChunkCount: int
    groundedBlockCount: int = 0
    contextTruncated: bool
    model: str
    content: str

    @classmethod
    def of(cls, lesson: Lesson) -> "LessonResponse":
        return cls(
            kind=lesson.kind,
            sourceId=lesson.source_id,
            subject=lesson.subject,
            nodePath=lesson.node_path,
            nodeTitle=lesson.node_title,
            breadcrumb=list(lesson.breadcrumb),
            pageStart=lesson.page_start,
            pageEnd=lesson.page_end,
            groundedChunkCount=lesson.grounded_chunk_count,
            groundedBlockCount=lesson.grounded_block_count,
            contextTruncated=lesson.context_truncated,
            model=lesson.model,
            content=lesson.content,
        )


@router.post("/lesson", response_model=LessonResponse)
def lesson(
    request: LessonRequest,
    settings: Settings = Depends(get_settings),
) -> LessonResponse:
    """Generate study content for one curriculum node, grounded in its slice.

    ``kind`` selects what to produce (summary / key_points / quiz); generation
    uses the caller's own BYOK key. The node's slice text is the only source the
    model is given, so the output stays grounded in the book.
    """
    if not (request.subject or request.sourceId):
        raise HTTPException(status_code=400, detail="lesson requires subject or sourceId")
    if not (request.nodePath or request.nodeId or request.nodeTitle):
        raise HTTPException(
            status_code=400, detail="lesson requires nodePath, nodeId, or nodeTitle"
        )
    database_url = _require_database_url(settings)

    # Reject a provider/model mismatch up front (400) so a real GenerationError
    # escaping the use-case can only be an upstream provider failure (502).
    try:
        ProviderPolicy.validate(request.generation.model, request.generation.provider)
    except GenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        result = generate_lesson(
            database_url=database_url,
            kind=request.kind,
            provider=request.generation.provider,
            model=request.generation.model,
            api_key=request.generation.api_key.get_secret_value(),
            subject=request.subject,
            source_id=request.sourceId,
            node_path=request.nodePath,
            node_id=request.nodeId,
            node_title=request.nodeTitle,
            include_descendants=request.includeDescendants,
            include_blocks=request.includeBlocks,
            max_chars=request.maxChars,
            max_blocks=request.maxBlocks,
        )
    except TopicSliceError as exc:
        _raise_for_slice_error(exc)
    except EmptySliceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return LessonResponse.of(result)


# --- study tools (structured flashcards & quizzes) -------------------------


def _validate_study_request(
    *,
    subject: str | None,
    source_id: str | None,
    node_path: str | None,
    node_id: str | None,
    node_title: str | None,
    generation: "GenerationRequest",
    what: str,
) -> None:
    """Shared 400-guards for the structured generation routes.

    Asserts a book + node selector are present and that the provider matches the
    model prefix, so a ``GenerationError`` later can only be an upstream failure.
    """
    if not (subject or source_id):
        raise HTTPException(status_code=400, detail=f"{what} requires subject or sourceId")
    if not (node_path or node_id or node_title):
        raise HTTPException(
            status_code=400, detail=f"{what} requires nodePath, nodeId, or nodeTitle"
        )
    try:
        ProviderPolicy.validate(generation.model, generation.provider)
    except GenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class FlashcardsRequest(BaseModel):
    subject: str | None = None
    sourceId: str | None = None
    nodePath: str | None = None
    nodeId: str | None = None
    nodeTitle: str | None = None
    count: int = Field(default=12, ge=1, le=40)
    includeDescendants: bool = True
    includeBlocks: bool = True
    maxChars: int = Field(default=12000, ge=500, le=200000)
    maxBlocks: int = Field(default=40, ge=0, le=500)
    generation: GenerationRequest


class FlashcardOut(BaseModel):
    front: str
    back: str

    @classmethod
    def of(cls, card: Flashcard) -> "FlashcardOut":
        return cls(front=card.front, back=card.back)


class FlashcardsResponse(BaseModel):
    sourceId: str
    subject: str | None = None
    nodePath: str
    nodeTitle: str
    breadcrumb: list[str]
    pageStart: int | None = None
    pageEnd: int | None = None
    groundedChunkCount: int
    groundedBlockCount: int = 0
    contextTruncated: bool
    model: str
    cardCount: int
    cards: list[FlashcardOut]

    @classmethod
    def of(cls, deck: FlashcardDeck) -> "FlashcardsResponse":
        return cls(
            sourceId=deck.source_id,
            subject=deck.subject,
            nodePath=deck.node_path,
            nodeTitle=deck.node_title,
            breadcrumb=list(deck.breadcrumb),
            pageStart=deck.page_start,
            pageEnd=deck.page_end,
            groundedChunkCount=deck.grounded_chunk_count,
            groundedBlockCount=deck.grounded_block_count,
            contextTruncated=deck.context_truncated,
            model=deck.model,
            cardCount=len(deck.cards),
            cards=[FlashcardOut.of(c) for c in deck.cards],
        )


class QuizRequest(BaseModel):
    subject: str | None = None
    sourceId: str | None = None
    nodePath: str | None = None
    nodeId: str | None = None
    nodeTitle: str | None = None
    count: int = Field(default=5, ge=1, le=20)
    includeDescendants: bool = True
    includeBlocks: bool = True
    maxChars: int = Field(default=12000, ge=500, le=200000)
    maxBlocks: int = Field(default=40, ge=0, le=500)
    generation: GenerationRequest


class QuizQuestionOut(BaseModel):
    prompt: str
    options: list[str]
    correctIndex: int
    explanation: str

    @classmethod
    def of(cls, q: QuizQuestion) -> "QuizQuestionOut":
        return cls(
            prompt=q.prompt,
            options=list(q.options),
            correctIndex=q.correct_index,
            explanation=q.explanation,
        )


class QuizResponse(BaseModel):
    sourceId: str
    subject: str | None = None
    nodePath: str
    nodeTitle: str
    breadcrumb: list[str]
    pageStart: int | None = None
    pageEnd: int | None = None
    groundedChunkCount: int
    groundedBlockCount: int = 0
    contextTruncated: bool
    model: str
    questionCount: int
    questions: list[QuizQuestionOut]

    @classmethod
    def of(cls, quiz: Quiz) -> "QuizResponse":
        return cls(
            sourceId=quiz.source_id,
            subject=quiz.subject,
            nodePath=quiz.node_path,
            nodeTitle=quiz.node_title,
            breadcrumb=list(quiz.breadcrumb),
            pageStart=quiz.page_start,
            pageEnd=quiz.page_end,
            groundedChunkCount=quiz.grounded_chunk_count,
            groundedBlockCount=quiz.grounded_block_count,
            contextTruncated=quiz.context_truncated,
            model=quiz.model,
            questionCount=len(quiz.questions),
            questions=[QuizQuestionOut.of(q) for q in quiz.questions],
        )


@router.post("/flashcards", response_model=FlashcardsResponse)
def flashcards(
    request: FlashcardsRequest,
    settings: Settings = Depends(get_settings),
) -> FlashcardsResponse:
    """Generate a structured, grounded flashcard deck for one curriculum node.

    The reply is parsed into validated cards; a model that returns unusable JSON
    surfaces as a 502 so the client can retry rather than render a broken deck.
    """
    _validate_study_request(
        subject=request.subject, source_id=request.sourceId,
        node_path=request.nodePath, node_id=request.nodeId, node_title=request.nodeTitle,
        generation=request.generation, what="flashcards",
    )
    database_url = _require_database_url(settings)

    try:
        deck = generate_flashcards(
            database_url=database_url,
            provider=request.generation.provider,
            model=request.generation.model,
            api_key=request.generation.api_key.get_secret_value(),
            count=request.count,
            subject=request.subject,
            source_id=request.sourceId,
            node_path=request.nodePath,
            node_id=request.nodeId,
            node_title=request.nodeTitle,
            include_descendants=request.includeDescendants,
            include_blocks=request.includeBlocks,
            max_chars=request.maxChars,
            max_blocks=request.maxBlocks,
        )
    except TopicSliceError as exc:
        _raise_for_slice_error(exc)
    except EmptySliceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except StudyToolParseError as exc:
        raise HTTPException(
            status_code=502, detail=f"could not build flashcards from model output: {exc}"
        ) from exc
    except GenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return FlashcardsResponse.of(deck)


@router.post("/quiz", response_model=QuizResponse)
def quiz(
    request: QuizRequest,
    settings: Settings = Depends(get_settings),
) -> QuizResponse:
    """Generate a structured, grounded multiple-choice quiz for one node.

    Each question carries its options, a resolved correct index, and a rationale;
    unusable model output surfaces as a 502.
    """
    _validate_study_request(
        subject=request.subject, source_id=request.sourceId,
        node_path=request.nodePath, node_id=request.nodeId, node_title=request.nodeTitle,
        generation=request.generation, what="quiz",
    )
    database_url = _require_database_url(settings)

    try:
        result = generate_quiz(
            database_url=database_url,
            provider=request.generation.provider,
            model=request.generation.model,
            api_key=request.generation.api_key.get_secret_value(),
            count=request.count,
            subject=request.subject,
            source_id=request.sourceId,
            node_path=request.nodePath,
            node_id=request.nodeId,
            node_title=request.nodeTitle,
            include_descendants=request.includeDescendants,
            include_blocks=request.includeBlocks,
            max_chars=request.maxChars,
            max_blocks=request.maxBlocks,
        )
    except TopicSliceError as exc:
        _raise_for_slice_error(exc)
    except EmptySliceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except StudyToolParseError as exc:
        raise HTTPException(
            status_code=502, detail=f"could not build quiz from model output: {exc}"
        ) from exc
    except GenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return QuizResponse.of(result)
