"""
Semantic Matcher - Embedding-based cosine similarity between
CVs / student profiles and job descriptions.

Uses sentence-transformers for dense embeddings (optional - falls back
to pure-Python skill-based matching if not installed).
"""

import math
import re
from typing import List, Optional, Tuple

from spb_nlp.models import (
    CVParseResult, Job, MatchResult,
)
from spb_nlp.utils import preprocess_for_embedding, extract_skills, skills_in_same_cluster, estimate_years_of_experience

# Curated-cluster membership (e.g. "kotlin" <-> "android development") is a
# stronger, auditable signal than raw short-phrase cosine similarity, which is
# too noisy to tell "kotlin~android" (should credit) apart from "tensorflow~
# django" (coincidental) at the single-phrase level. Cluster credit is high
# but not automatic-full-marks — an inferred skill is still not a confirmed one.
CLUSTER_CREDIT = 0.65

# Skill-level semantic matching thresholds (cosine similarity between two short
# skill phrases, e.g. "machine learning" vs "python"). Calibrated empirically
# against ~25 hand-checked skill pairs: clearly unrelated pairs (e.g. "cooking"
# vs "docker") sit ~0.10-0.15, marginal/coincidental pairs (e.g. "tensorflow"
# vs "django" — both "Python-adjacent" but not actually related) sit ~0.30-0.36,
# and genuinely related pairs (e.g. "sql" vs "postgresql") sit ~0.45-0.55+.
# The floor is set above the marginal-noise band so coincidental topical
# overlap doesn't get credited as a real skill relationship.
SKILL_SIM_FLOOR = 0.33   # below this: no credit, treated as unrelated
SKILL_SIM_CEIL = 0.62    # at/above this: full credit, treated as effectively equivalent

# Holistic CV-vs-job document similarity thresholds. Any two resume/job-posting
# texts share generic boilerplate phrasing, so there's a "noise floor" around
# 0.40 even for completely unrelated fields — only similarity above that is signal.
DOC_SIM_FLOOR = 0.40
DOC_SIM_CEIL = 0.75

# ------------------------------------------------------------------ #
#  Optional dependency: sentence-transformers + numpy + sklearn
# ------------------------------------------------------------------ #
_HAS_EMBEDDINGS = False
try:
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity
    _HAS_EMBEDDINGS = True
except ImportError:
    pass


class SemanticMatcher:
    """
    Semantic matching engine.

    When sentence-transformers + numpy + sklearn are installed, uses
    BERT-based dense vector embeddings (all-MiniLM-L6-v2) + cosine similarity
    for deep semantic matching.

    Otherwise falls back to a pure-Python keyword + character n-gram
    similarity (fast, reasonable accuracy).
    """

    _MODEL_NAME = "all-MiniLM-L6-v2"

    def __init__(self, model_name: str = _MODEL_NAME, lazy_load: bool = False):
        self._model_name = model_name
        self._model = None
        self._load_error = None
        if not lazy_load and _HAS_EMBEDDINGS:
            self._load_model()

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def match_cv_to_job(
        self,
        cv_result: CVParseResult,
        job: Job,
        threshold: Optional[float] = None,
    ) -> MatchResult:
        """Match parsed CV against a job posting.  See module docstring."""
        threshold = threshold if threshold is not None else job.matching_threshold

        # -- Skill matching: exact overlap + semantic (BERT) inference (60%) -- #
        # A candidate who only lists "machine learning" should still get partial
        # credit for a "python" requirement, because ML work implies Python —
        # that's context, and it's exactly what embedding similarity is for.
        # A candidate's declared skills list isn't the only place their skills show
        # up either — someone might describe using a tool in their experience or
        # project write-up without it making the formal skills list. Mirror the
        # job-side treatment below so neither side is judged on one field alone.
        cv_experience_text = " ".join([cv_result.experience or ""] + list(cv_result.projects))
        cv_implied_skills = {s.lower().strip() for s in extract_skills(cv_experience_text)}
        cv_skills_lower = {s.lower().strip() for s in cv_result.skills if s.strip()} | cv_implied_skills
        job_skills_lower = {s.lower().strip() for s in job.required_skills if s.strip()}

        # Requirements aren't only the formal `required_skills` list — companies
        # also bury them in free-text description/requirements/qualifications.
        implied_text = " ".join([job.description or ""] + list(job.requirements) + list(job.qualifications))
        implied_skills = {s.lower().strip() for s in extract_skills(implied_text)}
        all_required = job_skills_lower | implied_skills

        # A required skill counts as an exact hit if it's either in the
        # candidate's extracted skill set (limited to the curated
        # SKILL_KEYWORDS vocabulary) OR literally present as a standalone
        # word/phrase anywhere in their resume text. The extracted-set path
        # alone means a required skill that simply isn't in that finite list
        # (e.g. a generic word like "programming") could only ever earn a
        # probabilistic BERT/cluster inference instead of the direct credit
        # it's actually earned when the CV states it in plain words —
        # keeping the system from being fully dependent on vocabulary
        # coverage for company-typed required skills specifically.
        cv_full_text_lower = ((cv_result.raw_text or "") + " " + cv_experience_text).lower()

        def _text_has_skill(text: str, skill: str) -> bool:
            if not text or not skill:
                return False
            return bool(re.search(r'(?<!\w)' + re.escape(skill) + r'(?!\w)', text))

        literal_hits = {req for req in all_required if _text_has_skill(cv_full_text_lower, req)}
        exact_hits = (cv_skills_lower & all_required) | literal_hits
        semantic_hits = {}  # required_skill -> (best_candidate_skill, similarity)
        remaining = all_required - exact_hits
        if remaining and cv_skills_lower:
            # Runs even without embeddings installed — curated cluster
            # matching alone still catches well-known skill relationships.
            semantic_hits = self._semantic_skill_matches(remaining, cv_skills_lower)

        total_required = len(all_required) or 1
        semantic_credit = sum(credit for _, credit in semantic_hits.values())
        skill_ratio = min((len(exact_hits) + semantic_credit) / total_required, 1.0)

        # Meeting every requirement once is worth the bulk of the 60% (54 pts),
        # but two candidates who both "just meet" a requirement aren't
        # necessarily equally qualified — someone who covers a required skill
        # with three related tools (e.g. C, C++, and Python for a
        # "programming" requirement) has demonstrably deeper coverage than
        # someone who covers it with exactly one. Reward that depth with a
        # small bonus, separate from and on top of the pass/fail ratio.
        reinforcing_extra = self._count_reinforcing_skills(all_required, cv_skills_lower)
        depth_bonus = min(reinforcing_extra * 1.5, 6.0)
        skill_score = min(skill_ratio * 54.0 + depth_bonus, 60.0)  # Skills — 60%

        # For the API-facing report, only surface skills against the company's
        # explicit required_skills list (implied_skills are an internal scoring aid).
        matching_skills = sorted((cv_skills_lower & job_skills_lower) | (set(semantic_hits) & job_skills_lower) | (literal_hits & job_skills_lower))
        missing_skills = sorted(job_skills_lower - set(matching_skills))

        # -- Holistic CV-vs-job context similarity via BERT (10%) ------------- #
        # Captures tone/domain alignment beyond discrete skills (e.g. the job
        # description's overall subject matter vs the candidate's experience).
        cos_sim = self._compute_similarity(cv_result, job)
        doc_ratio = self._clamp((cos_sim - DOC_SIM_FLOOR) / (DOC_SIM_CEIL - DOC_SIM_FLOOR))
        bert_score = doc_ratio * 10.0

        # -- Experience match (15% weight) -------------------------------- #
        # Tied to what the job actually asks for, not an absolute years count:
        # a job that never states a years requirement falls back to a fixed
        # scale (0 years is the norm for students, not a red flag here), but
        # once a job *does* say e.g. "2+ years", meeting that bar is worth
        # more than merely having "some" experience, and exceeding it earns a
        # capped bonus rather than an unbounded reward for raw years.
        # A stated minimum is only a hard requirement when the company
        # explicitly sets it (job.minimum_experience_years, a structured
        # field — same pattern as minimum_gpa/required_education). Free text
        # like "2 years experience in teaching" inside the description or
        # requirements list still *informs the score* (so weighting stays
        # smart for jobs posted before this field existed), but it never by
        # itself causes an auto-reject — a prose mention is too easy to
        # false-positive on to gate an application on it.
        explicit_min_years = job.minimum_experience_years or 0.0
        implied_required_years = estimate_years_of_experience(
            " ".join([job.description or ""] + list(job.requirements))
        )
        required_years = explicit_min_years if explicit_min_years > 0 else implied_required_years
        yr = cv_result.years_of_experience
        experience_match_bool = True if explicit_min_years <= 0 else (yr >= explicit_min_years)
        if required_years <= 0:
            if yr >= 5.0:
                exp_score = 15.0
            elif yr >= 2.0:
                exp_score = 12.0
            elif yr >= 1.0:
                exp_score = 9.0
            elif yr > 0:
                exp_score = 5.5
            else:
                exp_score = 3.0  # baseline — "no experience yet" is the norm, not a penalty
        else:
            # A stated requirement is a floor, not a ceiling — meeting it
            # earns a strong 80% baseline (never harshly penalized for
            # "just" meeting what was asked), and the remaining 20% scales
            # with how far *past* it the candidate is, up to a reasonable
            # excess (one more full requirement's-worth of years), so two
            # candidates who both clear the bar — e.g. 3 vs 4 years against
            # a 2-year requirement — still rank differently instead of
            # tying at a flat "full marks". Falling short scales down
            # proportionally instead of cliff-dropping to zero.
            if yr >= required_years:
                excess = yr - required_years
                bonus_range = max(required_years, 2.0)
                bonus_ratio = min(excess / bonus_range, 1.0)
                exp_score = 15.0 * (0.8 + 0.2 * bonus_ratio)
            else:
                exp_score = max(3.0, 15.0 * (yr / required_years))

        # -- Education (10% weight) --------------------------------------- #
        def _has_word(text: str, words) -> bool:
            return any(re.search(r'(?<!\w)' + re.escape(w) + r'(?!\w)', text) for w in words)

        EDU_LEVELS = {
            "phd": 4, "ph.d.": 4, "doctorate": 4,
            "master": 3, "m.s.": 3, "m.a.": 3, "m.tech": 3, "mba": 3, "mcom": 3, "msc": 3, "m.sc": 3, "ms": 3, "ma": 3,
            "bachelor": 2, "b.s.": 2, "b.a.": 2, "b.tech": 2, "b.e.": 2, "bba": 2,
            "bcom": 2, "bsc": 2, "b.sc": 2, "bs": 2, "ba": 2, "b.eng": 2, "beng": 2,
            "high school": 1, "highschool": 1, "secondary school": 1, "intermediate": 1,
            "hssc": 1, "matric": 1, "matriculation": 1, "a-level": 1, "a level": 1,
            "diploma": 1, "associate degree": 1,
        }

        def _edu_level(text: str) -> int:
            if not text:
                return 0
            text_lower = text.lower()
            for word, level in sorted(EDU_LEVELS.items(), key=lambda kv: -kv[1]):
                if _has_word(text_lower, [word]):
                    return level
            return 1  # some education mentioned, but not a recognized degree tier

        REQUIRED_EDU_LEVELS = {"any": 0, "": 0, "high school": 1, "bachelor": 2, "master": 3, "phd": 4}
        required_level = REQUIRED_EDU_LEVELS.get((job.required_education or "Any").strip().lower(), 0)
        candidate_level = _edu_level(cv_result.education)
        education_match_bool = candidate_level >= required_level

        if required_level == 0:
            # No specific requirement stated — reward the candidate's own
            # level on an absolute scale, same as before.
            edu_score = [0.0, 4.0, 6.0, 8.0, 10.0][candidate_level]
        else:
            # Same 80%-baseline-plus-proportional-bonus rule as Experience:
            # meeting "Bachelor minimum" earns a strong baseline, and each
            # degree tier above it (Master, PhD) earns a further slice of
            # the remaining 20%, so a Bachelor's and a PhD candidate against
            # the same "Bachelor minimum" job don't tie.
            if candidate_level >= required_level:
                excess_levels = candidate_level - required_level
                bonus_ratio = min(excess_levels / 2.0, 1.0)
                edu_score = 10.0 * (0.8 + 0.2 * bonus_ratio)
            else:
                edu_score = max(0.0, 10.0 * (candidate_level / required_level))

        # -- GPA (5% weight) ------------------------------------------------ #
        required_gpa = job.minimum_gpa or 0.0
        gpa_match_bool = True if required_gpa <= 0 else (cv_result.gpa >= required_gpa)
        if required_gpa <= 0:
            # No minimum stated — reward the candidate's own GPA on an
            # absolute scale, same as before.
            if cv_result.gpa >= 3.5:
                gpa_score = 5.0
            elif cv_result.gpa >= 3.0:
                gpa_score = 3.5
            elif cv_result.gpa >= 2.5:
                gpa_score = 2.0
            elif cv_result.gpa > 0:
                gpa_score = 1.0
            else:
                gpa_score = 0.0
        else:
            # Same 80%-baseline-plus-proportional-bonus rule: meeting the
            # stated minimum GPA earns a strong baseline, and the remaining
            # room up to a 4.0 scale earns a proportional bonus — so 3.4 and
            # 3.6 against a 3.0 minimum both score well but don't tie.
            if cv_result.gpa >= required_gpa:
                excess = cv_result.gpa - required_gpa
                bonus_range = max(4.0 - required_gpa, 0.5)
                bonus_ratio = min(excess / bonus_range, 1.0)
                gpa_score = 5.0 * (0.8 + 0.2 * bonus_ratio)
            else:
                gpa_score = max(0.0, 5.0 * (cv_result.gpa / required_gpa)) if cv_result.gpa > 0 else 0.0

        recs = []
        if semantic_hits:
            inferred = ", ".join(
                f"{req} (via your {cand} experience)" for req, (cand, _credit) in list(semantic_hits.items())[:3]
            )
            recs.append(f"Partially inferred from related skills: {inferred}")
        if missing_skills:
            recs.append(f"Consider learning: {', '.join(missing_skills[:3])}")
        if cv_result.gpa > 0 and cv_result.gpa < 2.5:
            recs.append("GPA below 2.5")
        if doc_ratio < 0.15 and skill_ratio < 0.2:
            recs.append("Profile needs significant upskilling for this role")

        # -- Final composite (0-100) ------------------------------------ #
        # Skills 60 | Experience 15 | Education 10 | Semantic(BERT) 10 | GPA 5
        total = skill_score + bert_score + exp_score + edu_score + gpa_score
        total = min(max(total, 0.0), 100.0)

        return MatchResult(
            job_id=job.job_id,
            job_title=job.title,
            company_name=job.company_name,
            match_score=round(total, 2),
            meets_threshold=total >= threshold,
            matching_skills=matching_skills,
            missing_skills=missing_skills,
            experience_match=experience_match_bool,
            gpa_match=gpa_match_bool,
            education_match=education_match_bool,
            cosine_similarity=round(cos_sim, 4),
            recommendations=recs,
            skill_score=round(skill_score, 2),
            experience_score=round(exp_score, 2),
            education_score=round(edu_score, 2),
            extra_score=round(gpa_score, 2),  # field name kept for API compatibility — now holds the GPA sub-score
            context_score=round(bert_score, 2),
            detailed_analysis=(
                f"Skills: {skill_score:.0f}/60 | Exp: {exp_score:.0f}/15 | "
                f"Edu: {edu_score:.0f}/10 | Semantic(BERT): {bert_score:.0f}/10 | "
                f"GPA: {gpa_score:.0f}/5"
                + (f" | Semantic matches: {len(semantic_hits)}" if semantic_hits else "")
            ),
        )

    @staticmethod
    def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
        return max(lo, min(hi, x))

    @classmethod
    def _skill_credit(cls, similarity: float) -> float:
        """Map a skill-pair cosine similarity to a 0-1 partial-match credit."""
        return cls._clamp((similarity - SKILL_SIM_FLOOR) / (SKILL_SIM_CEIL - SKILL_SIM_FLOOR))

    def _semantic_skill_matches(self, required_skills, candidate_skills):
        """
        For each required skill with no exact match, find the best-related
        candidate skill using two combined signals:
          1. Curated skill-family clusters (e.g. "kotlin" <-> "android
             development") — precise, but only covers common professional
             skill groups.
          2. BERT embedding cosine similarity — generalizes to any skill pair
             (e.g. "machine learning" -> "python"), but is noisier for short
             technical phrases.
        Returns {required_skill: (best_candidate_skill, credit)} where credit
        is a 0-1 partial-match strength, for pairs with credit > 0.
        """
        required_list = sorted(required_skills)
        candidate_list = sorted(candidate_skills)

        sim_matrix = None
        if self._model is None:
            self._load_model()
        if self._model is not None:
            try:
                req_emb = self._model.encode(required_list, normalize_embeddings=True)
                cand_emb = self._model.encode(candidate_list, normalize_embeddings=True)
                sim_matrix = cosine_similarity(req_emb, cand_emb)
            except Exception:
                sim_matrix = None

        hits = {}
        for i, req_skill in enumerate(required_list):
            best_credit = 0.0
            best_cand = None
            for j, cand_skill in enumerate(candidate_list):
                bert_credit = self._skill_credit(float(sim_matrix[i][j])) if sim_matrix is not None else 0.0
                cluster_credit = CLUSTER_CREDIT if skills_in_same_cluster(req_skill, cand_skill) else 0.0
                credit = max(bert_credit, cluster_credit)
                if credit > best_credit:
                    best_credit = credit
                    best_cand = cand_skill
            if best_cand is not None and best_credit > 0:
                hits[req_skill] = (best_cand, best_credit)
        return hits

    def _count_reinforcing_skills(self, all_required, cv_skills_lower) -> int:
        """
        For each required skill, count how many *additional* candidate skills
        relate to it beyond the single one needed to satisfy it (e.g. knowing
        C, C++, and Python when the job only asked for "programming" once).
        Uses the same BERT-similarity-or-cluster test as `_semantic_skill_matches`,
        just summing every match above the credit floor instead of keeping
        only the best one.
        """
        if not all_required or not cv_skills_lower:
            return 0
        req_list = sorted(all_required)
        cand_list = sorted(cv_skills_lower)

        sim_matrix = None
        if self._model is None:
            self._load_model()
        if self._model is not None:
            try:
                req_emb = self._model.encode(req_list, normalize_embeddings=True)
                cand_emb = self._model.encode(cand_list, normalize_embeddings=True)
                sim_matrix = cosine_similarity(req_emb, cand_emb)
            except Exception:
                sim_matrix = None

        total_extra = 0
        for i, req_skill in enumerate(req_list):
            related = 0
            for j, cand_skill in enumerate(cand_list):
                if cand_skill == req_skill:
                    related += 1
                    continue
                bert_credit = self._skill_credit(float(sim_matrix[i][j])) if sim_matrix is not None else 0.0
                cluster_credit = CLUSTER_CREDIT if skills_in_same_cluster(req_skill, cand_skill) else 0.0
                if max(bert_credit, cluster_credit) > 0:
                    related += 1
            total_extra += max(related - 1, 0)
        return total_extra

    def match_cv_to_jobs(
        self,
        cv_result: CVParseResult,
        jobs: List[Job],
        min_score: float = 0.0,
    ) -> List[MatchResult]:
        """Match a single CV against multiple jobs."""
        results = [self.match_cv_to_job(cv_result, j) for j in jobs]
        results.sort(key=lambda r: r.match_score, reverse=True)
        if min_score > 0:
            results = [r for r in results if r.match_score >= min_score]
        return results

    def batch_match(
        self, cv_results: List[CVParseResult], jobs: List[Job],
        min_score: float = 0.0,
    ) -> List[List[MatchResult]]:
        return [self.match_cv_to_jobs(cv, jobs, min_score) for cv in cv_results]

    # ------------------------------------------------------------------ #
    #  Similarity computation
    # ------------------------------------------------------------------ #

    def _compute_similarity(self, cv: CVParseResult, job: Job) -> float:
        """Cosine similarity between CV and job text."""
        cv_text = self._build_cv_text(cv)
        job_text = self._build_job_text(job)

        if _HAS_EMBEDDINGS:
            # _embedding_similarity lazy-loads the model on first use and
            # falls back internally if loading ever fails.
            return self._embedding_similarity(cv_text, job_text)
        else:
            return self._fallback_similarity(cv_text, job_text)

    def _build_cv_text(self, cv: CVParseResult) -> str:
        parts = [
            f"Skills: {', '.join(cv.skills)}",
            f"Experience: {cv.experience[:500]}",
            f"Education: {cv.education[:300]}",
            f"Certifications: {', '.join(cv.certifications)}",
            f"Projects: {', '.join(cv.projects)}",
        ]
        return preprocess_for_embedding(" ".join(parts))

    def _build_job_text(self, job: Job) -> str:
        parts = [
            f"Title: {job.title}",
            f"Description: {job.description}",
            f"Required Skills: {', '.join(job.required_skills)}",
            f"Requirements: {', '.join(job.requirements)}",
            f"Qualifications: {', '.join(job.qualifications)}",
        ]
        return preprocess_for_embedding(" ".join(parts))

    # ------------------------------------------------------------------ #
    #  Embedding-based (requires sentence-transformers + numpy + sklearn)
    # ------------------------------------------------------------------ #

    def _embedding_similarity(self, text_a: str, text_b: str) -> float:
        try:
            if self._model is None:
                self._load_model()
            if self._model is None:
                return self._fallback_similarity(text_a, text_b)
            emb_a = self._model.encode([text_a], normalize_embeddings=True)
            emb_b = self._model.encode([text_b], normalize_embeddings=True)
            sim = cosine_similarity(emb_a, emb_b)[0][0]
            return float(np.clip(sim, 0.0, 1.0))
        except Exception:
            return self._fallback_similarity(text_a, text_b)

    @property
    def using_bert(self) -> bool:
        """Whether BERT embeddings (sentence-transformers) are active."""
        return _HAS_EMBEDDINGS and self._model is not None

    def _load_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
        except Exception as e:
            self._load_error = str(e)
            self._model = None

    # ------------------------------------------------------------------ #
    #  Pure-Python fallback (n-gram overlap + keyword overlap)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _fallback_similarity(text_a: str, text_b: str) -> float:
        """
        Character n-gram cosine similarity (no external packages).

        Uses character bigram and trigram overlap as a simple
        semantic proxy.  Fast and dependency-free.
        """
        if not text_a or not text_b:
            return 0.0

        def _ngrams(t: str, n: int) -> dict:
            d = {}
            for i in range(len(t) - n + 1):
                gram = t[i:i + n]
                d[gram] = d.get(gram, 0) + 1
            return d

        def _cosine(d1: dict, d2: dict) -> float:
            dot = 0.0
            n1 = n2 = 0.0
            for k, v in d1.items():
                n1 += v * v
                if k in d2:
                    dot += v * d2[k]
            for v in d2.values():
                n2 += v * v
            if n1 == 0 or n2 == 0:
                return 0.0
            return dot / (math.sqrt(n1) * math.sqrt(n2))

        bigram_sim = _cosine(_ngrams(text_a.lower(), 2),
                             _ngrams(text_b.lower(), 2))
        trigram_sim = _cosine(_ngrams(text_a.lower(), 3),
                              _ngrams(text_b.lower(), 3))

        # Weighted: 40% bigram, 60% trigram
        return bigram_sim * 0.4 + trigram_sim * 0.6
