import shutil
import subprocess
from pathlib import Path

from app.ingest.models import IngestionWarning, ManifestSource, ParsedDocument, ParsedPage


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
    return ParsedDocument(
        source=source,
        pages=[ParsedPage(page_number=1, text=text, layout_json={"parser": "txt"})],
    )


def parse_pdf_source(source: ManifestSource) -> ParsedDocument:
    # got_ocr: formula-aware OCR (GOT-OCR-2.0) for STEM pages where plain OCR
    # destroys the math. Emits Markdown + LaTeX. Offline batch only.
    if source.parser.text_extraction == "got_ocr":
        return _parse_pdf_with_got_ocr(source)

    # force_ocr: the embedded text layer is known-bad (mojibake / no ToUnicode),
    # so rasterize + OCR every page instead of trusting extraction.
    if source.parser.text_extraction == "force_ocr":
        return _parse_pdf_with_forced_ocr(source)

    pdf_path, ocr_warnings = prepare_pdf_for_parsing(source)
    if source.parser.primary == "docling":
        document = _parse_pdf_with_docling(source, pdf_path)
    else:
        document = _parse_pdf_with_pypdf(source, pdf_path)
    return document.model_copy(update={"warnings": [*ocr_warnings, *document.warnings]})


def _parse_pdf_with_got_ocr(source: ManifestSource) -> ParsedDocument:
    from app.ingest.got_ocr import GotOcrError, got_ocr_pdf

    try:
        got_pages = got_ocr_pdf(source.path)
    except GotOcrError as exc:
        raise SourceParseError(str(exc)) from exc

    pages: list[ParsedPage] = []
    warnings: list[IngestionWarning] = []
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
        pages.append(
            ParsedPage(
                page_number=got_page.page_number,
                text=got_page.text,
                layout_json={"parser": "got-ocr-2.0", "text_extraction": "got_ocr"},
            )
        )
    return ParsedDocument(source=source, pages=pages, warnings=warnings)


def _parse_pdf_with_forced_ocr(source: ManifestSource) -> ParsedDocument:
    from app.ingest.ocr import OcrError, ocr_pdf

    try:
        ocr_pages = ocr_pdf(source.path, languages=source.ocr.languages)
    except OcrError as exc:
        raise SourceParseError(str(exc)) from exc

    pages: list[ParsedPage] = []
    warnings: list[IngestionWarning] = []
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
        pages.append(
            ParsedPage(
                page_number=ocr_page.page_number,
                text=ocr_page.text,
                layout_json={"parser": "gs+tesseract", "text_extraction": "force_ocr"},
            )
        )
    return ParsedDocument(source=source, pages=pages, warnings=warnings)


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


def _parse_pdf_with_pypdf(source: ManifestSource, pdf_path: Path | None = None) -> ParsedDocument:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise OptionalDependencyMissing("Install ingestion extras to parse PDFs: pip install -e '.[ingestion]'") from exc

    reader = PdfReader(str(pdf_path or source.path))
    pages: list[ParsedPage] = []
    warnings: list[IngestionWarning] = []

    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if not text.strip():
            warnings.append(
                IngestionWarning(
                    source_id=source.source_id,
                    page_number=index,
                    code="empty_pdf_page_text",
                    message="PDF page has no extractable text; OCR may be required.",
                )
            )
        pages.append(
            ParsedPage(
                page_number=index,
                text=text,
                layout_json={"parser": "pypdf", "pdf_path": str(pdf_path or source.path)},
            )
        )

    return ParsedDocument(source=source, pages=pages, warnings=warnings)


def _parse_pdf_with_docling(source: ManifestSource, pdf_path: Path | None = None) -> ParsedDocument:
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise OptionalDependencyMissing("Install ingestion extras to parse with Docling: pip install -e '.[ingestion]'") from exc

    converter = DocumentConverter()
    result = converter.convert(str(pdf_path or source.path))
    markdown = result.document.export_to_markdown()

    return ParsedDocument(
        source=source,
        pages=[ParsedPage(page_number=1, text=markdown, layout_json={"parser": "docling", "page_strategy": "markdown_fallback"})],
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
    languages = "+".join(source.ocr.languages)
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
