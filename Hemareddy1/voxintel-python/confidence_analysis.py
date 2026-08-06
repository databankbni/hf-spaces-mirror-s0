"""
confidence_analysis.py
-----------------------
Analyzes how confident a candidate sounds based on their written/spoken answer.

Since we are working primarily with text (not raw audio), confidence is inferred from:
  - Filler word density (um, uh, like, you know...)
  - Hedging language (I think, maybe, probably, I'm not sure...)
  - Answer length relative to expected depth
  - Sentence structure consistency
  - Submission time (very fast = possibly copied, very slow = hesitant)

This is a LIGHTWEIGHT, practical implementation — not a full emotion AI system.
The goal is to give useful communication feedback, not clinical accuracy.
"""

import re
import logging
from typing import Dict

logger = logging.getLogger(__name__)

# ── Filler Words ─────────────────────────────────────────────
# Words that indicate hesitation or low confidence in spoken/informal responses.

FILLER_WORDS = [
    "um", "uh", "uhh", "umm", "er", "err",
    "like", "basically", "literally", "actually",
    "you know", "sort of", "kind of", "i guess",
    "i think maybe", "not sure", "i believe maybe"
]

# ── Hedging Phrases ──────────────────────────────────────────
# Phrases that suggest the candidate is uncertain about their answer.

HEDGING_PHRASES = [
    r"i think",
    r"i believe",
    r"i'm not sure",
    r"i'm not certain",
    r"maybe",
    r"probably",
    r"possibly",
    r"might be",
    r"could be",
    r"i guess",
    r"not exactly",
    r"i don't know",
    r"i'm not 100%",
    r"something like that",
    r"roughly",
    r"approximately",
]

# ── Confidence Signals (Positive) ────────────────────────────
# Phrases that suggest confident, direct communication.

CONFIDENCE_SIGNALS = [
    r"specifically",
    r"for example",
    r"for instance",
    r"the reason is",
    r"this works because",
    r"this means",
    r"therefore",
    r"as a result",
    r"in other words",
    r"to summarize",
    r"the key point is",
    r"the main difference is",
]

# ── Filler Word Counter ───────────────────────────────────────

def count_filler_words(text: str) -> int:
    """Count the number of filler word occurrences in the text."""
    lower = text.lower()
    count = 0
    for filler in FILLER_WORDS:
        # Use word boundary for single words, plain search for phrases
        if " " in filler:
            count += lower.count(filler)
        else:
            pattern = r"\b" + re.escape(filler) + r"\b"
            count += len(re.findall(pattern, lower))
    return count


def count_hedging(text: str) -> int:
    """Count hedging phrases — signs of uncertainty."""
    lower = text.lower()
    count = 0
    for phrase in HEDGING_PHRASES:
        count += len(re.findall(phrase, lower))
    return count


def count_confidence_signals(text: str) -> int:
    """Count positive confidence signals in the text."""
    lower = text.lower()
    count = 0
    for signal in CONFIDENCE_SIGNALS:
        count += len(re.findall(signal, lower))
    return count

# ── Time Analysis ─────────────────────────────────────────────

def analyze_submission_time(time_taken_seconds: int, word_count: int) -> Dict:
    """
    Analyze whether the submission time is suspicious or indicates confidence.

    - Very fast (< 5 seconds for a long answer) → possible copy-paste
    - Normal range → confident
    - Very slow (> 3 min for a short answer) → hesitant

    Returns a dict with speed label and any time-related flags.
    """
    if word_count == 0:
        return {"speech_speed": "empty", "time_flag": "no_answer"}

    # Words per minute — average speaking rate is ~130 wpm, typing ~40-60 wpm
    if time_taken_seconds > 0:
        wpm = (word_count / time_taken_seconds) * 60
    else:
        wpm = 999  # instantaneous = suspicious

    if wpm > 500:
        speed = "instant"
        flag = "suspiciously_fast"
    elif wpm > 120:
        speed = "fast"
        flag = None
    elif wpm > 40:
        speed = "normal"
        flag = None
    elif wpm > 10:
        speed = "slow"
        flag = "hesitant"
    else:
        speed = "very_slow"
        flag = "hesitant"

    return {"speech_speed": speed, "time_flag": flag, "wpm": round(wpm)}

# ── Main Confidence Analysis ──────────────────────────────────

def analyze_confidence(text: str, time_taken_seconds: int = 0, mode: str = "text") -> Dict:
    """
    Main confidence analysis function.

    Parameters:
        text: The candidate's answer text.
        time_taken_seconds: How long they took to answer.
        mode: "text" or "voice" (voice input may have more filler words naturally).

    Returns a dict with:
        score: 0-100
        filler_word_count: int
        speech_speed: str
        feedback: str
        suggestions: list of improvement tips
    """
    if not text or not text.strip():
        return {
            "score": 0,
            "filler_word_count": 0,
            "speech_speed": "N/A",
            "feedback": "No answer provided.",
            "suggestions": ["Please provide an answer to be evaluated."],
        }

    word_count = len(text.split())
    filler_count = count_filler_words(text)
    hedge_count = count_hedging(text)
    confidence_signal_count = count_confidence_signals(text)

    # Time analysis
    time_info = analyze_submission_time(time_taken_seconds, word_count)

    # ── Score Calculation ────────────────────────────────────
    # Start at 100 and subtract for negative signals, add for positive ones.

    score = 100.0

    # Penalize filler words (up to -30 points)
    # Normalize by word count to be fair to longer answers
    filler_density = filler_count / max(word_count, 1)
    filler_penalty = min(30, filler_density * 300)
    score -= filler_penalty

    # Penalize hedging (up to -25 points)
    hedge_density = hedge_count / max(word_count, 1)
    hedge_penalty = min(25, hedge_density * 250)
    score -= hedge_penalty

    # Reward confidence signals (up to +15 points back)
    confidence_bonus = min(15, confidence_signal_count * 3)
    score += confidence_bonus

    # Penalize very short answers (< 20 words) — suggests nervousness
    if word_count < 20:
        score -= 20
    elif word_count < 40:
        score -= 10

    # Voice mode: be slightly more lenient on filler words (natural in speech)
    if mode == "voice":
        score += 5  # small leniency

    # Clamp to [0, 100]
    score = max(0, min(100, round(score)))

    # ── Generate Feedback ────────────────────────────────────
    feedback = _generate_confidence_feedback(
        score, filler_count, hedge_count, confidence_signal_count,
        word_count, time_info
    )

    suggestions = _generate_suggestions(
        score, filler_count, hedge_count, word_count, time_info
    )

    logger.info(f"Confidence score: {score} | Filler: {filler_count} | Hedging: {hedge_count}")

    return {
        "score": score,
        "filler_word_count": filler_count,
        "hedging_count": hedge_count,
        "confidence_signal_count": confidence_signal_count,
        "speech_speed": time_info["speech_speed"],
        "wpm": time_info.get("wpm"),
        "time_flag": time_info.get("time_flag"),
        "feedback": feedback,
        "suggestions": suggestions,
    }

# ── Feedback and Suggestion Generators ───────────────────────

def _generate_confidence_feedback(
    score: int,
    filler_count: int,
    hedge_count: int,
    confidence_signals: int,
    word_count: int,
    time_info: Dict
) -> str:
    """Generate a human-readable confidence feedback paragraph."""

    parts = []

    if score >= 80:
        parts.append("Your response demonstrates strong confidence.")
    elif score >= 60:
        parts.append("Your response shows moderate confidence with some room for improvement.")
    elif score >= 40:
        parts.append("Your response indicates some hesitation — try to sound more decisive.")
    else:
        parts.append("Your response suggests low confidence. Focus on speaking clearly and directly.")

    if filler_count > 5:
        parts.append(
            f"You used {filler_count} filler words, which can distract the interviewer. "
            "Practice pausing silently instead of filling gaps with 'um' or 'like'."
        )
    elif filler_count > 2:
        parts.append(f"You used {filler_count} filler words — a slight improvement would help.")

    if hedge_count > 3:
        parts.append(
            "You used several hedging phrases ('I think', 'maybe', 'I'm not sure'). "
            "State what you know directly, and if uncertain, say 'In my experience...' instead."
        )

    if confidence_signals > 2:
        parts.append(
            "Great use of structuring language ('for example', 'therefore', 'specifically') — "
            "this shows clear thinking."
        )

    if word_count < 30:
        parts.append("Your answer was brief. Interviewers expect detailed explanations — aim for 3-5 sentences minimum.")

    speed = time_info.get("speech_speed", "normal")
    if speed == "instant":
        parts.append("Your answer was submitted almost instantly — make sure you're engaging thoughtfully, not pasting pre-written text.")
    elif speed == "slow":
        parts.append("You took a while to respond — in real interviews, pausing too long can signal uncertainty.")

    return " ".join(parts)


def _generate_suggestions(
    score: int,
    filler_count: int,
    hedge_count: int,
    word_count: int,
    time_info: Dict
) -> list:
    """Generate a list of specific, actionable improvement tips."""
    suggestions = []

    if filler_count > 3:
        suggestions.append("Replace filler words with a brief silent pause — pauses project confidence, not weakness.")

    if hedge_count > 2:
        suggestions.append("Replace 'I think' with 'In my experience' or 'Based on my understanding' — sounds more authoritative.")

    if word_count < 40:
        suggestions.append("Expand your answers with a concrete example or explanation of *why* something works the way it does.")

    if score < 50:
        suggestions.append("Practice the STAR method (Situation, Task, Action, Result) to structure confident answers.")
        suggestions.append("Record yourself answering questions — listening back reveals habits you don't notice while speaking.")

    if not suggestions:
        suggestions.append("Keep up the clear, direct communication style.")

    return suggestions
