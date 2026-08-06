from collections import Counter
from pathlib import Path

from app.ingestion.domain.models import ManifestSource, ParsedDocument
from app.ingestion.domain.profile import ExtractionPlan, ExtractorId


def _dominant_extractor(plan: ExtractionPlan) -> ExtractorId | None:
    """The book-level extraction strategy: the extractor covering the most pages.

    DİM books are prepared by a single strategy, so a plan is effectively
    homogeneous and we execute the whole book with one proven parser. If a plan
    ever mixes strategies, the page-dominant one wins (a conservative,
    deterministic choice) rather than silently dropping pages.
    """
    if not plan.steps:
        return None
    pages_per_extractor: Counter[ExtractorId] = Counter()
    for step in plan.steps:
        pages_per_extractor[step.extractor] += step.page_end - step.page_start + 1
    return pages_per_extractor.most_common(1)[0][0]


def extract_document(
    source: ManifestSource, plan: ExtractionPlan, gpu_artifact_path: Path | None = None
) -> ParsedDocument:
    """Execute an extraction plan into a ParsedDocument.

    Routing is delegated to the proven per-strategy parsers (the History
    native+OCR-fallback recipe, the GOT-OCR path, force-OCR, or Docling) so there
    is a single implementation of each extractor — this module only selects which
    one the plan calls for.
    """
    # Deferred to avoid an import cycle: parser.parse_pdf_source builds the plan
    # that lands here, and the strategy executor lives alongside it.
    from app.ingestion.application.parser import execute_extraction_strategy

    return execute_extraction_strategy(source, _dominant_extractor(plan))
