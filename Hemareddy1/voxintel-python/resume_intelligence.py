"""
resume_intelligence.py
-----------------------
Resume Intelligence Engine for VoxIntel Phase 1.

Analyzes a parsed resume and produces a structured intelligence report:
  - candidateLevel  : Beginner / Junior / Intermediate / Advanced / Senior
  - skillStrength   : 0–100
  - experienceStrength : 0–100
  - projectStrength : 0–100
  - readinessScore  : 0–100 (weighted composite)
  - recommendedDifficulty : Beginner / Intermediate / Advanced / Expert
  - strengths       : top skills/areas
  - improvementAreas: gaps found in the resume

Design:
  - Pure Python, no external ML model required.
  - Works from the already-parsed resume dict produced by resume_parser.py.
  - All scoring is deterministic and reproducible.
  - Does NOT modify the parsed dict — returns a separate intelligence dict.
"""

import re
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

# ── Skill Tier Classification ────────────────────────────────
# Ordered lists for scoring skill depth. Tier 1 = foundational, Tier 3 = advanced.

SKILL_TIERS = {
    "tier3_advanced": [
        "kubernetes", "terraform", "ansible", "kafka", "spark", "hadoop",
        "machine learning", "deep learning", "nlp", "computer vision",
        "langchain", "hugging face", "pytorch", "tensorflow",
        "microservices", "graphql", "rust", "scala", "go",
        "system design", "distributed systems", "elasticsearch",
        "redis", "cassandra", "dynamodb",
        "ci/cd", "github actions", "jenkins",
    ],
    "tier2_mid": [
        "react", "nextjs", "vue", "angular", "node.js", "nodejs", "express",
        "django", "flask", "fastapi", "spring", "nestjs",
        "mongodb", "postgresql", "mysql", "docker",
        "aws", "gcp", "azure", "typescript",
        "redux", "graphql", "rest api",
        "python", "java", "c++", "kotlin",
        "pandas", "numpy", "sklearn", "scikit-learn",
    ],
    "tier1_basic": [
        "html", "css", "javascript", "git", "github", "sqlite",
        "bootstrap", "tailwind", "sass", "bash",
        "postman", "figma", "vs code", "linux",
    ],
}

# ── Advanced project indicators ───────────────────────────────

PROJECT_COMPLEXITY_KEYWORDS = {
    "high": [
        "microservice", "distributed", "scalable", "kubernetes", "kafka",
        "machine learning", "deep learning", "nlp", "ai", "llm", "transformer",
        "real-time", "websocket", "event-driven", "cqrs", "saga",
        "multi-tenant", "sharding", "replication", "load balancing",
        "pipeline", "recommender", "neural", "computer vision",
    ],
    "medium": [
        "api", "authentication", "oauth", "jwt", "rest", "crud",
        "dashboard", "analytics", "notification", "payment",
        "search", "filter", "pagination", "caching", "redis",
        "docker", "ci/cd", "deployment", "automated",
    ],
    "low": [
        "portfolio", "todo", "weather", "calculator", "blog",
        "landing page", "static", "basic", "simple",
    ],
}

# ── Key domain areas for improvement gap analysis ─────────────

DOMAIN_AREAS = {
    "Cloud": ["aws", "gcp", "azure", "cloud", "ec2", "lambda", "s3", "heroku", "vercel"],
    "DevOps": ["docker", "kubernetes", "ci/cd", "jenkins", "github actions", "terraform", "ansible"],
    "Testing": ["unit test", "jest", "pytest", "mocha", "cypress", "tdd", "bdd", "testing"],
    "System Design": ["system design", "scalability", "microservice", "distributed", "load balancing"],
    "AI/ML": ["machine learning", "deep learning", "tensorflow", "pytorch", "sklearn", "nlp", "ai"],
    "Databases": ["mongodb", "postgresql", "mysql", "redis", "sqlite", "database", "sql"],
    "Security": ["authentication", "oauth", "jwt", "https", "encryption", "xss", "csrf", "security"],
    "Frontend": ["react", "vue", "angular", "html", "css", "javascript", "typescript", "nextjs"],
    "Backend": ["node.js", "express", "django", "flask", "fastapi", "spring", "rest api"],
    "Algorithms": ["data structures", "algorithms", "leetcode", "competitive", "sorting", "graph"],
}


# ── Scoring helpers ───────────────────────────────────────────

def _flatten_text(parsed: Dict) -> str:
    """Combine all resume text fields into one searchable string."""
    parts = []
    parts.extend(parsed.get("skills", []))
    parts.extend(parsed.get("technologies", []))
    parts.extend(parsed.get("certifications", []))

    for proj in parsed.get("projects", []):
        parts.append(proj.get("name", ""))
        parts.append(proj.get("description", ""))
        parts.extend(proj.get("technologies", []))

    for exp in parsed.get("experience", []):
        parts.append(exp.get("role", ""))
        parts.append(exp.get("company", ""))
        parts.append(exp.get("duration", ""))

    for edu in parsed.get("education", []):
        parts.append(edu.get("degree", ""))

    return " ".join(parts).lower()


def compute_skill_strength(parsed: Dict) -> int:
    """
    Score 0–100 for skill strength.

    Factors:
      - Total number of skills (breadth)
      - Tier weighting (tier3 > tier2 > tier1)
      - Cross-domain diversity bonus
    """
    skills = [s.lower() for s in parsed.get("skills", [])]
    technologies = [t.lower() for t in parsed.get("technologies", [])]
    all_skills = list(set(skills + technologies))

    if not all_skills:
        return 0

    tier3_count = sum(1 for s in all_skills if s in SKILL_TIERS["tier3_advanced"])
    tier2_count = sum(1 for s in all_skills if s in SKILL_TIERS["tier2_mid"])
    tier1_count = sum(1 for s in all_skills if s in SKILL_TIERS["tier1_basic"])

    # Weighted score: tier3=5pts, tier2=3pts, tier1=1pt
    raw_score = (tier3_count * 5) + (tier2_count * 3) + (tier1_count * 1)

    # Normalize: a strong senior has ~20+ weighted points → cap at 100
    normalized = min(100, int((raw_score / 25) * 100))

    # Diversity bonus: reward covering multiple domains
    domains_covered = 0
    flat = " ".join(all_skills)
    for domain_keywords in DOMAIN_AREAS.values():
        if any(kw in flat for kw in domain_keywords):
            domains_covered += 1

    diversity_bonus = min(15, domains_covered * 2)

    return min(100, normalized + diversity_bonus)


def _parse_experience_years(experience: List[Dict]) -> float:
    """
    Estimate total years of experience from the experience list.
    Tries to parse duration strings like "Jan 2022 - Dec 2023" or "2021-2023".
    Returns float years (best effort, 0 if unparseable).
    """
    total_months = 0

    for exp in experience:
        duration = exp.get("duration", "")
        if not duration:
            continue

        # Pattern: year ranges like 2021 - 2023 or 2021–2024
        years = re.findall(r"\b(20\d{2}|19\d{2})\b", duration)
        if len(years) >= 2:
            try:
                yr_start, yr_end = int(years[0]), int(years[-1])
                if yr_end >= yr_start:
                    total_months += (yr_end - yr_start) * 12
                    continue
            except ValueError:
                pass

        # Pattern: "X months" or "X years"
        month_match = re.search(r"(\d+)\s*months?", duration, re.IGNORECASE)
        year_match = re.search(r"(\d+)\s*years?", duration, re.IGNORECASE)
        if year_match:
            total_months += int(year_match.group(1)) * 12
        if month_match:
            total_months += int(month_match.group(1))

        # If single year mentioned and no range, assume ~12 months
        if not years and not month_match and not year_match:
            single_year = re.search(r"\b(20\d{2})\b", duration)
            if single_year:
                total_months += 12

    return total_months / 12.0


def compute_experience_strength(parsed: Dict) -> int:
    """
    Score 0–100 for experience strength.

    Factors:
      - Years of experience
      - Number of distinct roles
      - Certifications
      - Technologies used across experience
    """
    experience = parsed.get("experience", [])
    certifications = parsed.get("certifications", [])

    years = _parse_experience_years(experience)
    role_count = len(experience)
    cert_count = len(certifications)

    # Year-based score: 0 yrs=0, 1yr=15, 2yrs=30, 3yrs=45, 5yrs=70, 8+yrs=95
    if years == 0:
        year_score = 5 if role_count > 0 else 0  # has entries but couldn't parse dates
    elif years < 1:
        year_score = 15
    elif years < 2:
        year_score = 30
    elif years < 3:
        year_score = 45
    elif years < 5:
        year_score = 60
    elif years < 8:
        year_score = 78
    else:
        year_score = 92

    # Role diversity bonus
    role_bonus = min(10, role_count * 3)

    # Certification bonus
    cert_bonus = min(8, cert_count * 3)

    return min(100, year_score + role_bonus + cert_bonus)


def compute_project_strength(parsed: Dict) -> int:
    """
    Score 0–100 for project strength.

    Factors:
      - Number of projects
      - Complexity indicators in project descriptions/technologies
      - Cloud/DevOps usage
      - AI/ML usage
      - Diversity of tech across projects
    """
    projects = parsed.get("projects", [])

    if not projects:
        return 0

    # Base from count: 1=10, 2=20, 3=30, 4+=40 (capped)
    count_score = min(40, len(projects) * 10)

    complexity_score = 0
    for proj in projects:
        desc = (proj.get("description", "") + " " + proj.get("name", "")).lower()
        tech_text = " ".join(proj.get("technologies", [])).lower()
        combined = desc + " " + tech_text

        # Check complexity indicators
        high_matches = sum(1 for kw in PROJECT_COMPLEXITY_KEYWORDS["high"] if kw in combined)
        med_matches = sum(1 for kw in PROJECT_COMPLEXITY_KEYWORDS["medium"] if kw in combined)

        proj_score = min(20, (high_matches * 5) + (med_matches * 2))
        complexity_score += proj_score

    complexity_score = min(40, complexity_score)

    # Tech diversity across ALL projects
    all_proj_techs = set()
    for proj in projects:
        all_proj_techs.update(t.lower() for t in proj.get("technologies", []))

    diversity_score = min(20, len(all_proj_techs) * 2)

    return min(100, count_score + complexity_score + diversity_score)


def compute_readiness_score(skill_strength: int, experience_strength: int, project_strength: int) -> int:
    """
    Weighted composite:
      - Skills:     35%
      - Experience: 40%
      - Projects:   25%
    """
    score = (
        (skill_strength * 0.35) +
        (experience_strength * 0.40) +
        (project_strength * 0.25)
    )
    return min(100, int(round(score)))


def infer_candidate_level(
    readiness_score: int,
    skill_strength: int,
    experience_strength: int,
    project_strength: int,
    parsed: Dict,
) -> str:
    """
    Infer candidate level from holistic signals — NOT just years of experience.

    Uses:
      - Readiness score bands
      - Skill tier distribution
      - Project complexity
      - Years of experience (parsed)
    """
    years = _parse_experience_years(parsed.get("experience", []))

    skills = [s.lower() for s in parsed.get("skills", []) + parsed.get("technologies", [])]
    tier3 = sum(1 for s in skills if s in SKILL_TIERS["tier3_advanced"])

    # Weight the decision
    if readiness_score >= 82 or (years >= 5 and tier3 >= 5):
        return "Senior"
    elif readiness_score >= 65 or (years >= 3 and tier3 >= 3):
        return "Advanced"
    elif readiness_score >= 45 or (years >= 1 and (skill_strength >= 40 or project_strength >= 40)):
        return "Intermediate"
    elif readiness_score >= 25 or (skill_strength >= 20 or project_strength >= 20):
        return "Junior"
    else:
        return "Beginner"


def infer_recommended_difficulty(readiness_score: int, candidate_level: str) -> str:
    """
    Map readiness score + level to interview difficulty.
    Returns: Beginner | Intermediate | Advanced | Expert
    """
    if candidate_level in ("Senior",) or readiness_score >= 80:
        return "Expert"
    elif candidate_level in ("Advanced",) or readiness_score >= 60:
        return "Advanced"
    elif candidate_level in ("Intermediate",) or readiness_score >= 35:
        return "Intermediate"
    else:
        return "Beginner"


def identify_strengths(parsed: Dict, skill_strength: int) -> List[str]:
    """
    Return top skill/technology names that represent the candidate's strengths.
    Prioritizes tier3 skills, then tier2 skills that appear in projects.
    """
    skills = [s.lower() for s in parsed.get("skills", []) + parsed.get("technologies", [])]

    # Project-backed skills (appear in at least one project tech stack)
    project_techs = set()
    for proj in parsed.get("projects", []):
        for t in proj.get("technologies", []):
            project_techs.add(t.lower())

    strengths = []

    # Tier 3 first (advanced skills are always strengths)
    for s in skills:
        if s in SKILL_TIERS["tier3_advanced"] and s not in strengths:
            strengths.append(s)

    # Project-backed tier 2 skills
    for s in skills:
        if s in SKILL_TIERS["tier2_mid"] and s in project_techs and s not in strengths:
            strengths.append(s)

    # Top skills by frequency across project descriptions (if still < 5)
    if len(strengths) < 5:
        for s in skills:
            if s in SKILL_TIERS["tier2_mid"] and s not in strengths:
                strengths.append(s)

    # Normalize display names to title-case-friendly versions
    display_map = {
        "node.js": "Node.js", "nodejs": "Node.js", "react": "React",
        "python": "Python", "javascript": "JavaScript", "typescript": "TypeScript",
        "mongodb": "MongoDB", "postgresql": "PostgreSQL", "mysql": "MySQL",
        "docker": "Docker", "aws": "AWS", "gcp": "GCP", "azure": "Azure",
        "machine learning": "Machine Learning", "deep learning": "Deep Learning",
        "django": "Django", "flask": "Flask", "fastapi": "FastAPI",
        "tensorflow": "TensorFlow", "pytorch": "PyTorch",
        "redis": "Redis", "kubernetes": "Kubernetes",
    }

    formatted = [display_map.get(s, s.title()) for s in strengths[:8]]
    return formatted


def identify_improvement_areas(parsed: Dict) -> List[str]:
    """
    Identify domains that are weak or absent from the resume.
    Returns up to 5 improvement areas.
    """
    flat = _flatten_text(parsed)
    gaps = []

    for domain, keywords in DOMAIN_AREAS.items():
        covered = any(kw in flat for kw in keywords)
        if not covered:
            gaps.append(domain)

    return gaps[:5]


# ── Main Intelligence Generator ───────────────────────────────

def generate_intelligence(parsed: Dict) -> Dict:
    """
    Main entry point.
    Takes the parsed resume dict (output of resume_parser.parse_resume_file)
    and returns an intelligence dict.

    Returns:
    {
        "candidateLevel": str,
        "skillStrength": int,
        "experienceStrength": int,
        "projectStrength": int,
        "readinessScore": int,
        "recommendedDifficulty": str,
        "strengths": [str],
        "improvementAreas": [str]
    }
    """
    try:
        skill_strength = compute_skill_strength(parsed)
        experience_strength = compute_experience_strength(parsed)
        project_strength = compute_project_strength(parsed)
        readiness_score = compute_readiness_score(skill_strength, experience_strength, project_strength)

        candidate_level = infer_candidate_level(
            readiness_score, skill_strength, experience_strength, project_strength, parsed
        )
        recommended_difficulty = infer_recommended_difficulty(readiness_score, candidate_level)

        strengths = identify_strengths(parsed, skill_strength)
        improvement_areas = identify_improvement_areas(parsed)

        intelligence = {
            "candidateLevel": candidate_level,
            "skillStrength": skill_strength,
            "experienceStrength": experience_strength,
            "projectStrength": project_strength,
            "readinessScore": readiness_score,
            "recommendedDifficulty": recommended_difficulty,
            "strengths": strengths,
            "improvementAreas": improvement_areas,
        }

        logger.info(
            f"Intelligence generated: level={candidate_level}, "
            f"readiness={readiness_score}, difficulty={recommended_difficulty}"
        )
        return intelligence

    except Exception as e:
        logger.error(f"Intelligence generation error: {e}")
        # Return safe defaults so the rest of the system doesn't break
        return {
            "candidateLevel": "Intermediate",
            "skillStrength": 0,
            "experienceStrength": 0,
            "projectStrength": 0,
            "readinessScore": 0,
            "recommendedDifficulty": "Intermediate",
            "strengths": [],
            "improvementAreas": [],
        }
