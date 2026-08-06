import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.gemini import gemini

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/interview", tags=["Interview"])


class ScoreRequest(BaseModel):
    job_title: str
    job_description: str
    questions: list[str]
    answers: list[str]


class ScoreResponse(BaseModel):
    overall_score: float = 0.0
    feedback: str = ""
    strengths: list[str] = []
    improvements: list[str] = []
    communication_tone: str = "Neutral"
    clarity_score: float = 70.0


class QuestionRequest(BaseModel):
    job_title: str
    job_description: str
    required_skills: list[str] = []
    interview_type: str = "Technical"
    number_of_questions: int = 5


class QuestionResponse(BaseModel):
    questions: list[str] = []


class SentimentRequest(BaseModel):
    answer: str


class SentimentResponse(BaseModel):
    tone: str = "Neutral"
    clarity_score: int = 70
    suggested_improvement: str = ""


class PredictionRequest(BaseModel):
    student_cgpa: float = 0.0
    match_score: float = 0.0
    interview_score: float = 0.0
    required_skills: list[str] = []
    student_skills: list[str] = []


class PredictionResponse(BaseModel):
    probability: float = 0.0
    risk_factors: list[str] = []
    recommendation: str = "Review"


@router.post("/score", response_model=ScoreResponse)
def score_interview(request: ScoreRequest):
    if not gemini.is_available():
        raise HTTPException(status_code=503, detail="Gemini AI not configured")

    qa_block = "\n\n".join(
        f"Q{i+1}: {q}\nA{i+1}: {a}"
        for i, (q, a) in enumerate(zip(request.questions, request.answers))
    )
    prompt = f"""You are an expert HR interviewer. Evaluate these interview responses.

Job Title: {request.job_title}
Job Description: {request.job_description}

Interview Q&A:
{qa_block}

Return ONLY valid JSON:
{{
  "overallScore": <0-100>,
  "feedback": "...",
  "strengths": [...],
  "improvements": [...],
  "communicationTone": "Confident/Nervous/Formal/Neutral",
  "clarityScore": <0-100>
}}"""
    try:
        data = gemini.generate_json(prompt)
        return ScoreResponse(
            overall_score=float(data.get("overallScore", 0)),
            feedback=data.get("feedback", ""),
            strengths=data.get("strengths", []),
            improvements=data.get("improvements", []),
            communication_tone=data.get("communicationTone", "Neutral"),
            clarity_score=float(data.get("clarityScore", 70)),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/questions", response_model=QuestionResponse)
def generate_questions(request: QuestionRequest):
    if not gemini.is_available():
        raise HTTPException(status_code=503, detail="Gemini AI not configured")

    skills_str = ", ".join(request.required_skills) if request.required_skills else "General"
    prompt = f"""Generate {request.number_of_questions} {request.interview_type} interview questions.

Job Title: {request.job_title}
Description: {request.job_description}
Skills: {skills_str}

Return ONLY a JSON array of strings: ["q1", "q2", ...]"""
    try:
        data = gemini.generate_json(prompt)
        if isinstance(data, list):
            questions = data
        elif isinstance(data, dict):
            questions = data.get("questions", [])
        else:
            questions = []
        return QuestionResponse(questions=questions[: request.number_of_questions])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sentiment", response_model=SentimentResponse)
def analyze_sentiment(request: SentimentRequest):
    if not gemini.is_available():
        raise HTTPException(status_code=503, detail="Gemini AI not configured")

    prompt = f"""Analyze the tone and communication quality of this interview answer.
Answer: {request.answer}

Return ONLY valid JSON:
{{
  "tone": "Confident/Nervous/Formal/Neutral",
  "clarityScore": <0-100>,
  "suggestedImprovement": "..."
}}"""
    try:
        data = gemini.generate_json(prompt)
        return SentimentResponse(
            tone=data.get("tone", "Neutral"),
            clarity_score=int(data.get("clarityScore", 70)),
            suggested_improvement=data.get("suggestedImprovement", ""),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/predict", response_model=PredictionResponse)
def predict_hiring(request: PredictionRequest):
    if not gemini.is_available():
        raise HTTPException(status_code=503, detail="Gemini AI not configured")

    prompt = f"""Predict the selection probability for this candidate.

CGPA: {request.student_cgpa}/4.0
Skill Match: {request.match_score}%
Interview Score: {request.interview_score}%
Required Skills: {', '.join(request.required_skills)}
Candidate Skills: {', '.join(request.student_skills)}

Return ONLY valid JSON:
{{
  "probability": <0-100>,
  "riskFactors": [...],
  "recommendation": "Hire/Consider/Reject"
}}"""
    try:
        data = gemini.generate_json(prompt)
        return PredictionResponse(
            probability=float(data.get("probability", 0)),
            risk_factors=data.get("riskFactors", []),
            recommendation=data.get("recommendation", "Review"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
