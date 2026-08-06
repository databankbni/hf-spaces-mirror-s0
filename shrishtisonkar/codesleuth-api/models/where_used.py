"""Pydantic models for Where Used feature."""
from typing import Literal
from pydantic import BaseModel


class UsedByItem(BaseModel):
    id: str
    label: str
    relation: str


class WhereUsedRequest(BaseModel):
    session_id: str
    target: str
    target_type: Literal["file", "module", "function"] = "file"


class WhereUsedResponse(BaseModel):
    target: str
    target_type: str
    used_by: list[UsedByItem]
    related_flows: list[str]
    graph_highlights: list[str]
    summary: str
