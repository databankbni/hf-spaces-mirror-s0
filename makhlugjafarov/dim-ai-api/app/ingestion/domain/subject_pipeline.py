"""
SubjectPipeline — per-subject Strategy for the corpus/RAG stages (GRO-78 CP6).

A SubjectPipeline is the single, explicit owner of how one subject moves through
the content stages:

    parse -> segment -> enrich   (+ a declared content_contract and prompt-policy)

It replaces ad-hoc ``if subject == ...`` branching with a registry-selected
Strategy (resolves P3/P10/P13 from 01_DIAGNOSE.md).

## Design notes (read before extending)

* **Behaviour-preserving by construction.** ``BaseSubjectPipeline`` *delegates* to
  the existing stage functions (``parse_source``, ``chunk_pages_with_stats``) and
  the CP4 ``PromptPolicyRegistry``. The concrete History/Geography/Math pipelines
  override **nothing** behavioural today — they only declare their ``subject`` and
  ``content_contract``. So selecting a pipeline cannot change retrieval/ingestion
  output (the CP6 eval gate). Subject-specific overrides arrive later:
  CP7 gives ``MathPipeline`` its JSON parse path; CP13 registers math/MCQ/persona
  prompt policies.

* **Scope.** This pipeline owns the *content-shaping* stages (parse/segment/enrich),
  the ``content_contract``, and *prompt-policy selection*. ``embed`` and ``retrieve``
  stay with their current infra owners (the loader and the retrieval context) and
  remain subject-agnostic — subject flows to retrieval through the existing
  ``RetrievalFilters(subject=...)``. Keeping infra out of this domain object
  preserves the dependency direction (domain depends on no SDK/DB).

* **enrich** is an identity step today (a declared seam for future formula/figure/
  table enrichment); it returns the chunks unchanged.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.answer.domain.prompt_policy import PromptPolicy, get_registry
from app.ingest.chunker import ChunkingResult, chunk_pages_with_stats
from app.ingest.models import Chunk, ManifestSource, ParsedDocument
from app.ingest.parser import parse_source
from app.ingestion.domain.content_contract import (
    LATEX_CONTRACT,
    PROSE_CONTRACT,
    ContentContract,
)

# Canonical subject identifiers (must match data/books/manifest.yaml `subject:`).
SubjectId = str

SUBJECT_HISTORY: SubjectId = "azerbaycan_tarixi"
SUBJECT_GEOGRAPHY: SubjectId = "geography"
SUBJECT_MATH: SubjectId = "mathematics"


@runtime_checkable
class SubjectPipeline(Protocol):
    """Structural contract for a subject's content pipeline.

    Any object exposing ``subject`` + ``content_contract`` and the stage methods
    qualifies — no inheritance required.
    """

    subject: SubjectId
    content_contract: ContentContract

    def parse(self, source: ManifestSource) -> ParsedDocument: ...
    def segment(self, document: ParsedDocument) -> ChunkingResult: ...
    def enrich(self, chunks: list[Chunk]) -> list[Chunk]: ...
    def prompt_policy(
        self, *, question_type: str | None = None, persona: str | None = None
    ) -> PromptPolicy: ...


class BaseSubjectPipeline:
    """Default pipeline — shared stages, no subject-specific overrides.

    Delegates every stage to the existing implementation, so it is byte-equivalent
    to today's behaviour. Subjects subclass this only to declare their identity and
    content contract (and, later, to override a specific stage).
    """

    subject: SubjectId = "default"
    content_contract: ContentContract = PROSE_CONTRACT

    def parse(self, source: ManifestSource) -> ParsedDocument:
        return parse_source(source)

    def segment(self, document: ParsedDocument) -> ChunkingResult:
        return chunk_pages_with_stats(document.source, document.pages)

    def enrich(self, chunks: list[Chunk]) -> list[Chunk]:
        # Identity today; seam for future formula/figure/table enrichment.
        return list(chunks)

    def prompt_policy(
        self, *, question_type: str | None = None, persona: str | None = None
    ) -> PromptPolicy:
        # Subject-aware policy selection via the CP4 registry (single source of truth).
        return get_registry().resolve(self.subject, question_type, persona)


class HistoryPipeline(BaseSubjectPipeline):
    subject = SUBJECT_HISTORY
    content_contract = PROSE_CONTRACT


class GeographyPipeline(BaseSubjectPipeline):
    subject = SUBJECT_GEOGRAPHY
    content_contract = PROSE_CONTRACT


class MathPipeline(BaseSubjectPipeline):
    # Math is the only subject with a non-prose contract today: chunks carry LaTeX
    # that must be preserved verbatim and KaTeX-rendered. The parse override (the
    # GOT-OCR JSON path) arrives in CP7; the math prompt-policy in CP13.
    subject = SUBJECT_MATH
    content_contract = LATEX_CONTRACT

    def parse(self, source: ManifestSource) -> ParsedDocument:
        if source.parser.json_artifact_path is not None:
            path = source.parser.json_artifact_path
            if not path.is_absolute():
                # Resolve relative to the source file's parent dir
                path = source.path.parent / path
            if path.exists():
                from app.ingest.pages_json import parsed_document_from_pages_json
                return parsed_document_from_pages_json(source, path)
        # Fallback: in-process GOT-OCR (GPU-heavy; logs a warning so it's visible)
        import logging
        logging.getLogger(__name__).warning(
            "MathPipeline.parse: no json_artifact_path configured or file not found for "
            "source=%s; falling back to in-process GOT-OCR (requires GPU).",
            source.source_id,
        )
        return super().parse(source)


class SubjectPipelineRegistry:
    """Resolves a subject id to its SubjectPipeline, with a safe default.

    Open/Closed: adding a subject is a single ``register(...)`` call — no edits to
    the loader or any route. Unknown subjects fall back to ``BaseSubjectPipeline``
    (prose), so an unmapped subject degrades gracefully rather than raising.
    """

    def __init__(self) -> None:
        self._by_subject: dict[SubjectId, SubjectPipeline] = {}
        self._default: SubjectPipeline = BaseSubjectPipeline()

    def register(self, pipeline: SubjectPipeline) -> None:
        self._by_subject[pipeline.subject] = pipeline

    def resolve(self, subject: SubjectId | None) -> SubjectPipeline:
        if subject is None:
            return self._default
        return self._by_subject.get(subject, self._default)

    def known_subjects(self) -> list[SubjectId]:
        return sorted(self._by_subject.keys())


def _build_default_registry() -> SubjectPipelineRegistry:
    registry = SubjectPipelineRegistry()
    registry.register(HistoryPipeline())
    registry.register(GeographyPipeline())
    registry.register(MathPipeline())
    return registry


_registry = _build_default_registry()


def get_subject_pipeline_registry() -> SubjectPipelineRegistry:
    """Return the shared SubjectPipeline registry (module-level singleton)."""
    return _registry
