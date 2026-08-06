from app.ingestion.domain.models import ManifestSource
from app.ingestion.domain.profile import BookProfile, PageProfile, ExtractionPlan
from app.ingestion.domain.page_offset import detect_page_offset
from app.platform.text_quality import cyrillic_garble_token_ratio, spaced_letter_run_count

NATIVE_TEXT_FLOOR = 40
GARBLE_OCR_THRESHOLD = 0.02

class Profiler:
    def profile(self, source: ManifestSource) -> BookProfile:
        pages = []
        page_numbers = []
        has_toc = False
        try:
            # pypdf is an optional [ingestion] extra and never loads in the request
            # path — defer the import (see got_ocr.py). A missing extra degrades to
            # page_count=0, the same fallback as an unreadable PDF.
            import pypdf

            reader = pypdf.PdfReader(source.path)
            page_count = len(reader.pages)

            for i in range(page_count):
                page_obj = reader.pages[i]
                text = page_obj.extract_text() or ""

                native_text_chars = len(text.strip())
                is_scanned = native_text_chars <= NATIVE_TEXT_FLOOR
                garble_ratio = cyrillic_garble_token_ratio(text)
                spaced_runs = spaced_letter_run_count(text)
                needs_layout_ocr = is_scanned or garble_ratio > GARBLE_OCR_THRESHOLD or spaced_runs > 0

                # Heuristics
                formula_density = self._calc_formula_density(text)
                table_likeness = self._calc_table_likeness(text)

                if not has_toc and "MÜNDƏRİCAT" in text.upper():
                    has_toc = True

                pages.append(PageProfile(
                    page_number=i + 1,
                    native_text_chars=native_text_chars,
                    is_scanned=is_scanned,
                    formula_density=formula_density,
                    table_likeness=table_likeness,
                    native_garble_token_ratio=garble_ratio,
                    spaced_letter_runs=spaced_runs,
                    needs_layout_ocr=needs_layout_ocr,
                    chosen_extractor=None  # assigned by the planner
                ))
                page_numbers.append((i + 1, None))  # printed-page numbers TBD
        except Exception:
            page_count = 0

        offset = detect_page_offset(page_numbers)

        profile = BookProfile(
            page_count=page_count,
            language="az",
            page_offset=offset,
            has_toc=has_toc,
            dominant_content=self._dominant_content(pages),
            subject_guess=source.subject if hasattr(source, "subject") else None,
            grade_guess=source.grade if hasattr(source, "grade") else None,
            pages=pages,
            plan=ExtractionPlan(steps=[]),  # populated by the planner
            confidence=0.9,
            warnings=[]
        )
        return profile

    def _dominant_content(self, pages: list[PageProfile]) -> str:
        """Classify the book from mean formula density (observability only — the
        per-page planner decides routing). Math books carry visibly more math
        glyphs than prose textbooks."""
        if not pages:
            return "prose"
        mean_formula = sum(p.formula_density for p in pages) / len(pages)
        if mean_formula >= 0.05:
            return "math"
        return "prose"

    def _calc_formula_density(self, text: str) -> float:
        """Heuristic for formula density.
        Counts math-specific glyphs and compares against total text length.
        """
        if not text:
            return 0.0
        math_chars = set("=+-/*√∑∫()[]{}<>≤≥≠≈∞")
        count = sum(1 for c in text if c in math_chars)
        return count / len(text)

    def _calc_table_likeness(self, text: str) -> float:
        """Heuristic for table likeness.
        Counts lines that have multiple large gaps (tabs or multiple spaces) or pipe characters.
        """
        if not text:
            return 0.0
        lines = text.split("\n")
        if not lines:
            return 0.0
        table_lines = 0
        for line in lines:
            if "|" in line or "   " in line or "\t" in line:
                table_lines += 1
        return table_lines / len(lines)
