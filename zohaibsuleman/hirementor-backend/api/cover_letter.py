import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.gemini import gemini

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cover-letter", tags=["Cover Letter"])


class CoverLetterRequest(BaseModel):
    student_name: str
    job_title: str
    company_name: str
    student_skills: list[str] = []
    student_experience: str = ""


class CoverLetterResponse(BaseModel):
    cover_letter: str = ""


@router.post("/generate", response_model=CoverLetterResponse)
def generate_cover_letter(request: CoverLetterRequest):
    if not gemini.is_available():
        raise HTTPException(status_code=503, detail="Gemini AI not configured")

    skills_str = ", ".join(request.student_skills) if request.student_skills else "relevant skills"
    prompt = f"""Write a professional cover letter (200-250 words) for a job application.

Applicant: {request.student_name}
Position: {request.job_title}
Company: {request.company_name}
Skills: {skills_str}
Experience: {request.student_experience or 'N/A'}

The cover letter should:
- Express enthusiasm for the role and company
- Highlight relevant skills
- Show cultural fit
- Include a strong closing

Return ONLY the cover letter text, no introductory remarks."""
    try:
        text = gemini.generate(prompt, temperature=0.7)
        return CoverLetterResponse(cover_letter=text.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
