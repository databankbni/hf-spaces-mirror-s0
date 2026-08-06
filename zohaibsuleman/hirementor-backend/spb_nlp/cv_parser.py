"""
CV Parser - NLP-based information extraction from resumes/ CVs.
Extracts: name, email, phone, skills, education, experience, GPA,
certifications, projects using regex + keyword matching.

Includes SpacyNerParser — enhances extraction using spaCy NER model
(PERSON, ORG, GPE, DATE entities) with automatic fallback to regex.
"""

import os
from typing import List, Optional

from spb_nlp.models import CVParseResult
from spb_nlp.utils import (
    clean_text, extract_emails, extract_phones, extract_skills,
    extract_education, extract_experience, extract_name,
    estimate_years_of_experience, extract_gpa, extract_certifications,
    extract_projects, preprocess_for_embedding,
)

# ------------------------------------------------------------------ #
#  Optional dependency: spaCy NER model
# ------------------------------------------------------------------ #
_HAS_SPACY = False
try:
    import spacy
    _HAS_SPACY = True
except ImportError:
    pass


class CVParser:
    """
    NLP-based CV/Resume parser.

    Extracts structured information from raw text or PDF files.
    Uses regex patterns, keyword matching, and heuristics --
    no external AI API required.
    """

    def parse_text(self, text: str) -> CVParseResult:
        """
        Parse a plain text resume and return structured data.

        Args:
            text: Raw text content of the resume.

        Returns:
            CVParseResult with all extracted fields.
        """
        text = clean_text(text)

        email = extract_emails(text)
        phone = extract_phones(text)
        skills = extract_skills(text)
        education = extract_education(text)
        experience = extract_experience(text)
        name = extract_name(text)
        years_exp = estimate_years_of_experience(text)
        gpa = extract_gpa(text)
        certifications = extract_certifications(text)
        projects = extract_projects(text)

        summary = self._generate_summary(name, skills, education, years_exp)

        return CVParseResult(
            candidate_name=name,
            email=email[0] if email else "",
            phone=phone[0] if phone else "",
            skills=skills,
            experience=experience,
            education=education,
            gpa=gpa,
            years_of_experience=years_exp,
            certifications=certifications,
            projects=projects,
            summary=summary,
            raw_text=text,
        )

    def parse_pdf(self, file_path: str) -> CVParseResult:
        """
        Parse a PDF resume file.

        Uses pdfminer to extract text, then applies NLP parsing.

        Args:
            file_path: Absolute path to the PDF file.

        Returns:
            CVParseResult with extracted fields.
        """
        text = self._extract_pdf_text(file_path)
        return self.parse_text(text)

    def parse_pdf_bytes(self, pdf_bytes: bytes) -> CVParseResult:
        """
        Parse a PDF from raw bytes (e.g., uploaded file).

        Args:
            pdf_bytes: Raw PDF file content.

        Returns:
            CVParseResult with extracted fields.
        """
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name
        try:
            result = self.parse_pdf(tmp_path)
        finally:
            os.unlink(tmp_path)
        return result

    def batch_parse(self, file_paths: List[str]) -> List[CVParseResult]:
        """Parse multiple PDFs and return list of results."""
        return [self.parse_pdf(fp) for fp in file_paths]

    # ------------------------------------------------------------------ #
    #  Private helpers
    # ------------------------------------------------------------------ #

    def _extract_pdf_text(self, file_path: str) -> str:
        """
        Extract text from a PDF, trying pdfminer first and falling back to
        PyPDF2 if pdfminer fails outright or returns unusably little text.

        pdfminer chokes on some real-world resume PDFs — certain resume-
        builder exports, PDFs with table-based layouts, or unusual embedded
        fonts can make it raise or silently return almost nothing. That
        used to propagate all the way up as an unhandled exception, which
        turned into a hard failure for the whole upload (the frontend would
        fall back to whatever was on the student's profile instead of the
        CV actually being uploaded — silently, with no indication that
        parsing had failed at all). PyPDF2 uses a different extraction
        engine and often succeeds where pdfminer doesn't, so it's a
        meaningful second attempt rather than a redundant one. Never raises
        — worst case this returns an empty string, which the rest of the
        pipeline already handles gracefully.
        """
        text = ""
        try:
            from pdfminer.high_level import extract_text as pdf_extract
            text = pdf_extract(file_path) or ""
        except Exception:
            text = ""

        if len(text.strip()) < 20:
            try:
                import PyPDF2
                with open(file_path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    pypdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
                if len(pypdf_text.strip()) > len(text.strip()):
                    text = pypdf_text
            except Exception:
                pass  # both extractors failed — return whatever we have, possibly empty

        return text

    def _generate_summary(
        self, name: str, skills: List[str],
        education: str, years_exp: float,
    ) -> str:
        parts = []
        if name:
            parts.append(f"{name}")
        if skills:
            parts.append(f"Skilled in {', '.join(skills[:8])}")
        if education:
            parts.append(f"Education: {education[:100]}")
        if years_exp > 0:
            parts.append(f"{years_exp:.0f}+ years of experience")
        return " | ".join(parts) if parts else ""

    def get_clean_text_for_embedding(self, parse_result: CVParseResult) -> str:
        """Produce a clean text representation suitable for embedding."""
        parts = [
            f"Skills: {', '.join(parse_result.skills)}",
            f"Experience: {parse_result.experience[:300]}",
            f"Education: {parse_result.education[:200]}",
            f"Certifications: {', '.join(parse_result.certifications)}",
            f"Projects: {', '.join(parse_result.projects)}",
            f"Summary: {parse_result.summary}",
        ]
        return preprocess_for_embedding(" ".join(parts))


# ------------------------------------------------------------------ #
#  SpaCy NER Parser (enhances extraction with named entity recognition)
# ------------------------------------------------------------------ #

class SpacyNerParser(CVParser):
    """
    CV parser that uses spaCy NER model (en_core_web_lg) for
    entity extraction, with fallback to regex-based CVParser.

    spaCy entities used:
      - PERSON  → candidate name
      - ORG     → universities, companies, organizations
      - GPE     → locations (city, country)
      - DATE    → years, date ranges
      - MONEY   → salary mentions

    When spaCy is not installed, silently falls back to CVParser.
    """

    _DEFAULT_MODEL = "en_core_web_sm"

    def __init__(self, model_name: str = _DEFAULT_MODEL):
        super().__init__()
        self._model_name = model_name
        self._nlp = None
        self._load_model()

    # ------------------------------------------------------------------ #
    #  Model loading
    # ------------------------------------------------------------------ #

    def _load_model(self):
        if not _HAS_SPACY:
            return
        try:
            self._nlp = spacy.load(self._model_name)
        except OSError:
            # Try downloading the model automatically
            try:
                from spacy.cli import download
                download(self._model_name)
                self._nlp = spacy.load(self._model_name)
            except Exception:
                self._nlp = None

    @property
    def is_using_spacy(self) -> bool:
        """Whether spaCy NER is active or falling back to regex."""
        return self._nlp is not None

    # ------------------------------------------------------------------ #
    #  Override parse_text to use NER
    # ------------------------------------------------------------------ #

    def parse_text(self, text: str) -> CVParseResult:
        if self._nlp is None:
            return super().parse_text(text)

        text = clean_text(text)
        doc = self._nlp(text)

        # -- Extract via NER + regex hybrid ---------------------------- #
        email = extract_emails(text)
        phone = extract_phones(text)
        skills = self._ner_extract_skills(doc, text)
        education = self._ner_extract_education(doc, text)
        experience = extract_experience(text)
        name = self._ner_extract_name(doc, text)
        years_exp = estimate_years_of_experience(text)
        gpa = extract_gpa(text)
        certifications = extract_certifications(text)
        projects = extract_projects(text)

        summary = self._generate_summary(name, skills, education, years_exp)

        return CVParseResult(
            candidate_name=name,
            email=email[0] if email else "",
            phone=phone[0] if phone else "",
            skills=skills,
            experience=experience,
            education=education,
            gpa=gpa,
            years_of_experience=years_exp,
            certifications=certifications,
            projects=projects,
            summary=summary,
            raw_text=text,
        )

    # ------------------------------------------------------------------ #
    #  NER extraction helpers
    # ------------------------------------------------------------------ #

    def _ner_extract_name(self, doc, text: str) -> str:
        """Extract name using PERSON entities, fallback to regex."""
        for ent in doc.ents:
            if ent.label_ == "PERSON" and len(ent.text.split()) in [2, 3, 4]:
                return ent.text.strip()
        return extract_name(text)

    def _ner_extract_skills(self, doc, text: str) -> List[str]:
        """
        Extract skills using NER + keyword matching.
        spaCy labels PROG_LANG, PRODUCT can detect tech terms.
        Fallback to keyword set.
        """
        skills = set()

        # NER-based: ORG + PRODUCT can contain tech names (TensorFlow, etc.)
        for ent in doc.ents:
            ent_lower = ent.text.lower().strip()
            if ent.label_ in ("PRODUCT", "ORG", "WORK_OF_ART"):
                from spb_nlp.utils import SKILL_KEYWORDS
                if ent_lower in SKILL_KEYWORDS:
                    skills.add(ent_lower)

        # Merge with keyword-based extraction for coverage
        skills.update(extract_skills(text))
        return sorted(skills)

    def _ner_extract_education(self, doc, text: str) -> str:
        """
        Extract education using ORG entities (universities) + degree keywords.
        Fallback to regex section extraction.
        """
        orgs = []
        univ_keywords = {"university", "college", "institute", "school",
                         "academy", "polytechnic"}
        for ent in doc.ents:
            if ent.label_ == "ORG":
                if any(kw in ent.text.lower() for kw in univ_keywords):
                    orgs.append(ent.text.strip())

        # Try section-based extraction first
        edu_section = extract_education(text)
        if edu_section:
            return edu_section

        # If no section found, build from NER entities + degree lines
        degree_lines = []
        for ent in doc.ents:
            if ent.label_ == "ORG" and any(kw in ent.text.lower() for kw in univ_keywords):
                degree_lines.append(f"Attended {ent.text}")
        return " | ".join(degree_lines) if degree_lines else ""
