"""
coding_question_generator.py
------------------------------
Selects a set of coding problems for a "Coding Interview" / "Coding Round"
session: 60% from the static bank (coding_questions.py) unfiltered, 40%
prioritized toward problems whose skill_tags match the candidate's resume
skills (falling back to the remaining static problems if there aren't enough
skill matches). Every problem is still pre-authored and pre-tested — resume
data only influences *which* problems get selected, not their content, so
test cases stay trustworthy.

If the requested count exceeds the size of the bank, the bank size is the
hard ceiling — problems are never repeated within a session.
"""

import math
import random
import logging
from typing import List, Dict

from coding_questions import CODING_QUESTIONS

logger = logging.getLogger(__name__)

SOURCE_RESUME = "resume"
SOURCE_DATASET = "dataset"


def _matches_skill(question: Dict, normalized_skills: set) -> bool:
    tags = {t.lower() for t in question.get("skill_tags", [])}
    return bool(normalized_skills & tags)


def _public_view(question: Dict, source: str) -> Dict:
    """Attach source tracking; hidden_test_cases stay in the object for the
    Node caller to store server-side, but are stripped before reaching the frontend."""
    return {**question, "source": source, "type": "coding"}


def generate_coding_questions(skills: List[str], count: int = 10) -> List[Dict]:
    total = min(count, len(CODING_QUESTIONS))
    if total < count:
        logger.warning(
            f"Requested {count} coding questions but the bank only has "
            f"{len(CODING_QUESTIONS)} — returning {total} without repeats."
        )

    resume_count = max(0, total - math.ceil(total * 0.6))
    dataset_count = total - resume_count

    pool = list(CODING_QUESTIONS)
    random.shuffle(pool)

    normalized_skills = {s.lower() for s in (skills or [])}
    skill_matched = [q for q in pool if _matches_skill(q, normalized_skills)]
    non_matched = [q for q in pool if not _matches_skill(q, normalized_skills)]

    selected = []
    used_ids = set()

    # 40% bucket — prefer skill-matched problems
    for q in skill_matched:
        if len(selected) >= resume_count:
            break
        selected.append(_public_view(q, SOURCE_RESUME))
        used_ids.add(q["id"])

    # Not enough skill matches? Fill remaining resume slots from the rest.
    remaining = [q for q in pool if q["id"] not in used_ids]
    while len(selected) < resume_count and remaining:
        q = remaining.pop()
        selected.append(_public_view(q, SOURCE_RESUME))
        used_ids.add(q["id"])

    # 60% bucket — static, whatever's left
    remaining = [q for q in pool if q["id"] not in used_ids]
    while len(selected) < total and remaining:
        q = remaining.pop()
        selected.append(_public_view(q, SOURCE_DATASET))
        used_ids.add(q["id"])

    random.shuffle(selected)

    logger.info(
        f"Coding question selection: total={len(selected)}, "
        f"resume={sum(1 for q in selected if q['source'] == SOURCE_RESUME)}, "
        f"dataset={sum(1 for q in selected if q['source'] == SOURCE_DATASET)}"
    )

    return selected
