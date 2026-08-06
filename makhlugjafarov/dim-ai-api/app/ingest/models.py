from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SourceType = Literal["pdf", "txt"]
LegalStatus = Literal[
    "public_official",
    "licensed",
    "owned",
    "permission_requested",
    "permission_granted",
    "demo_only",
    "do_not_ingest",
    "TBD",
]

# 1 = official textbook / DİM rules (highest authority)
# 2 = DİM practice sources / Abituriyent
# 3 = licensed supplementary pedagogy (default)
# 4 = teacher annotations
# 5 = student-generated content
SourceTier = Literal[1, 2, 3, 4, 5]

ReviewStatus = Literal["pending", "reviewed", "approved", "flagged"]


class ParserConfig(BaseModel):
    primary: str = "auto"
    text_extraction: str = "auto"
    json_artifact_path: Path | None = None


class OcrConfig(BaseModel):
    enabled: bool | Literal["auto"] = "auto"
    engine: str = "ocrmypdf-tesseract"
    languages: list[str] = Field(default_factory=lambda: ["aze", "eng", "rus"])


class ExpectedConfig(BaseModel):
    page_count: int | None = Field(default=None, ge=1)
    min_text_coverage_ratio: float | None = Field(default=None, ge=0, le=1)


class ManifestSource(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_id: str = Field(alias="id", min_length=1)
    title: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    grade: int | None = Field(default=None, ge=5, le=11)
    language: str = Field(default="az", min_length=2, max_length=8)
    curriculum: str = "DIM"
    source_type: SourceType
    source_category: str = Field(min_length=1)
    path: Path
    legal_status: LegalStatus
    source_tier: SourceTier = 3
    review_status: ReviewStatus = "pending"
    owner: str | None = None
    publisher: str | None = None
    source_version: str = Field(min_length=1)
    citation_label: str = Field(min_length=1)
    source_uri: str | None = None
    # PDF page index → printed (book) page number. printed = pdf_index - page_offset.
    # Front matter (cover/anthem/contents) makes the PDF index run ahead of the
    # page number printed on the page; we cite what the student actually flips to.
    page_offset: int = Field(default=0, ge=0)
    parser: ParserConfig = Field(default_factory=ParserConfig)
    ocr: OcrConfig = Field(default_factory=OcrConfig)
    expected: ExpectedConfig = Field(default_factory=ExpectedConfig)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def tier_consistent_with_legal_status(self) -> "ManifestSource":
        # official textbooks must be tier 1 or 2; warn-worthy combinations are caught at ingest
        if self.legal_status == "public_official" and self.source_tier > 2:
            raise ValueError(
                f"source_id={self.source_id!r}: legal_status='public_official' expects source_tier "
                f"1 or 2, got {self.source_tier}. Official sources must rank highest."
            )
        return self

    @field_validator("source_id")
    @classmethod
    def source_id_must_be_stable(cls, value: str) -> str:
        if any(char.isspace() for char in value):
            raise ValueError("source id must not contain whitespace")
        return value


class CorpusManifest(BaseModel):
    corpus_version: str = Field(min_length=1)
    default_language: str = "az"
    embedding_policy_id: str = "bge-m3-dim-v1"
    chunking_policy_id: str = "dim-page-section-v1"
    sources: list[ManifestSource] = Field(min_length=1)


class ParsedPage(BaseModel):
    page_number: int = Field(ge=1)
    text: str
    ocr_confidence: float | None = Field(default=None, ge=0, le=100)
    layout_json: dict[str, object] = Field(default_factory=dict)


class ParsedDocument(BaseModel):
    source: ManifestSource
    pages: list[ParsedPage]
    warnings: list["IngestionWarning"] = Field(default_factory=list)


class IngestionWarning(BaseModel):
    source_id: str
    page_number: int | None = None
    severity: Literal["info", "warning", "error"] = "warning"
    code: str
    message: str
    metadata: dict[str, object] = Field(default_factory=dict)


class Chunk(BaseModel):
    source_id: str
    chunk_index: int = Field(ge=0)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    content: str = Field(min_length=1)
    content_hash: str
    subject: str
    grade: int | None = Field(default=None, ge=5, le=11)
    language: str
    source_category: str
    chunking_policy_id: str = "dim-page-section-v1"
    metadata: dict[str, object] = Field(default_factory=dict)
