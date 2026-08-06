import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.gemini import gemini

try:
    from spb_nlp import models as nlp_models
    from spb_nlp.semantic_matcher import SemanticMatcher
    from spb_nlp.utils import extract_skills
    NLP_AVAILABLE = True
    _skill_matcher = SemanticMatcher(lazy_load=True)
except ImportError:
    NLP_AVAILABLE = False
    _skill_matcher = None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/skill", tags=["Skill Matching"])


class SkillMatchRequest(BaseModel):
    student_skills: list[str] = []
    student_major: str = ""
    student_experience: str = ""
    job_title: str = ""
    job_company: str = ""
    job_required_skills: list[str] = []
    job_description: str = ""


class SkillMatchResponse(BaseModel):
    match_score: float = 0.0
    matching_skills: list[str] = []
    missing_skills: list[str] = []
    recommendations: list[str] = []
    analysis: str = ""


class SkillAnalysisRequest(BaseModel):
    student_skills: list[str] = []
    student_major: str = ""
    student_experience: str = ""
    student_projects: str = ""


class SkillAnalysisResponse(BaseModel):
    technical_skills: list[str] = []
    soft_skills: list[str] = []
    experience_level: str = "Entry"
    skill_gaps: list[str] = []
    recommended_skills: list[str] = []
    career_path: list[str] = []


class StudentProfile(BaseModel):
    student_id: str
    name: str = ""
    skills: list[str] = []
    major: str = ""
    experience: str = ""
    cgpa: float = 0.0

class BatchMatchRequest(BaseModel):
    job_title: str
    job_description: str = ""
    required_skills: list[str] = []
    students: list[StudentProfile]
    threshold: float = 50.0

class BatchMatchItem(BaseModel):
    student_id: str
    name: str = ""
    match_score: float = 0.0
    matching_skills: list[str] = []
    missing_skills: list[str] = []
    meets_threshold: bool = False

class BatchMatchResponse(BaseModel):
    results: list[BatchMatchItem] = []


class MCQGenerateRequest(BaseModel):
    job_title: str = ""
    job_description: str = ""
    required_skills: list[str] = []
    number_of_questions: int = 5
    question_type: str = "Technical MCQs"


class MCQItem(BaseModel):
    question: str
    options: list[str]
    correct_answer_index: int
    explanation: str


class MCQGenerateResponse(BaseModel):
    mcqs: list[MCQItem] = []


class MCQParseRequest(BaseModel):
    text: str


class MCQParseResponse(BaseModel):
    mcqs: list[MCQItem] = []


@router.post("/match", response_model=SkillMatchResponse)
def skill_match(request: SkillMatchRequest):
    candidate_skills = {s.lower() for s in request.student_skills}
    required_skills = {s.lower() for s in request.job_required_skills}

    matching = list(candidate_skills & required_skills)
    missing = list(required_skills - candidate_skills)

    if NLP_AVAILABLE and _skill_matcher is not None:
        try:
            cv_result = nlp_models.CVParseResult(
                skills=request.student_skills,
                education=request.student_major,
                experience=request.student_experience,
            )
            job = nlp_models.Job(
                title=request.job_title,
                description=request.job_description,
                required_skills=request.job_required_skills,
            )
            result = _skill_matcher.match_cv_to_job(cv_result, job)
            return SkillMatchResponse(
                match_score=round(result.match_score, 1),
                matching_skills=sorted(result.matching_skills),
                missing_skills=sorted(result.missing_skills),
                recommendations=result.recommendations or [
                    f"Consider adding: {', '.join(missing[:3])}"
                ] if missing else [],
                analysis=result.detailed_analysis or f"Semantic match score: {result.match_score:.1f}%",
            )
        except Exception as e:
            logger.warning("SemanticMatcher skill match failed: %s", e)

    if gemini.is_available():
        prompt = f"""Analyze the match between a student and a job.

Student Skills: {', '.join(request.student_skills)}
Major: {request.student_major}
Experience: {request.student_experience or 'N/A'}

Job: {request.job_title} at {request.job_company}
Required Skills: {', '.join(request.job_required_skills)}
Description: {request.job_description[:500]}

Return ONLY valid JSON:
{{
  "matchScore": <0-100>,
  "matchingSkills": {matching},
  "missingSkills": {missing},
  "recommendations": [...],
  "analysis": "..."
}}"""
        try:
            data = gemini.generate_json(prompt)
            return SkillMatchResponse(
                match_score=float(data.get("matchScore", 0)),
                matching_skills=data.get("matchingSkills", matching),
                missing_skills=data.get("missingSkills", missing),
                recommendations=data.get("recommendations", []),
                analysis=data.get("analysis", ""),
            )
        except Exception as e:
            logger.warning("Gemini skill match failed: %s", e)

    skill_ratio = len(matching) / len(required_skills) if required_skills else 0
    score = round(skill_ratio * 100, 1)
    recs = [f"Consider adding: {', '.join(missing[:3])}"] if missing else ["Great fit!"]
    return SkillMatchResponse(
        match_score=score,
        matching_skills=sorted(matching),
        missing_skills=sorted(missing),
        recommendations=recs,
        analysis=f"Matched {len(matching)}/{len(required_skills)} required skills ({score}%).",
    )


@router.post("/batch-match", response_model=BatchMatchResponse)
def batch_match(request: BatchMatchRequest):
    results = []
    for student in request.students:
        score = 0.0
        matching = []
        missing = []
        meets = False

        if NLP_AVAILABLE and _skill_matcher is not None:
            try:
                cv_result = nlp_models.CVParseResult(
                    skills=student.skills,
                    education=student.major,
                    experience=student.experience,
                )
                job = nlp_models.Job(
                    title=request.job_title,
                    description=request.job_description,
                    required_skills=request.required_skills,
                )
                result = _skill_matcher.match_cv_to_job(cv_result, job)
                score = round(result.match_score, 1)
                matching = result.matching_skills
                missing = result.missing_skills
                meets = result.meets_threshold
            except Exception as e:
                logger.warning("Batch match student %s failed: %s", student.student_id, e)
                _fallback_batch(student, request, score, matching, missing, meets)

        if score == 0.0:
            s_skills = {s.lower() for s in student.skills}
            r_skills = {s.lower() for s in request.required_skills}
            matching = list(s_skills & r_skills)
            missing = list(r_skills - s_skills)
            ratio = len(matching) / len(r_skills) if r_skills else 0
            score = round(ratio * 100, 1)
            meets = score >= request.threshold

        results.append(BatchMatchItem(
            student_id=student.student_id,
            name=student.name,
            match_score=round(score, 1),
            matching_skills=sorted(matching),
            missing_skills=sorted(missing),
            meets_threshold=meets,
        ))

    results.sort(key=lambda x: x.match_score, reverse=True)
    return BatchMatchResponse(results=results)


@router.post("/analyze", response_model=SkillAnalysisResponse)
def analyze_skills(request: SkillAnalysisRequest):
    if not gemini.is_available():
        raise HTTPException(status_code=503, detail="Gemini AI not configured")

    prompt = f"""Analyze this student's skills comprehensively.

Skills: {', '.join(request.student_skills)}
Major: {request.student_major}
Experience: {request.student_experience or 'N/A'}
Projects: {request.student_projects or 'N/A'}

Return ONLY valid JSON:
{{
  "technicalSkills": [...],
  "softSkills": [...],
  "experienceLevel": "Entry/Junior/Mid/Senior",
  "skillGaps": [...],
  "recommendedSkills": [...],
  "careerPath": [...]
}}"""
    try:
        data = gemini.generate_json(prompt)
        return SkillAnalysisResponse(
            technical_skills=data.get("technicalSkills", []),
            soft_skills=data.get("softSkills", []),
            experience_level=data.get("experienceLevel", "Entry"),
            skill_gaps=data.get("skillGaps", []),
            recommended_skills=data.get("recommendedSkills", []),
            career_path=data.get("careerPath", []),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mcq/generate", response_model=MCQGenerateResponse)
def generate_mcqs(request: MCQGenerateRequest):
    if not gemini.is_available():
        raise HTTPException(status_code=503, detail="Gemini AI not configured")

    skills_str = ", ".join(request.required_skills) if request.required_skills else "General"
    prompt = f"""Generate {request.number_of_questions} {request.question_type} for this job.

Job: {request.job_title}
Description: {request.job_description}
Skills: {skills_str}

Each MCQ must have 4 options, 1 correct answer (index 0-3), and an explanation.

Return ONLY a JSON array:
[{{"question":"...","options":["a","b","c","d"],"correctAnswerIndex":0,"explanation":"..."}}]"""
    try:
        data = gemini.generate_json(prompt)
        items = data if isinstance(data, list) else data.get("mcqs", [])
        mcqs = []
        for item in items[: request.number_of_questions]:
            mcqs.append(
                MCQItem(
                    question=item.get("question", ""),
                    options=item.get("options", ["", "", "", ""]),
                    correct_answer_index=int(item.get("correctAnswerIndex", 0)),
                    explanation=item.get("explanation", ""),
                )
            )
        return MCQGenerateResponse(mcqs=mcqs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mcq/parse", response_model=MCQParseResponse)
def parse_mcqs(request: MCQParseRequest):
    if not gemini.is_available():
        raise HTTPException(status_code=503, detail="Gemini AI not configured")

    prompt = f"""Extract MCQs from this text.

{request.text[:10000]}

Each MCQ must have 4 options, 1 correct answer (index 0-3), and an explanation.

Return ONLY a JSON array:
[{{"question":"...","options":["a","b","c","d"],"correctAnswerIndex":0,"explanation":"..."}}]"""
    try:
        data = gemini.generate_json(prompt)
        items = data if isinstance(data, list) else data.get("mcqs", [])
        mcqs = []
        for item in items:
            mcqs.append(
                MCQItem(
                    question=item.get("question", ""),
                    options=item.get("options", ["", "", "", ""]),
                    correct_answer_index=int(item.get("correctAnswerIndex", 0)),
                    explanation=item.get("explanation", ""),
                )
            )
        return MCQParseResponse(mcqs=mcqs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
