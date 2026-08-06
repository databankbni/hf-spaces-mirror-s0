"""Data models matching the Kotlin/Android SPB app structures."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Student:
    student_id: str = ""
    full_name: str = ""
    email: str = ""
    phone: str = ""
    university: str = ""
    degree: str = ""
    major: str = ""
    graduation_year: int = 0
    cgpa: float = 0.0
    skills: List[str] = field(default_factory=list)
    certifications: List[str] = field(default_factory=list)
    cv_url: str = ""
    resume_text: str = ""
    profile_complete: bool = False


@dataclass
class Job:
    job_id: str = ""
    company_id: str = ""
    company_name: str = ""
    title: str = ""
    type: str = ""  # "job" or "internship"
    description: str = ""
    requirements: List[str] = field(default_factory=list)
    qualifications: List[str] = field(default_factory=list)
    required_skills: List[str] = field(default_factory=list)
    required_education: str = "Any"
    minimum_gpa: float = 0.0
    minimum_experience_years: float = 0.0
    location: str = ""
    salary: str = ""
    deadline: int = 0
    status: str = "active"
    matching_threshold: float = 50.0


@dataclass
class CVParseResult:
    """Structured output from CV parsing."""
    candidate_name: str = ""
    email: str = ""
    phone: str = ""
    skills: List[str] = field(default_factory=list)
    experience: str = ""
    education: str = ""
    gpa: float = 0.0
    years_of_experience: float = 0.0
    certifications: List[str] = field(default_factory=list)
    projects: List[str] = field(default_factory=list)
    summary: str = ""
    raw_text: str = ""


@dataclass
class MatchResult:
    """Result of matching a CV against a job."""
    job_id: str = ""
    job_title: str = ""
    company_name: str = ""
    match_score: float = 0.0
    meets_threshold: bool = False
    matching_skills: List[str] = field(default_factory=list)
    missing_skills: List[str] = field(default_factory=list)
    experience_match: bool = False
    gpa_match: bool = False
    education_match: bool = False
    cosine_similarity: float = 0.0
    recommendations: List[str] = field(default_factory=list)
    detailed_analysis: str = ""
    skill_score: float = 0.0
    experience_score: float = 0.0
    education_score: float = 0.0
    extra_score: float = 0.0
    context_score: float = 0.0


@dataclass
class SkillMatch:
    """Skill-based match for job recommendation."""
    job_id: str = ""
    job_title: str = ""
    company_name: str = ""
    match_score: float = 0.0
    matching_skills: List[str] = field(default_factory=list)
    missing_skills: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    salary: str = ""
    location: str = ""
    cosine_similarity: float = 0.0


@dataclass
class ShortlistResult:
    """Result of the shortlisting process for a single job."""
    job_id: str = ""
    job_title: str = ""
    total_applicants: int = 0
    shortlisted: List[MatchResult] = field(default_factory=list)
    rejected: List[MatchResult] = field(default_factory=list)
    threshold_used: float = 50.0


@dataclass
class JobRecommendation:
    """Job recommendation for a student."""
    job_id: str = ""
    job_title: str = ""
    company_name: str = ""
    match_score: float = 0.0
    matching_skills: List[str] = field(default_factory=list)
    missing_skills: List[str] = field(default_factory=list)
    reason: str = ""
    salary: str = ""
    location: str = ""
