import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.gemini import gemini

try:
    from spb_nlp.recommender import JobRecommender
    NLP_AVAILABLE = True
except ImportError:
    NLP_AVAILABLE = False

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recommendations", tags=["Recommendations"])


class JobRecommendRequest(BaseModel):
    student_skills: list[str] = []
    student_major: str = ""
    student_experience: str = ""
    available_jobs: list[dict] = []


class JobRecommendResponse(BaseModel):
    recommendations: list[dict] = []


class LearningRecommendRequest(BaseModel):
    student_skills: list[str] = []
    target_jobs: list[str] = []
    skill_gaps: list[str] = []


class LearningRecommendResponse(BaseModel):
    recommendations: list[str] = []


class ResumeAnalysisRequest(BaseModel):
    student_profile: str


class ResumeAnalysisResponse(BaseModel):
    score: float = 0.0
    strengths: list[str] = []
    improvements: list[str] = []
    suggestions: str = ""


@router.post("/jobs", response_model=JobRecommendResponse)
def recommend_jobs(request: JobRecommendRequest):
    if not gemini.is_available():
        raise HTTPException(status_code=503, detail="Gemini AI not configured")

    jobs_preview = "\n".join(
        f"- {j.get('title', '')} at {j.get('companyName', '')} (Skills: {', '.join(j.get('requiredSkills', []))})"
        for j in request.available_jobs[:50]
    )
    prompt = f"""Recommend the best jobs for this student.

Skills: {', '.join(request.student_skills)}
Major: {request.student_major}
Experience: {request.student_experience or 'N/A'}

Available Jobs:
{jobs_preview or 'None'}

Return ONLY a JSON array of objects with fields "jobTitle", "companyName", "matchScore" (0-100), and "reason".
Example: [{{"jobTitle":"...","companyName":"...","matchScore":85,"reason":"..."}}]"""
    try:
        data = gemini.generate_json(prompt)
        recs = data if isinstance(data, list) else data.get("recommendations", [])
        return JobRecommendResponse(recommendations=recs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/learning", response_model=LearningRecommendResponse)
def learning_recommendations(request: LearningRecommendRequest):
    if not gemini.is_available():
        raise HTTPException(status_code=503, detail="Gemini AI not configured")

    prompt = f"""Give personalized learning recommendations.

Current Skills: {', '.join(request.student_skills)}
Target Jobs: {', '.join(request.target_jobs)}
Skill Gaps: {', '.join(request.skill_gaps) or 'None identified'}

Return ONLY a JSON array of strings with specific courses/resources to learn. Max 5 items."""
    try:
        data = gemini.generate_json(prompt)
        recs = data if isinstance(data, list) else []
        return LearningRecommendResponse(recommendations=recs[:5])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resume-analysis", response_model=ResumeAnalysisResponse)
def analyze_resume(request: ResumeAnalysisRequest):
    if not gemini.is_available():
        raise HTTPException(status_code=503, detail="Gemini AI not configured")

    prompt = f"""Analyze this student profile and provide resume feedback.

Profile:
{request.student_profile}

Return ONLY valid JSON:
{{
  "score": <0-100>,
  "strengths": [...],
  "improvements": [...],
  "suggestions": "..."
}}"""
    try:
        data = gemini.generate_json(prompt)
        return ResumeAnalysisResponse(
            score=float(data.get("score", 0)),
            strengths=data.get("strengths", []),
            improvements=data.get("improvements", []),
            suggestions=data.get("suggestions", ""),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
