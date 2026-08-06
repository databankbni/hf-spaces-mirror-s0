from pydantic import BaseModel, Field

from app.ingest.models import Chunk, IngestionWarning, ParsedDocument


class IngestionReport(BaseModel):
    corpus_version: str
    dry_run: bool
    documents_total: int = 0
    pages_total: int = 0
    chunks_created: int = 0
    duplicate_chunks_skipped: int = 0
    warnings: list[IngestionWarning] = Field(default_factory=list)


def build_report(
    *,
    corpus_version: str,
    dry_run: bool,
    documents: list[ParsedDocument],
    chunks_by_source: dict[str, list[Chunk]],
    duplicate_chunks_skipped: int = 0,
) -> IngestionReport:
    return IngestionReport(
        corpus_version=corpus_version,
        dry_run=dry_run,
        documents_total=len(documents),
        pages_total=sum(len(document.pages) for document in documents),
        chunks_created=sum(len(chunks) for chunks in chunks_by_source.values()),
        duplicate_chunks_skipped=duplicate_chunks_skipped,
        warnings=[warning for document in documents for warning in document.warnings],
    )
