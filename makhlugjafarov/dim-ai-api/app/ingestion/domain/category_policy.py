from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

from app.ingestion.domain.content_contract import (
    ContentContract, PROSE_CONTRACT, LATEX_CONTRACT,
)
from app.ingestion.domain.heading import HeadingPolicy, HUM_POLICY, STEM_FORMULA_POLICY, STEM_DESC_POLICY
from app.ingestion.domain.readiness import ReadinessThresholds, HUM_THRESHOLDS, STEM_FORMULA_THRESHOLDS, STEM_DESC_THRESHOLDS

Family = Literal["HUM", "STEM_FORMULA", "STEM_DESC"]

# Single source of truth for subject -> family
def subject_family(subject: str) -> Family:
    if subject in ("mathematics", "physics", "chemistry"):
        return "STEM_FORMULA"
    if subject in ("biology", "geography"):
        return "STEM_DESC"
    return "HUM"

@dataclass(frozen=True)
class CategoryPolicy:
    family: Family
    content_contract: ContentContract
    never_split_types: frozenset[str]
    heading_policy: HeadingPolicy
    readiness_thresholds: ReadinessThresholds

_POLICIES: dict[Family, CategoryPolicy] = {
    "HUM": CategoryPolicy("HUM", PROSE_CONTRACT, frozenset(), HUM_POLICY, HUM_THRESHOLDS),
    "STEM_FORMULA": CategoryPolicy("STEM_FORMULA", LATEX_CONTRACT, frozenset({"formula"}), STEM_FORMULA_POLICY, STEM_FORMULA_THRESHOLDS),
    "STEM_DESC": CategoryPolicy("STEM_DESC", PROSE_CONTRACT, frozenset({"table"}), STEM_DESC_POLICY, STEM_DESC_THRESHOLDS),
}

def get_category_policy(subject: str) -> CategoryPolicy:
    return _POLICIES[subject_family(subject)]
