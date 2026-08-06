import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from app.ingestion.domain.models import Block, IngestionWarning, ManifestSource, ParsedDocument, ParsedPage

if TYPE_CHECKING:
    from app.ingestion.domain.profile import ExtractorId


class SourceParseError(RuntimeError):
    """Raised when a source cannot be parsed by the configured parser path."""


class OptionalDependencyMissing(SourceParseError):
    """Raised when a parser path needs an optional ingestion dependency."""


def parse_source(source: ManifestSource) -> ParsedDocument:
    if source.source_type == "txt":
        return parse_txt_source(source)
    if source.source_type == "pdf":
        return parse_pdf_source(source)
    raise SourceParseError(f"Unsupported source type: {source.source_type}")


def parse_txt_source(source: ManifestSource) -> ParsedDocument:
    text = source.path.read_text(encoding="utf-8")
    block = Block(
        type="text",
        text=text,
        page=1,
        reading_order=1,
        confidence=1.0,
        method="txt_native"
    )
    return ParsedDocument(
        source=source,
        pages=[ParsedPage(page_number=1, text=text, layout_json={"parser": "txt", "blocks": [block.model_dump()]})],
        blocks=[block],
    )


def parse_pdf_source(source: ManifestSource) -> ParsedDocument:
    """Decide *how* to extract (detect or honour the manifest override), then hand
    the plan to ``extract_document`` to execute.

    The manifest's ``text_extraction`` is an explicit override of the detected
    plan, not the primary decision (GRO-128). When it is unset, the Profiler reads
    the PDF and the Planner picks the strategy from real page signals.
    """
    from app.ingestion.application.extract_document import extract_document
    from app.ingestion.domain.profile import ExtractionPlan, ExtractionStep

    override = _manifest_extractor_override(source)
    if override is not None:
        # Explicit strategy: skip profiling (it cannot change the decision) and
        # build a single book-level plan. Page count is best-effort for the plan
        # range; the chosen strategy already knows how to walk the book.
        page_count = _pdf_page_count(source.path)
        plan = ExtractionPlan(
            steps=[ExtractionStep(extractor=override, page_start=1, page_end=max(page_count, 1))]
        )
    else:
        from app.ingestion.application.profiler import Profiler
        from app.ingestion.application.extraction_planner import ExtractionPlanner

        profile = Profiler().profile(source)
        plan = ExtractionPlanner().plan(profile)

    return extract_document(source, plan)


def _manifest_extractor_override(source: ManifestSource) -> "ExtractorId | None":
    """Translate the manifest's extraction vocabulary into an extraction strategy.

    ``ocr_done`` means the PDF already carries a text layer, so it reads natively
    (with per-page OCR fallback) — the same proven History recipe.
    """
    parser_cfg = source.parser
    if parser_cfg is None:
        return None
    if parser_cfg.text_extraction == "got_ocr":
        return "got_ocr"
    if parser_cfg.text_extraction == "force_ocr":
        return "tesseract_layout"
    if parser_cfg.text_extraction == "ocr_done":
        return "native"
    if parser_cfg.primary == "docling":
        return "docling"
    return None


def _pdf_page_count(path: Path) -> int:
    try:
        from pypdf import PdfReader
    except ImportError:
        return 0
    try:
        return len(PdfReader(str(path)).pages)
    except Exception:
        return 0


def execute_extraction_strategy(
    source: ManifestSource, extractor: "ExtractorId | None"
) -> ParsedDocument:
    """Run the proven parser for a book-level extraction strategy.

    DİM books are prepared by a *single* extraction strategy (native+OCR-fallback,
    an offline GOT-OCR batch, Tesseract layout OCR, or Docling), so extraction is delegated
    whole-book to one of the proven paths rather than re-implemented per call
    site. Per-page-range *mixing* of strategies is a deliberate future seam (it is
    infeasible today: selective GOT-OCR needs a GPU the ingest host lacks).
    """
    if extractor in (None, "native", "ocr"):
        return _parse_pdf_with_routing(source)
    if extractor == "got_ocr":
        return _parse_pdf_with_got_ocr(source)
    if extractor in ("force_ocr", "tesseract_layout"):
        return _parse_pdf_with_forced_ocr(source)
    if extractor == "docling":
        pdf_path, ocr_warnings = prepare_pdf_for_parsing(source)
        document = _parse_pdf_with_docling(source, pdf_path)
        return document.model_copy(update={"warnings": [*ocr_warnings, *document.warnings]})
    return _parse_pdf_with_routing(source)


def _parse_pdf_with_got_ocr(source: ManifestSource) -> ParsedDocument:
    from app.ingestion.infrastructure.got_ocr import GotOcrError, got_ocr_pdf
    from app.ingestion.infrastructure.blocks_ocr import extract_markdown_blocks
    from app.ingestion.domain.heading import get_heading_policy, HeadingDetector

    try:
        got_pages = got_ocr_pdf(source.path)
    except GotOcrError as exc:
        raise SourceParseError(str(exc)) from exc

    pages: list[ParsedPage] = []
    blocks: list[Block] = []
    warnings: list[IngestionWarning] = []
    detector = HeadingDetector(get_heading_policy(source.subject))
    for got_page in got_pages:
        if not got_page.text.strip():
            warnings.append(
                IngestionWarning(
                    source_id=source.source_id,
                    page_number=got_page.page_number,
                    code="empty_got_ocr_page_text",
                    message="GOT-OCR-2.0 produced no text for this page.",
                )
            )
        page_blocks = extract_markdown_blocks(got_page.text, got_page.page_number, method="got_ocr")
        detector.detect(page_blocks)
        blocks.extend(page_blocks)
        pages.append(
            ParsedPage(
                page_number=got_page.page_number,
                text=got_page.text,
                layout_json={"parser": "got-ocr-2.0", "text_extraction": "got_ocr", "blocks": [b.model_dump() for b in page_blocks]},
            )
        )
    return ParsedDocument(source=source, pages=pages, blocks=blocks, warnings=warnings)


def _parse_pdf_with_forced_ocr(source: ManifestSource) -> ParsedDocument:
    return _parse_pdf_with_tesseract_layout(source)


def _parse_pdf_with_tesseract_layout(source: ManifestSource) -> ParsedDocument:
    from app.ingestion.infrastructure.ocr import OcrError, ocr_pdf_layout
    from app.ingestion.domain.heading import get_heading_policy, HeadingDetector

    try:
        ocr_pages = ocr_pdf_layout(source.path, languages=source.effective_ocr_languages)
    except OcrError as exc:
        raise SourceParseError(str(exc)) from exc

    pages: list[ParsedPage] = []
    blocks: list[Block] = []
    warnings: list[IngestionWarning] = []
    detector = HeadingDetector(get_heading_policy(source.subject))

    for ocr_page in ocr_pages:
        if not ocr_page.text.strip():
            warnings.append(
                IngestionWarning(
                    source_id=source.source_id,
                    page_number=ocr_page.page_number,
                    code="empty_ocr_page_text",
                    message="OCR produced no text for this page.",
                )
            )

        page_blocks = detector.detect(list(ocr_page.blocks))
        blocks.extend(page_blocks)

        pages.append(
            ParsedPage(
                page_number=ocr_page.page_number,
                text=ocr_page.text,
                ocr_confidence=ocr_page.ocr_confidence,
                layout_json={
                    "parser": "gs+tesseract-tsv",
                    "text_extraction": "force_ocr",
                    "extractor": "tesseract_layout",
                    "blocks": [block.model_dump() for block in page_blocks],
                },
            )
        )
    return ParsedDocument(source=source, pages=pages, blocks=blocks, warnings=warnings)


def prepare_pdf_for_parsing(source: ManifestSource) -> tuple[Path, list[IngestionWarning]]:
    if source.parser.text_extraction == "ocr_done":
        return source.path, []

    coverage = detect_pdf_text_coverage(source.path)
    min_coverage = source.expected.min_text_coverage_ratio or 0.8
    if coverage["coverage_ratio"] >= min_coverage:
        return source.path, []

    if source.ocr.enabled is False:
        return source.path, [
            IngestionWarning(
                source_id=source.source_id,
                code="low_pdf_text_coverage",
                message="PDF text coverage is below the expected threshold, but OCR is disabled.",
                metadata={"coverage": coverage, "min_text_coverage_ratio": min_coverage},
            )
        ]

    ocr_pdf, sidecar_txt = _ocr_output_paths(source.path)
    if not ocr_pdf.exists():
        _run_ocrmypdf(source, output_pdf=ocr_pdf, sidecar_txt=sidecar_txt)

    return ocr_pdf, [
        IngestionWarning(
            source_id=source.source_id,
            code="ocr_pdf_selected",
            message="PDF text coverage was below threshold; parsing OCRmyPDF output.",
            severity="info",
            metadata={
                "coverage": coverage,
                "min_text_coverage_ratio": min_coverage,
                "ocr_pdf": str(ocr_pdf),
                "sidecar": str(sidecar_txt),
            },
        )
    ]


def detect_pdf_text_coverage(path: Path) -> dict[str, int | float]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise OptionalDependencyMissing("Install ingestion extras to inspect PDFs: pip install -e '.[ingestion]'") from exc

    reader = PdfReader(str(path))
    page_count = len(reader.pages)
    pages_with_text = 0
    total_chars = 0

    for page in reader.pages:
        page_text = page.extract_text() or ""
        chars = len(page_text.strip())
        total_chars += chars
        if chars > 40:
            pages_with_text += 1

    ratio = pages_with_text / page_count if page_count else 0
    return {"page_count": page_count, "pages_with_text": pages_with_text, "total_chars": total_chars, "coverage_ratio": ratio}


def _parse_pdf_with_routing(source: ManifestSource) -> ParsedDocument:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise OptionalDependencyMissing("Install ingestion extras: pip install -e '.[ingestion]'") from exc

    from app.ingestion.infrastructure.blocks_native import extract_native_blocks
    from app.ingestion.domain.heading import get_heading_policy, HeadingDetector

    reader = PdfReader(str(source.path))
    page_count = len(reader.pages)

    needs_ocr_pages = set()
    # Generalize text coverage detect per page
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if len(text.strip()) <= 40:
            needs_ocr_pages.add(index)

    warnings: list[IngestionWarning] = []

    ocr_pdf = None
    if needs_ocr_pages and source.parser.text_extraction != "ocr_done" and source.ocr.enabled:
        ocr_pdf, sidecar_txt = _ocr_output_paths(source.path)
        if not ocr_pdf.exists():
            _run_ocrmypdf(source, output_pdf=ocr_pdf, sidecar_txt=sidecar_txt)
        warnings.append(
            IngestionWarning(
                source_id=source.source_id,
                code="ocr_fallback_pages",
                message=f"OCR fallback used for {len(needs_ocr_pages)} pages.",
                severity="info",
                metadata={"ocr_pages": list(needs_ocr_pages)}
            )
        )
    elif needs_ocr_pages and source.ocr.enabled is False:
        warnings.append(
            IngestionWarning(
                source_id=source.source_id,
                code="ocr_disabled_pages",
                message=f"{len(needs_ocr_pages)} pages had low text coverage but OCR is disabled.",
                metadata={"ocr_pages": list(needs_ocr_pages)}
            )
        )

    pages: list[ParsedPage] = []
    blocks: list[Block] = []
    detector = HeadingDetector(get_heading_policy(source.subject))

    for index in range(1, page_count + 1):
        is_native = index not in needs_ocr_pages
        pdf_path_to_read = source.path
        if not is_native and ocr_pdf and ocr_pdf.exists():
            pdf_path_to_read = ocr_pdf

        page_blocks = extract_native_blocks(str(pdf_path_to_read), index, method="native" if is_native else "ocr_fallback")
        detector.detect(page_blocks)
        page_text = "\n\n".join(b.text for b in page_blocks)

        if not page_text.strip():
            warnings.append(
                IngestionWarning(
                    source_id=source.source_id,
                    page_number=index,
                    code="empty_pdf_page_text",
                    message="PDF page has no extractable text after extraction routing.",
                )
            )

        pages.append(
            ParsedPage(
                page_number=index,
                text=page_text,
                layout_json={
                    "parser": "pdfplumber",
                    "pdf_path": str(pdf_path_to_read),
                    "routing": "native" if is_native else "ocr_fallback",
                    "blocks": [b.model_dump() for b in page_blocks]
                },
            )
        )
        blocks.extend(page_blocks)

    return ParsedDocument(source=source, pages=pages, blocks=blocks, warnings=warnings)


def _parse_pdf_with_docling(source: ManifestSource, pdf_path: Path | None = None) -> ParsedDocument:
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise OptionalDependencyMissing("Install ingestion extras to parse with Docling: pip install -e '.[ingestion]'") from exc

    from app.ingestion.infrastructure.blocks_ocr import extract_markdown_blocks
    from app.ingestion.domain.heading import get_heading_policy, HeadingDetector

    converter = DocumentConverter()
    result = converter.convert(str(pdf_path or source.path))
    markdown = result.document.export_to_markdown()

    blocks = extract_markdown_blocks(markdown, 1, "docling")
    HeadingDetector(get_heading_policy(source.subject)).detect(blocks)

    return ParsedDocument(
        source=source,
        pages=[ParsedPage(
            page_number=1,
            text=markdown,
            layout_json={"parser": "docling", "page_strategy": "markdown_fallback", "blocks": [b.model_dump() for b in blocks]}
        )],
        blocks=blocks,
        warnings=[
            IngestionWarning(
                source_id=source.source_id,
                code="docling_page_mapping_pending",
                message="Docling parser path is wired, but exact page segmentation still needs source-level verification.",
                severity="info",
            )
        ],
    )


def _ocr_output_paths(source_path: Path) -> tuple[Path, Path]:
    if source_path.parent.name == "derived":
        derived_dir = source_path.parent
    else:
        derived_dir = source_path.parent / "derived"
    output_stem = source_path.stem.removesuffix(".ocr")
    return derived_dir / f"{output_stem}.ocr.pdf", derived_dir / f"{output_stem}.txt"


def _run_ocrmypdf(source: ManifestSource, *, output_pdf: Path, sidecar_txt: Path) -> None:
    executable = shutil.which("ocrmypdf")
    if not executable:
        raise OptionalDependencyMissing(
            "OCR is required for this scanned PDF, but ocrmypdf was not found. "
            "Install it with: brew install ocrmypdf tesseract-lang"
        )

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    languages = "+".join(source.effective_ocr_languages)
    command = [
        executable,
        "--skip-text",
        "--deskew",
        "--clean",
        "-l",
        languages,
        "--sidecar",
        str(sidecar_txt),
        str(source.path),
        str(output_pdf),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        message = "OCRmyPDF failed while processing scanned source PDF."
        if detail:
            message = f"{message} {detail}"
        raise SourceParseError(message) from exc
