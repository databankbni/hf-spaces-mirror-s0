"""
code_followup_generator.py
-----------------------------
Generates an adaptive follow-up question for a coding-round submission —
used only for "Coding Interview" sessions (see sessionController.js;
"Coding Round" sessions never mark a question follow-up-eligible).

Like followup_generator.py, there's no generative LLM here — the follow-up
is built from templates plus signals about the submission:
  - If every test passed: ask about complexity/optimization, referencing
    one of the problem's expected_concepts if available.
  - If some/all tests failed: ask about the failure, referencing the first
    *public* failing test case only (hidden test inputs must never leak
    into a follow-up question).

The follow-up itself is answered in prose (not more code) — it's evaluated
the same way a text answer is, using expected_concepts as the keyword list.
"""

import random
from typing import Dict, List, Optional

OPTIMIZATION_PROBES = [
    "What's the time and space complexity of your solution, and how would you optimize it further?",
    "Is there a way to solve this with better time or space complexity? Walk me through the tradeoff.",
]


def generate_code_followup(
    passed_count: int,
    total_count: int,
    expected_concepts: List[str],
    first_public_failure: Optional[Dict] = None,
) -> Dict:
    """
    Returns { "question": str, "based_on": str }.
    `first_public_failure` (if provided): { "args": [...], "expected": ... }
    — from a *public* test case only, never a hidden one.
    """
    expected_concepts = expected_concepts or []

    if total_count > 0 and passed_count == total_count:
        if expected_concepts:
            concept = random.choice(expected_concepts)
            return {
                "question": f'Your solution works. Can you explain how "{concept}" relates to your approach, and what the time complexity is?',
                "based_on": f"correct:{concept}",
            }
        return {
            "question": random.choice(OPTIMIZATION_PROBES),
            "based_on": "correct:generic",
        }

    if first_public_failure:
        return {
            "question": (
                f"Your solution didn't handle the input {first_public_failure['args']} correctly "
                f"(expected {first_public_failure['expected']}). What edge case do you think you're missing?"
            ),
            "based_on": "failed:public",
        }

    return {
        "question": (
            "Your solution passed the visible examples but not all hidden test cases. "
            "What edge cases might your approach be missing — empty input, duplicates, negative numbers?"
        ),
        "based_on": "failed:hidden",
    }
