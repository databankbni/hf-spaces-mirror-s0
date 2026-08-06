"""Pydantic models for New Developer Onboarding Mode."""
from pydantic import BaseModel


class StartPoint(BaseModel):
    title: str
    file: str
    reason: str


class KeyModule(BaseModel):
    name: str
    summary: str


class GlossaryItem(BaseModel):
    term: str
    meaning: str


class OnboardingResponse(BaseModel):
    session_id: str
    repo_name: str
    overview: str
    recommended_start_points: list[StartPoint]
    key_modules: list[KeyModule]
    learning_path: list[str]
    glossary: list[GlossaryItem]
    suggested_questions: list[str]
