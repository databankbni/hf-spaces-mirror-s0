"""
Recommender - Job recommendation engine for students.
Generates personalized job recommendations using:
- Semantic similarity (cosine)
- Skill overlap
- Education / experience fit
- Knowledge of similar profiles
"""

from typing import List, Optional

from spb_nlp.models import (
    Student, Job, CVParseResult, SkillMatch, JobRecommendation,
)
from spb_nlp.semantic_matcher import SemanticMatcher


class JobRecommender:
    """
    Recommends jobs to students based on their profile / parsed CV.

    Supports:
    - Skill-based matching (keyword overlap)
    - Semantic similarity (cosine)
    - Hybrid scoring (weighted combination)
    - "Similar students" collaborative-style signal
    """

    def __init__(self, semantic_matcher: Optional[SemanticMatcher] = None):
        self._matcher = semantic_matcher or SemanticMatcher()

    # ------------------------------------------------------------------ #
    #  Primary recommendation methods
    # ------------------------------------------------------------------ #

    def recommend_for_student(
        self,
        student: Student,
        jobs: List[Job],
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> List[JobRecommendation]:
        """
        Generate job recommendations for a student.

        Args:
            student: Student profile (skills, major, degree, etc.)
            jobs: All active jobs to recommend from.
            top_k: Maximum number of recommendations.
            min_score: Minimum match score threshold.

        Returns:
            Ranked list of JobRecommendations.
        """
        scores = []
        for job in jobs:
            rec = self._score_job_for_student(student, job)
            if rec.match_score >= min_score:
                scores.append(rec)

        scores.sort(key=lambda r: r.match_score, reverse=True)
        return scores[:top_k]

    def recommend_for_cv(
        self,
        cv_result: CVParseResult,
        jobs: List[Job],
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> List[JobRecommendation]:
        """
        Generate job recommendations from a parsed CV (no student profile needed).

        Args:
            cv_result: Parsed CV output.
            jobs: All active jobs.
            top_k: Max recommendations.
            min_score: Minimum match score.

        Returns:
            Ranked list of JobRecommendations.
        """
        from spb_nlp.models import Student

        student = Student(
            skills=cv_result.skills,
            certifications=cv_result.certifications,
        )
        scores = []
        for job in jobs:
            rec = self._score_job_for_student(student, job, cv_result)
            if rec.match_score >= min_score:
                scores.append(rec)

        scores.sort(key=lambda r: r.match_score, reverse=True)
        return scores[:top_k]

    # ------------------------------------------------------------------ #
    #  Internal scoring
    # ------------------------------------------------------------------ #

    def _score_job_for_student(
        self,
        student: Student,
        job: Job,
        cv_result: Optional[CVParseResult] = None,
    ) -> JobRecommendation:
        """Compute recommendation score for a (student, job) pair.

        Uses the same scoring formula as SemanticMatcher.match_cv_to_job:
        40% skill overlap + 25% BERT semantic + 15% experience + 10% education + 10% extra.
        """
        # Build a CVParseResult from student data to reuse matcher logic
        cv = CVParseResult(
            candidate_name=student.full_name,
            email=student.email,
            skills=student.skills,
            experience=cv_result.experience if cv_result else "",
            education=f"{student.degree} in {student.major}" if student.degree or student.major
                      else cv_result.education if cv_result else "",
            gpa=student.cgpa,
            years_of_experience=cv_result.years_of_experience if cv_result else 0.0,
            certifications=student.certifications,
            projects=cv_result.projects if cv_result else [],
        )

        match = self._matcher.match_cv_to_job(cv, job)
        matching = match.matching_skills
        missing = match.missing_skills

        reason_parts = []
        if matching:
            reason_parts.append(f"skills: {', '.join(matching[:3])}")
        if job.location and student.university:
            reason_parts.append(f"location: {job.location}")
        if student.major and (student.major.lower() in job.title.lower() or
                              student.major.lower() in job.description.lower()):
            reason_parts.append(f"relevant: {student.major}")
        reason = " | ".join(reason_parts) if reason_parts else "general fit"

        recs = []
        if missing:
            recs.append(f"Learn: {', '.join(missing[:3])}")

        return JobRecommendation(
            job_id=job.job_id,
            job_title=job.title,
            company_name=job.company_name,
            match_score=match.match_score,
            matching_skills=matching,
            missing_skills=missing,
            reason=reason,
            salary=job.salary,
            location=job.location,
        )

    # ------------------------------------------------------------------ #
    #  Utility
    # ------------------------------------------------------------------ #

    def rerank_by_profile_change(
        self,
        recommendations: List[JobRecommendation],
        new_skills: List[str],
    ) -> List[JobRecommendation]:
        """Re-rank recommendations when a student adds new skills."""
        new_set = {s.lower() for s in new_skills}
        for rec in recommendations:
            rec_set = {s.lower() for s in rec.matching_skills}
            added = len(new_set & rec_set)
            rec.match_score = min(rec.match_score + added * 5.0, 100.0)
        recommendations.sort(key=lambda r: r.match_score, reverse=True)
        return recommendations

    def filter_by_location(
        self,
        recommendations: List[JobRecommendation],
        location: str,
    ) -> List[JobRecommendation]:
        """Filter recommendations by location."""
        loc_lower = location.lower()
        return [r for r in recommendations if loc_lower in r.location.lower()]

    def filter_by_salary_range(
        self,
        recommendations: List[JobRecommendation],
        min_salary: float = 0.0,
        max_salary: float = float("inf"),
    ) -> List[JobRecommendation]:
        """Filter by salary range (basic string parsing)."""
        import re

        def _parse_salary(s: str) -> float:
            nums = re.findall(r"\d+", s.replace(",", ""))
            return float(nums[0]) if nums else 0.0

        filtered = []
        for r in recommendations:
            sal = _parse_salary(r.salary)
            if min_salary <= sal <= max_salary:
                filtered.append(r)
        return filtered
