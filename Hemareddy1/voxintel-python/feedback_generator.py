"""
feedback_generator.py
----------------------
Generates personalized, actionable interview feedback by combining
results from the semantic evaluator, confidence analyzer, and plagiarism checker.

Design philosophy:
  - Specific, not generic. Feedback references the actual scores.
  - Encouraging tone — points out what's good before what needs work.
  - Actionable — each weakness comes with a tip.
  - Lightweight — pure Python logic, no ML model needed here.
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


# ── Score Interpretation Helpers ─────────────────────────────

def _score_label(score: int) -> str:
    """Convert a 0-100 score into a human-readable quality label."""
    if score >= 85:
        return "excellent"
    elif score >= 70:
        return "good"
    elif score >= 50:
        return "fair"
    elif score >= 30:
        return "below average"
    else:
        return "poor"


def _missing_keywords_hint(keywords: List[str], user_answer: str) -> str:
    """Find which keywords the candidate missed and suggest them."""
    if not keywords:
        return ""
    lower_answer = user_answer.lower() if user_answer else ""
    missed = [kw for kw in keywords if kw.lower() not in lower_answer]
    if not missed:
        return ""
    # Show up to 4 missed keywords to keep the message concise
    sample = missed[:4]
    return (
        f"Consider incorporating these important terms in your next attempt: "
        f"{', '.join(sample)}."
    )


# ── Section Builders ─────────────────────────────────────────

def _semantic_section(semantic_score: int, completeness_score: int) -> str:
    """Build feedback text for the semantic/completeness portion."""
    label = _score_label(semantic_score)

    if semantic_score >= 70:
        intro = f"Your answer was semantically {label} — you captured the core idea well."
    elif semantic_score >= 50:
        intro = (
            f"Your answer was {label} in terms of meaning. "
            "You touched on relevant points, but some key ideas were missing or unclear."
        )
    else:
        intro = (
            f"Your answer scored {label} for semantic similarity to the ideal response. "
            "It seems the core concept may not have been fully addressed."
        )

    if completeness_score < 50:
        intro += (
            " Your answer was relatively brief. Try to elaborate — explain the 'why' behind your answer, "
            "not just the 'what'."
        )
    elif completeness_score >= 80:
        intro += " Your answer had good depth and structure."

    return intro


def _keyword_section(keyword_score: int, keywords: List[str], user_answer: str) -> str:
    """Build feedback for technical terminology usage."""
    label = _score_label(keyword_score)

    if keyword_score >= 70:
        return (
            f"Technical vocabulary: {label}. You used the right terminology, "
            "which demonstrates solid domain knowledge."
        )
    elif keyword_score >= 40:
        hint = _missing_keywords_hint(keywords, user_answer)
        return (
            f"Technical vocabulary: {label}. You used some relevant terms, "
            f"but could be more precise. {hint}"
        )
    else:
        hint = _missing_keywords_hint(keywords, user_answer)
        return (
            f"Technical vocabulary: {label}. Using the correct technical terms "
            f"is important in interviews — it signals hands-on experience. {hint}"
        )


def _confidence_section(confidence: Dict) -> str:
    """Build feedback for communication and confidence."""
    if not confidence or confidence.get("score") is None:
        return ""

    score = confidence.get("score", 50)
    filler_count = confidence.get("filler_word_count", 0)
    hedge_count = confidence.get("hedging_count", 0)
    label = _score_label(score)

    parts = [f"Communication confidence: {label} ({score}/100)."]

    if filler_count > 4:
        parts.append(
            f"You used {filler_count} filler words. "
            "Practice pausing silently when you need to gather your thoughts — "
            "it reads far better than 'um' or 'like'."
        )
    elif filler_count > 1:
        parts.append(f"Minor: {filler_count} filler words detected. Keep an eye on this.")

    if hedge_count > 3:
        parts.append(
            "You hedged frequently ('I think', 'maybe', 'I'm not sure'). "
            "If you know something, say it directly. If you don't know, acknowledge it once and move on."
        )

    speed = confidence.get("speech_speed", "normal")
    if speed == "slow":
        parts.append("Your answer took a while — in live interviews, pausing too long can signal uncertainty.")
    elif speed == "instant":
        parts.append("Your answer appeared very quickly. Make sure you're engaging with each question thoughtfully.")

    return " ".join(parts)


def _plagiarism_section(plagiarism: Dict) -> str:
    """Build feedback for originality."""
    if not plagiarism:
        return ""

    score = plagiarism.get("score", 0)

    if score < 25:
        return "Originality: Your answer appears genuine and written in your own words."
    elif score < 50:
        return (
            "Originality: Some patterns in your answer resemble templated or AI-generated text. "
            "Try to answer in a natural, conversational way that reflects your own experience."
        )
    else:
        return (
            f"Originality: Your answer raised some flags (score: {score}/100). "
            "Interviewers value authentic answers that show real understanding. "
            "Practice expressing concepts in your own words."
        )


def _improvement_tips(overall_score: int, semantic_score: int, keyword_score: int) -> List[str]:
    """Generate 2-3 prioritized improvement tips based on the weakest areas."""
    tips = []

    if overall_score < 40:
        tips.append(
            "Focus on understanding the core concept first. "
            "Read the ideal answer after the session and try to re-explain it in your own words."
        )

    if semantic_score < 50:
        tips.append(
            "Your answer didn't closely match the expected meaning. "
            "Make sure you're directly addressing the question asked, not a related but different topic."
        )

    if keyword_score < 40:
        tips.append(
            "Build your technical vocabulary for this domain. "
            "Flashcards, documentation reading, and hands-on practice all help internalize the right terms."
        )

    if overall_score >= 70:
        tips.append(
            "Strong performance! Challenge yourself: "
            "try explaining this concept as if teaching it to a junior developer."
        )

    if not tips:
        tips.append("Keep practicing. Consistency is the key to interview confidence.")

    return tips


# ── Main Feedback Function ────────────────────────────────────

def generate_feedback(
    eval_result: Dict,
    confidence_result: Dict,
    plagiarism_result: Dict,
    keywords: List[str],
    user_answer: str = "",
) -> str:
    """
    Combine all evaluation signals into a single, coherent feedback paragraph.

    Parameters:
        eval_result: Output from semantic_evaluator.evaluate_answer()
        confidence_result: Output from confidence_analysis.analyze_confidence()
        plagiarism_result: Output from plagiarism_checker.check_plagiarism()
        keywords: List of expected technical keywords for this question.
        user_answer: The raw user answer (for keyword gap analysis).

    Returns:
        A multi-paragraph string of personalized feedback.
    """
    semantic_score = eval_result.get("semantic_score", 0)
    keyword_score = eval_result.get("keyword_score", 0)
    completeness_score = eval_result.get("completeness_score", 0)
    overall_score = eval_result.get("overall_score", 0)

    sections = []

    # ── Overall opening line ─────────────────────────────────
    overall_label = _score_label(overall_score)
    sections.append(
        f"Overall performance: {overall_label} ({overall_score}/100). "
        + (
            "Well done — you demonstrated solid understanding."
            if overall_score >= 70
            else "There's room to improve — see the detailed breakdown below."
        )
    )

    # ── Semantic & completeness ──────────────────────────────
    sections.append(_semantic_section(semantic_score, completeness_score))

    # ── Technical keywords ───────────────────────────────────
    sections.append(_keyword_section(keyword_score, keywords, user_answer))

    # ── Confidence (only if data exists) ────────────────────
    confidence_text = _confidence_section(confidence_result)
    if confidence_text:
        sections.append(confidence_text)

    # ── Originality ──────────────────────────────────────────
    originality_text = _plagiarism_section(plagiarism_result)
    if originality_text:
        sections.append(originality_text)

    # ── Improvement tips ─────────────────────────────────────
    tips = _improvement_tips(overall_score, semantic_score, keyword_score)
    if tips:
        tip_text = "Improvement tips: " + " | ".join(tips)
        sections.append(tip_text)

    # Join all sections with double newline for readability
    return "\n\n".join(s for s in sections if s)
