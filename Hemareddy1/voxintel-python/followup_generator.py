"""
followup_generator.py
-----------------------
Generates an adaptive follow-up question based on which keywords the
candidate's answer did or didn't use.

Design note — there is no generative LLM in this stack (spaCy /
sentence-transformers / scikit-learn only), so a follow-up is built from
templates plus a signal extracted from the answer, rather than free-form
text generation:
  - If the answer missed an important keyword, ask about that gap.
  - Otherwise, if it covered the keywords, ask the candidate to go deeper
    on one they used.
  - If there are no keywords to check against, fall back to a generic
    depth probe.
"""

import re
import random
from typing import Dict, List, Tuple

GENERIC_PROBES = [
    "Can you walk through a specific example from your own experience that illustrates this?",
    "What would you do differently if you had to solve this again under a tight deadline?",
    "What's a common mistake people make here, and how would you avoid it?",
]


def _keyword_coverage(user_answer: str, keywords: List[str]) -> Tuple[List[str], List[str]]:
    """Split keywords into (matched, missing) based on word-boundary matching."""
    lower_answer = user_answer.lower()
    matched, missing = [], []
    for kw in keywords:
        pattern = r"\b" + re.escape(kw.lower()) + r"\b"
        if re.search(pattern, lower_answer):
            matched.append(kw)
        else:
            missing.append(kw)
    return matched, missing


def generate_followup_question(user_answer: str, keywords: List[str]) -> Dict:
    """
    Build an adaptive follow-up question from the candidate's answer.

    Returns: { "question": str, "based_on": str }
    `based_on` is "missing:<keyword>", "matched:<keyword>", or "generic" —
    useful for debugging/analytics, not shown to the candidate.
    """
    keywords = keywords or []
    matched, missing = _keyword_coverage(user_answer or "", keywords)

    if missing:
        kw = random.choice(missing)
        return {
            "question": f'You didn\'t mention "{kw}" — how does that fit into your approach here?',
            "based_on": f"missing:{kw}",
        }

    if matched:
        kw = random.choice(matched)
        return {
            "question": f'You mentioned "{kw}" — can you go deeper into how you used it, with a specific example?',
            "based_on": f"matched:{kw}",
        }

    return {
        "question": random.choice(GENERIC_PROBES),
        "based_on": "generic",
    }
