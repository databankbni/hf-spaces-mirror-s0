from typing import Literal

from pydantic import BaseModel, Field


ChatMode = Literal["subject_tutor", "dim_coach"]


class ChatQuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    mode: ChatMode = "subject_tutor"
    subject: str | None = None
    grade: int | None = Field(default=None, ge=5, le=11)
    language: str | None = Field(default=None, min_length=2, max_length=8)


class Citation(BaseModel):
    document_id: str
    title: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    citation_label: str


class ChatAnswerResponse(BaseModel):
    answer: str
    mode: ChatMode
    weak_context: bool = False
    citations: list[Citation] = Field(default_factory=list)
