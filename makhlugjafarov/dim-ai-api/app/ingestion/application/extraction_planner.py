from app.ingestion.domain.profile import BookProfile, ExtractionPlan, ExtractionStep

class ExtractionPlanner:
    def plan(self, profile: BookProfile, overrides: dict | None = None) -> ExtractionPlan:
        steps = []
        current_extractor = None
        current_start = 1

        # Determine category family from subject
        # HUM -> azerbaycan_tarixi, umumi_tarix, edebiyyat
        # STEM_FORMULA -> mathematics, physics, chemistry
        # STEM_DESC -> biology, geography
        subject = (getattr(profile, "subject_guess", None) or "").lower()
        if subject in ("mathematics", "physics", "chemistry"):
            family = "STEM_FORMULA"
        elif subject in ("biology", "geography"):
            family = "STEM_DESC"
        else:
            family = "HUM"

        for i, page in enumerate(profile.pages):
            ext = "native"  # baseline default

            # Policy defaults + heuristics
            if family == "STEM_FORMULA":
                if page.formula_density > 0.05: # > 5% math chars
                    ext = "got_ocr"
                elif page.needs_layout_ocr:
                    ext = "tesseract_layout"
            else:
                if page.table_likeness > 0.8:
                    ext = "docling"
                elif page.needs_layout_ocr:
                    ext = "tesseract_layout"

            # Allow page-level overrides
            if overrides and "extractor" in overrides:
                ext = overrides["extractor"] # basic override

            if ext != current_extractor:
                if current_extractor is not None:
                    steps.append(ExtractionStep(extractor=current_extractor, page_start=current_start, page_end=page.page_number - 1))
                current_extractor = ext
                current_start = page.page_number

        if current_extractor is not None and profile.pages:
            steps.append(ExtractionStep(extractor=current_extractor, page_start=current_start, page_end=profile.pages[-1].page_number))

        return ExtractionPlan(steps=steps)
