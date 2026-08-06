"""
resume_parser.py
-----------------
Extracts structured information from resume files (PDF or DOCX).

Pipeline:
1. Extract raw text from file
2. Preprocess text (tokenize, normalize)
3. Extract skills, technologies, projects, education, certifications
4. Return structured dictionary

AI-assisted: SpaCy NER for entity recognition, pattern matching for skills.
"""

import re
import io
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

# ── NLTK / SpaCy Initialization ─────────────────────────────

# We import lazily to avoid hard failures if a library is missing.
# This way the service can still run partially.

def _init_nlp():
    """Load SpaCy model — returns None if unavailable."""
    try:
        import spacy
        return spacy.load("en_core_web_sm")
    except Exception as e:
        logger.warning(f"SpaCy not available: {e}. Falling back to regex.")
        return None

def _init_nltk():
    """Download required NLTK data."""
    try:
        import nltk
        nltk.download("punkt", quiet=True)
        nltk.download("stopwords", quiet=True)
        nltk.download("averaged_perceptron_tagger", quiet=True)
        return True
    except Exception:
        return False

# Load once at module import time
nlp = _init_nlp()
_init_nltk()

# ── Skill Keywords Database ──────────────────────────────────
# A curated list of technical skills/technologies to look for in resumes.

TECH_SKILLS = {
    "languages": [
        "python", "javascript", "java", "c++", "c#", "typescript", "go", "rust",
        "kotlin", "swift", "php", "ruby", "scala", "r", "matlab", "dart"
    ],
    "frontend": [
        "react", "angular", "vue", "nextjs", "gatsby", "html", "css", "sass",
        "tailwind", "bootstrap", "webpack", "vite", "redux", "graphql", "apollo"
    ],
    "backend": [
        "node.js", "nodejs", "express", "django", "flask", "fastapi", "spring",
        "laravel", "rails", "nestjs", "fastify", "rest api", "microservices"
    ],
    "databases": [
        "mongodb", "postgresql", "mysql", "sqlite", "redis", "elasticsearch",
        "cassandra", "dynamodb", "firebase", "supabase", "prisma", "mongoose"
    ],
    "cloud_devops": [
        "aws", "gcp", "azure", "docker", "kubernetes", "terraform", "ansible",
        "jenkins", "github actions", "ci/cd", "linux", "nginx", "apache"
    ],
    "ml_ai": [
        "tensorflow", "pytorch", "keras", "sklearn", "scikit-learn", "pandas",
        "numpy", "matplotlib", "spacy", "nltk", "hugging face", "langchain",
        "openai", "llm", "machine learning", "deep learning", "nlp", "computer vision"
    ],
    "tools": [
        "git", "github", "gitlab", "jira", "postman", "figma", "vs code",
        "intellij", "vim", "bash", "powershell"
    ]
}

# Flatten all skills into a single list for matching
ALL_SKILLS = [skill for group in TECH_SKILLS.values() for skill in group]

# ── Text Extraction ──────────────────────────────────────────

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extract text from a PDF.
    Primary: pdfminer.six (preserves layout).
    Fallback: OCR via pytesseract + pdf2image for scanned/image-based PDFs.
    """
    try:
        from pdfminer.high_level import extract_text_to_fp
        from pdfminer.layout import LAParams
        from io import StringIO
        output = StringIO()
        params = LAParams(line_margin=0.5, char_margin=2.0, word_margin=0.1)
        extract_text_to_fp(io.BytesIO(file_bytes), output, laparams=params)
        text = output.getvalue().strip()
        if text and len(text.split()) > 20:
            return text
        logger.info("pdfminer returned sparse text — attempting OCR")
    except ImportError:
        logger.warning("pdfminer not available — falling back to OCR")
    except Exception as e:
        logger.warning(f"pdfminer error: {e} — falling back to OCR")

    # OCR fallback
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
        logger.info("Running OCR on PDF (scanned resume detected)")
        images = convert_from_bytes(file_bytes, dpi=200)
        pages = [pytesseract.image_to_string(img, lang="eng") for img in images]
        combined = "\n".join(pages).strip()
        if combined:
            logger.info(f"OCR extracted {len(combined.split())} words")
            return combined
    except ImportError:
        logger.warning("pdf2image/pytesseract not installed — OCR unavailable")
    except Exception as e:
        logger.error(f"OCR fallback error: {e}")

    return ""


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract text from a DOCX file using python-docx."""
    try:
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)
    except ImportError:
        logger.warning("python-docx not available")
        return ""
    except Exception as e:
        logger.error(f"DOCX extraction error: {e}")
        return ""

# ── Text Preprocessing ───────────────────────────────────────

def preprocess_text(text: str) -> str:
    """
    Clean and normalize resume text for skill extraction ONLY.
    Preserves newlines so section detection still works downstream.
    - lowercase per line
    - collapses horizontal whitespace (spaces/tabs) but NOT newlines
    - keeps +, #, / for C++, C#, Node.js skill matching
    """
    text = text.lower()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in lines]
    text = "\n".join(lines)
    text = re.sub(r"[^\w\s.,@\-+#/]", " ", text)
    return text.strip()

# ── Skill Extraction ─────────────────────────────────────────

def _make_skill_pattern(skill: str) -> str:
    """
    Build regex for skill name, handling C++, C#, Node.js edge cases.
    """
    escaped = re.escape(skill)
    if skill.endswith(("+", "#", ".")):
        return r"(?:^|[\s,/;])" + escaped + r"(?:[\s,/;]|$)"
    if "." in skill:
        flexible = escaped.replace("\\.", "[.\\s]?")
        return r"(?:^|[\s,/;])" + flexible + r"(?:[\s,/;]|$)"
    return r"\b" + escaped + r"\b"


def extract_skills(text: str) -> List[str]:
    """
    Find known technical skills in the resume text using keyword matching.
    Uses context-aware regex for tricky names like C++, C#, Node.js.
    Returns a deduplicated list of matched skills.
    """
    lower_text = text.lower()
    found = []

    for skill in ALL_SKILLS:
        pattern = _make_skill_pattern(skill)
        try:
            if re.search(pattern, lower_text, re.IGNORECASE | re.MULTILINE):
                found.append(skill)
        except re.error:
            if skill.lower() in lower_text:
                found.append(skill)

    seen = set()
    unique = []
    for s in found:
        if s not in seen:
            seen.add(s)
            unique.append(s)

    return unique

def extract_technologies(skills: List[str]) -> List[str]:
    """
    From the matched skills, separate out technology names
    (databases, cloud, tools) as 'technologies'.
    """
    tech_categories = ["databases", "cloud_devops", "tools"]
    tech_skills_flat = [s for cat in tech_categories for s in TECH_SKILLS[cat]]
    return [s for s in skills if s in tech_skills_flat]

# ── Section Extraction ───────────────────────────────────────

def extract_projects(text: str) -> List[Dict]:
    """
    Heuristically find project sections and extract project names + descriptions.
    Looks for lines after 'projects' heading.
    """
    projects = []
    lines = text.split("\n")

    in_projects = False
    current_project = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Detect projects section header
        if re.match(r"^(projects?|personal projects?|academic projects?|projects\s*[&and]*\s*research|key projects?|notable projects?|major projects?)[\s:]*$", line.lower(), re.IGNORECASE):
            in_projects = True
            continue

        # Detect end of projects section (next major section)
        if in_projects and re.match(
            r"^(education|experience|skills|certifications|work experience|internships?|achievements?)$",
            line.lower()
        ):
            in_projects = False
            if current_project:
                projects.append(current_project)
                current_project = None
            continue

        if in_projects:
            # A new project likely starts with a capitalized or title-like line
            if len(line) < 80 and (line[0].isupper() or line[0].isdigit()):
                if current_project:
                    projects.append(current_project)
                # Extract technologies mentioned in the project line
                found_techs = extract_skills(line)
                current_project = {
                    "name": line[:100],
                    "description": "",
                    "technologies": found_techs
                }
            elif current_project:
                current_project["description"] += " " + line

    if current_project:
        projects.append(current_project)

    return projects[:10]  # cap at 10 projects


def extract_education(text: str) -> List[Dict]:
    """Extract education entries (degree, institution, year)."""
    education = []
    lines = text.split("\n")
    in_edu = False

    degree_patterns = [
        r"b\.?\s?tech|bachelor|b\.?\s?e\.|b\.?\s?sc|m\.?\s?tech|m\.?\s?sc|phd|mba|b\.?\s?ca|mca"
    ]
    degree_regex = re.compile("|".join(degree_patterns), re.IGNORECASE)

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if re.match(r"^(education|educational background|academic background|academic qualifications?|qualifications?|academics?)[\s:]*$", line.lower(), re.IGNORECASE):
            in_edu = True
            continue

        if in_edu and re.match(
            r"^(experience|projects?|skills|certifications|work)$", line.lower()
        ):
            in_edu = False
            continue

        if in_edu or degree_regex.search(line):
            # Try to extract year
            year_match = re.search(r"\b(19|20)\d{2}\b", line)
            year = year_match.group() if year_match else ""

            education.append({
                "degree": line[:100],
                "institution": "",
                "year": year
            })

    return education[:5]


def extract_certifications(text: str) -> List[str]:
    """Extract certification names."""
    certs = []
    lines = text.split("\n")
    in_certs = False

    cert_keywords = ["certified", "certification", "certificate", "aws", "google cloud",
                     "microsoft", "oracle", "coursera", "udemy", "nptel"]

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if re.match(r"^(certifications?|certificates?|achievements?|awards?|honours?|honors?|licenses?\s*and\s*certifications?)[\s:]*$", line.lower(), re.IGNORECASE):
            in_certs = True
            continue

        if in_certs and re.match(r"^(experience|projects?|skills|education)$", line.lower()):
            in_certs = False
            continue

        if in_certs or any(kw in line.lower() for kw in cert_keywords):
            if len(line) > 5 and len(line) < 200:
                certs.append(line[:200])

    return list(set(certs))[:10]


def extract_experience(text: str) -> List[Dict]:
    """Extract work experience entries."""
    experience = []
    lines = text.split("\n")
    in_exp = False
    current = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if re.match(r"^(work experience|professional experience|industry experience|experience|internships?|employment|work history|job experience)[\s:]*$", line.lower(), re.IGNORECASE):
            in_exp = True
            continue

        if in_exp and re.match(r"^(education|projects?|skills|certifications?)$", line.lower()):
            in_exp = False
            if current:
                experience.append(current)
            continue

        if in_exp:
            date_match = re.search(
                r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{4})[\s\-\u2013]+[\w\s,]+",
                line.lower()
            )
            role_kw = ["engineer", "developer", "analyst", "manager", "intern",
                       "lead", "architect", "scientist", "designer", "consultant", "specialist"]
            company_kw = ["ltd", "inc", "pvt", "technologies", "solutions",
                          "systems", "services", "corp", "labs", "studio", "group"]
            looks_like_role = (
                len(line) < 100 and line and line[0].isupper()
                and any(kw in line.lower() for kw in role_kw)
            )
            looks_like_company = any(kw in line.lower() for kw in company_kw)

            if date_match:
                if current:
                    current["duration"] = line[:80]
            elif looks_like_role:
                if current:
                    experience.append(current)
                current = {"role": line[:100], "company": "", "duration": ""}
            elif looks_like_company and current and not current["company"]:
                current["company"] = line[:100]
            elif current and re.search(r"\d{4}", line):
                current["duration"] = line[:50]

    if current:
        experience.append(current)

    return experience[:5]

# ── Main Parse Function ──────────────────────────────────────

def parse_resume_file(file, file_type: str) -> Dict:
    """
    Main entry point: extract and parse a resume file.
    Returns structured data dictionary.
    """
    # Read file bytes
    file_bytes = file.read()

    # Step 1: Extract raw text based on file type
    if file_type == "pdf":
        raw_text = extract_text_from_pdf(file_bytes)
    elif file_type == "docx":
        raw_text = extract_text_from_docx(file_bytes)
    else:
        raw_text = file_bytes.decode("utf-8", errors="ignore")

    if not raw_text.strip():
        logger.warning("Empty text extracted from resume")
        raw_text = "(Could not extract text from file)"

    # Step 2: Preprocess
    clean_text = preprocess_text(raw_text)

    # Step 3: Extract structured fields
    skills = extract_skills(clean_text)
    technologies = extract_technologies(skills)
    projects = extract_projects(raw_text)  # use raw text for case sensitivity
    education = extract_education(raw_text)
    certifications = extract_certifications(raw_text)
    experience = extract_experience(raw_text)

    logger.info(f"Extracted: {len(skills)} skills, {len(projects)} projects, {len(education)} education entries")

    return {
        "raw_text": raw_text[:5000],  # store first 5000 chars
        "skills": skills,
        "technologies": technologies,
        "projects": projects,
        "education": education,
        "certifications": certifications,
        "experience": experience,
    }
