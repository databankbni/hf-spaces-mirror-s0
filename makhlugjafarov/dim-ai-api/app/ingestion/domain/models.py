from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.ingestion.domain.ocr_profiles import languages_for_sector


# "dim_html" = an official DİM e-textbook HTML bundle (units/unit-*/pageN.xhtml +
# assets). Registered here so the manifest validates; the DimHtmlExtractor that
# actually parses it lands in the HTML-road epic — until then parser.py rejects it.
SourceType = Literal["pdf", "txt", "dim_html"]
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
    # None = "not explicitly overridden" → resolve from the source's sector
    # (see ManifestSource.effective_ocr_languages / ocr_profiles.py). A book that
    # genuinely needs a custom set can still pin one here; otherwise the sector
    # profile decides, which keeps `rus` off for the Azerbaijani sector by default.
    languages: list[str] | None = None


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

    @property
    def effective_ocr_languages(self) -> list[str]:
        """Tesseract language list to OCR this source with.

        An explicit ``ocr.languages`` wins (per-book override); otherwise the
        languages are resolved from the source's sector (``language``) via the
        profile registry. This is the single place consumers read OCR languages
        from — they must not touch ``ocr.languages`` directly, or the sector
        default (and the `rus`-off guarantee) is bypassed.
        """
        if self.ocr.languages is not None:
            return list(self.ocr.languages)
        return languages_for_sector(self.language)

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


class Block(BaseModel):
    type: str
    level: int | None = None
    text: str
    page: int
    bbox: list[float] | None = None
    reading_order: int
    confidence: float
    method: str
    metadata: dict[str, object] = Field(default_factory=dict)


class SectionBlock(BaseModel):
    id: str | None = None
    document_id: str
    ordinal: int
    section_title: str | None = None
    page_start: int
    page_end: int
    content: str
    content_hash: str
    image_uri: str | None = None
    extraction_method: str
    extraction_confidence: float | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class CurriculumNode(BaseModel):
    """A node in a book's TOC-derived curriculum tree (Fəsil → Bölmə → Mövzu).

    The tree is built top-down from the table of contents, so a node is keyed by
    a stable ``node_path`` (``"1"``, ``"1.2"``, ``"1.2.3"`` — ordinals from the
    root) rather than a DB uuid: the builder is a pure function with no DB, and
    the loader maps ``node_path`` → row id to wire ``parent_id`` and the
    ``chunks/section_blocks`` foreign keys. ``parent_path`` is ``None`` at the
    root. Pages are *printed* (book) pages, the same space sections cite in.
    """

    node_path: str
    parent_path: str | None = None
    level: int = Field(ge=1)
    ordinal: int = Field(ge=1)
    title: str = Field(min_length=1)
    raw_title: str
    page_start: int | None = None
    page_end: int | None = None
    extraction_method: str = "toc"
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)
    metadata: dict[str, object] = Field(default_factory=dict)


BlockKind = Literal["data_table", "exercise_template", "figure", "formula"]


class ContentBlock(BaseModel):
    """A typed non-prose artefact (table / figure / formula) attached to a node.

    Geography (and other STEM-descriptive books) carry data the prose flattens:
    tables, maps/diagrams, and isolated formulas. Each is detected as a layout
    region, extracted by the right tool (img2table cells / VLM caption / crop),
    and attached to the deepest curriculum node whose page span contains it — so a
    module can ask "this topic + its tables/figures". Like ``CurriculumNode`` the
    attachment is carried as a ``node_path`` (loader maps it → the FK).

    Design choice (from the GRO-79 spike): tables are stored as ``markdown`` for
    LLM consumption rather than per-cell typed values — OCR noise (``26,5?`` ← 26.5°)
    makes strict typing brittle, while an LLM tolerates it. ``fill_ratio`` separates
    real ``data_table``s from blank ``exercise_template`` worksheets. Figures keep
    both the authoritative printed ``caption`` (OCR proximity) and a best-effort
    ``vlm_description`` (we never rely on VLM Azerbaijani fluency alone).
    """

    source_id: str
    ordinal: int = Field(ge=0)
    kind: BlockKind
    page: int = Field(ge=1)
    bbox: list[float] | None = None
    # table
    markdown: str | None = None
    n_rows: int | None = Field(default=None, ge=0)
    n_cols: int | None = Field(default=None, ge=0)
    fill_ratio: float | None = Field(default=None, ge=0, le=1)
    # figure
    caption: str | None = None
    vlm_description: str | None = None
    detection_confidence: float | None = Field(default=None, ge=0, le=1)
    extraction_method: str
    node_path: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class ParsedDocument(BaseModel):
    source: ManifestSource
    pages: list[ParsedPage]
    warnings: list["IngestionWarning"] = Field(default_factory=list)
    blocks: list[Block] = Field(default_factory=list)
    sections: list[SectionBlock] = Field(default_factory=list)
    curriculum_nodes: list[CurriculumNode] = Field(default_factory=list)
    content_blocks: list[ContentBlock] = Field(default_factory=list)


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
    section_block_id: str | None = None
    chunking_policy_id: str = "dim-page-section-v1"
    metadata: dict[str, object] = Field(default_factory=dict)
