from dataclasses import dataclass
from typing import Literal

ExtractorId = Literal["native", "ocr", "got_ocr", "force_ocr", "tesseract_layout", "docling"]

@dataclass(frozen=True)
class PageProfile:
    page_number: int                 # 1-based PDF index
    native_text_chars: int           # chars pypdf extracts
    is_scanned: bool                 # native_text_chars <= NATIVE_TEXT_FLOOR
    formula_density: float           # 0..1 heuristic (math glyphs / area)
    table_likeness: float            # 0..1 (ruled-line / column heuristic)
    native_garble_token_ratio: float = 0.0
    spaced_letter_runs: int = 0
    needs_layout_ocr: bool = False
    chosen_extractor: ExtractorId | None = None  # assigned by the planner

@dataclass(frozen=True)
class ExtractionStep:
    extractor: ExtractorId
    page_start: int
    page_end: int

@dataclass(frozen=True)
class ExtractionPlan:
    steps: list[ExtractionStep]

@dataclass(frozen=True)
class BookProfile:
    page_count: int
    language: str                    # detected: az | ru | en
    page_offset: int                 # auto-detected printed-page vs PDF-index delta
    has_toc: bool                    # MÜNDƏRİCAT / dot-leader page found
    dominant_content: Literal["prose", "math", "mixed"]
    subject_guess: str | None        # from title-page text / filename
    grade_guess: int | None
    pages: list[PageProfile]
    plan: ExtractionPlan             # page-range → extractor mapping
    confidence: float                # overall auto-config confidence 0..1
    warnings: list[str]
