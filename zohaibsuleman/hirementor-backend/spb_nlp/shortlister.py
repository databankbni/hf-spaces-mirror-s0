"""
Shortlister - Filter candidates based on match scores and thresholds.
Supports per-job threshold, configurable filters, and ranking.
"""

from typing import List, Optional

from spb_nlp.models import MatchResult, ShortlistResult, Job


class Shortlister:
    """
    Candidate shortlisting engine.

    Takes MatchResults and filters/ranks candidates based on:
    - Minimum match score threshold (per-job or global)
    - Experience requirements
    - GPA requirements
    - Skill coverage
    """

    def shortlist_for_job(
        self,
        match_results: List[MatchResult],
        job: Optional[Job] = None,
        threshold: Optional[float] = None,
        min_experience_years: float = 0.0,
        min_gpa: float = 0.0,
        top_k: Optional[int] = None,
    ) -> ShortlistResult:
        """
        Shortlist candidates for a single job.

        Args:
            match_results: Match results for all candidates.
            job: Job object (used for threshold if not explicitly given).
            threshold: Minimum match score (overrides job.matching_threshold).
            min_experience_years: Minimum years of experience required.
            min_gpa: Minimum GPA required.
            top_k: If set, only keep top K candidates.

        Returns:
            ShortlistResult with shortlisted and rejected lists.
        """
        effective_threshold = (
            threshold if threshold is not None
            else (job.matching_threshold if job else 50.0)
        )

        shortlisted: List[MatchResult] = []
        rejected: List[MatchResult] = []

        for mr in match_results:
            passes = True
            reasons = []

            if mr.match_score < effective_threshold:
                passes = False
                reasons.append(f"Score {mr.match_score:.1f} < threshold {effective_threshold}")

            if min_experience_years > 0 and not mr.experience_match:
                passes = False
                reasons.append(f"Experience < {min_experience_years} yr(s)")

            if min_gpa > 0 and not mr.gpa_match:
                passes = False
                reasons.append(f"GPA < {min_gpa}")

            if passes:
                shortlisted.append(mr)
            else:
                rejected.append(mr)

        # Sort shortlisted by match_score descending
        shortlisted.sort(key=lambda r: r.match_score, reverse=True)

        if top_k and len(shortlisted) > top_k:
            shortlisted = shortlisted[:top_k]

        job_id = job.job_id if job else (match_results[0].job_id if match_results else "")
        job_title = job.title if job else (match_results[0].job_title if match_results else "")

        return ShortlistResult(
            job_id=job_id,
            job_title=job_title,
            total_applicants=len(match_results),
            shortlisted=shortlisted,
            rejected=rejected,
            threshold_used=effective_threshold,
        )

    def shortlist_multiple_jobs(
        self,
        job_results_map: dict,
        threshold: Optional[float] = None,
        top_k_per_job: Optional[int] = None,
    ) -> List[ShortlistResult]:
        """
        Shortlist candidates across multiple jobs.

        Args:
            job_results_map: Dict mapping Job -> List[MatchResult]
            threshold: Override threshold for all jobs.
            top_k_per_job: Max shortlisted per job.

        Returns:
            List of ShortlistResult, one per job.
        """
        results = []
        for job, match_results in job_results_map.items():
            sr = self.shortlist_for_job(
                match_results=match_results,
                job=job,
                threshold=threshold,
                top_k=top_k_per_job,
            )
            results.append(sr)
        return results

    def get_shortlist_summary(self, shortlist_result: ShortlistResult) -> dict:
        """Return a human-readable summary dict of a shortlist result."""
        return {
            "job_title": shortlist_result.job_title,
            "total_applicants": shortlist_result.total_applicants,
            "shortlisted_count": len(shortlist_result.shortlisted),
            "rejected_count": len(shortlist_result.rejected),
            "threshold_used": shortlist_result.threshold_used,
            "top_candidate": (
                {
                    "name": "",
                    "score": shortlist_result.shortlisted[0].match_score,
                    "skills": shortlist_result.shortlisted[0].matching_skills,
                }
                if shortlist_result.shortlisted else None
            ),
        }
