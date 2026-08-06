"""
plagiarism_checker.py
----------------------
Detects potentially plagiarized or AI-generated interview answers.

Approach (lightweight, no internet required):
  1. Pattern repetition detection — AI often repeats sentence structures.
  2. Vocabulary uniformity — AI uses overly formal, consistent vocabulary.
  3. Sentence length variance — human writing has more variation.
  4. Suspicious submission speed — answer appeared too fast to be typed.
  5. Common AI phrase detection — known GPT-style openers.
  6. Punctuation consistency — AI is unusually consistent.

NOTE: This is a heuristic system, NOT a guaranteed detector.
      It produces a likelihood score, not a verdict.
      The goal is to flag suspicious patterns, not to accuse candidates.
"""

import re
import math
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


# ── Minimum Content Thresholds ────────────────────────────────
# Submissions below these thresholds are too small to analyse meaningfully.
# Returning a fake similarity score for "hello" or a 2-line snippet would
# mislead interviewers — so we short-circuit before any scoring.

MIN_MEANINGFUL_TOKENS = 20   # words/tokens
MIN_CODE_LINES = 5           # non-blank lines for code submissions

# ── Programming Language Detection ───────────────────────────
# Used to scope plagiarism DB lookups to matching-language files only.
# Returns a language string or "unknown".

LANG_SIGNATURES = [
    # (language_name, [(pattern, weight), ...])
    ("python",     [(r"\bdef\b", 2), (r"\bimport\b", 1), (r":\s*$", 1), (r"\bprint\(", 1), (r"#.*$", 1)]),
    ("javascript", [(r"\bconst\b", 2), (r"\blet\b", 2), (r"\bfunction\b", 2), (r"=>", 2), (r"\bconsole\.log\(", 1)]),
    ("typescript", [(r":\s*(string|number|boolean|any)\b", 3), (r"\binterface\b", 3), (r"\btype\b", 2), (r"\benum\b", 2)]),
    ("java",       [(r"\bpublic\s+class\b", 3), (r"\bSystem\.out\.println\(", 2), (r"\bvoid\b", 1), (r"\bnew\s+\w+\(", 1)]),
    ("c++",        [(r"#include\s*<", 3), (r"\bstd::", 2), (r"\bcout\b", 2), (r"\bcin\b", 1)]),
    ("c",          [(r"#include\s*<stdio", 3), (r"\bprintf\(", 2), (r"\bscanf\(", 2), (r"\bmalloc\(", 1)]),
    ("csharp",     [(r"\busing\s+System", 3), (r"\bConsole\.Write", 2), (r"\bnamespace\b", 2), (r"\.cs\b", 1)]),
    ("go",         [(r"\bfunc\s+\w+\(", 3), (r"\bpackage\s+main\b", 3), (r"\bfmt\.Print", 2), (r":=", 2)]),
    ("rust",       [(r"\bfn\s+\w+\(", 3), (r"\blet\s+mut\b", 2), (r"\bprintln!", 2), (r"\buse\s+std::", 2)]),
    ("sql",        [(r"\bSELECT\b", 3), (r"\bFROM\b", 2), (r"\bWHERE\b", 2), (r"\bINSERT\s+INTO\b", 2)]),
    ("php",        [(r"<\?php", 4), (r"\$\w+", 2), (r"\becho\b", 2)]),
    ("html",       [(r"<html", 3), (r"<div", 2), (r"<body", 2), (r"<!DOCTYPE", 3)]),
]


def detect_language(code: str) -> str:
    """
    Heuristically detect the programming language of submitted code.
    Returns the best-match language name or "unknown".
    Scores each candidate language by pattern matching and returns the winner.
    """
    if not code or not code.strip():
        return "unknown"

    scores = {}
    for lang, patterns in LANG_SIGNATURES:
        score = 0
        for pattern, weight in patterns:
            if re.search(pattern, code, re.IGNORECASE | re.MULTILINE):
                score += weight
        if score > 0:
            scores[lang] = score

    if not scores:
        return "unknown"

    return max(scores, key=scores.get)


def count_meaningful_tokens(text: str) -> int:
    """Count words/tokens excluding pure whitespace and single-char symbols."""
    tokens = re.findall(r"\b\w{2,}\b", text)
    return len(tokens)


def count_meaningful_lines(text: str) -> int:
    """Count non-blank, non-comment-only lines."""
    lines = text.split("\n")
    meaningful = [
        l for l in lines
        if l.strip() and not l.strip().startswith(("#", "//", "/*", "*", "<!--"))
    ]
    return len(meaningful)


def is_content_sufficient(text: str) -> tuple:
    """
    Returns (is_sufficient: bool, reason: str).
    If False, plagiarism check should be skipped.
    """
    if not text or not text.strip():
        return False, "Empty submission."

    token_count = count_meaningful_tokens(text)
    line_count = count_meaningful_lines(text)

    if token_count < MIN_MEANINGFUL_TOKENS and line_count < MIN_CODE_LINES:
        return False, (
            f"Insufficient content for plagiarism analysis. "
            f"Submission has only {token_count} meaningful tokens and {line_count} code lines. "
            f"Minimum required: {MIN_MEANINGFUL_TOKENS} tokens or {MIN_CODE_LINES} lines."
        )

    return True, "ok"


# ── Common AI-Generated Opener Patterns ──────────────────────
# These phrases frequently appear in LLM-generated text.

AI_OPENER_PATTERNS = [
    r"^certainly[,!]",
    r"^great question[,!]",
    r"^of course[,!]",
    r"^absolutely[,!]",
    r"^sure[,!]",
    r"as an ai",
    r"as a language model",
    r"i don't have personal experience",
    r"it's worth noting that",
    r"in summary,? it's important to",
    r"it is important to note",
    r"this is a nuanced",
    r"let me explain this",
    r"to put it simply",
]

# ── Generic Filler Phrases Common in AI Text ─────────────────
AI_FILLER_PHRASES = [
    r"in conclusion",
    r"to summarize",
    r"overall[,.]",
    r"in essence",
    r"it is worth noting",
    r"it's important to understand",
    r"fundamentally[,.]",
    r"at its core[,.]",
    r"to elaborate",
    r"needless to say",
]

# ── Statistical Text Analysis ─────────────────────────────────

def get_sentence_lengths(text: str) -> List[int]:
    """Split text into sentences and return list of word counts per sentence."""
    # Split on common sentence-ending punctuation
    sentences = re.split(r"[.!?]+", text)
    lengths = [len(s.split()) for s in sentences if s.strip()]
    return lengths


def compute_variance(values: List[float]) -> float:
    """Compute population variance of a list of numbers."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


def compute_type_token_ratio(text: str) -> float:
    """
    Type-Token Ratio (TTR) = unique words / total words.
    AI text tends to have HIGHER TTR (more varied vocabulary).
    Human answers tend to repeat certain words naturally.
    TTR alone is not diagnostic but contributes to the overall signal.
    """
    words = re.findall(r"\b\w+\b", text.lower())
    if not words:
        return 0.0
    return len(set(words)) / len(words)


def count_pattern_matches(text: str, patterns: List[str]) -> int:
    """Count how many patterns from a list match in the text."""
    lower = text.lower()
    return sum(1 for p in patterns if re.search(p, lower))

# ── Submission Speed Check ────────────────────────────────────

def is_suspiciously_fast(text: str, time_taken_seconds: int) -> bool:
    """
    Returns True if the answer was submitted faster than a human could type it.
    Average typing speed: ~40 words/minute = ~0.67 words/second.
    We use a generous threshold of 2 words/second to allow for fast typists.
    """
    word_count = len(text.split())
    if time_taken_seconds <= 0:
        return False  # No time data — can't judge
    wps = word_count / time_taken_seconds  # words per second
    return wps > 2.5  # faster than ~150 wpm typed → suspicious

# ── Sentence Structure Repetition ────────────────────────────

def compute_structure_repetition(text: str) -> float:
    """
    AI often produces sentences with very similar grammatical structure.
    We approximate this by checking if sentence-starting patterns repeat.
    Returns 0.0 (no repetition) to 1.0 (high repetition).
    """
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    if len(sentences) < 3:
        return 0.0

    # Extract the first 1-2 words of each sentence as a "starter"
    starters = []
    for s in sentences:
        words = s.split()
        starter = " ".join(words[:2]).lower() if len(words) >= 2 else words[0].lower()
        starters.append(starter)

    # How many starters are duplicated?
    unique_starters = len(set(starters))
    repetition_ratio = 1 - (unique_starters / len(starters))
    return repetition_ratio

# ── Main Plagiarism / AI Check ────────────────────────────────

def check_plagiarism(text: str, time_taken_seconds: int = 0) -> Dict:
    """
    Run all heuristic checks and produce:
      - score: 0-100 likelihood of being plagiarized/AI-generated
      - ai_score: 0-100 likelihood of being AI-generated specifically
      - is_original: bool (True if score < 50)
      - feedback: human-readable explanation
    """
    # ── Pre-check: minimum content threshold ────────────────
    sufficient, reason = is_content_sufficient(text)
    if not sufficient:
        return {
            "score": 0,
            "ai_score": 0,
            "is_original": True,
            "language": "unknown",
            "feedback": reason,
            "insufficient_content": True,
        }

    # ── Detect programming language (for DB-scope optimisation) ──
    detected_language = detect_language(text)

    word_count = len(text.split())

    # ── Run all checks ───────────────────────────────────────

    # 1. AI opener patterns (strong signal)
    ai_opener_hits = count_pattern_matches(text, AI_OPENER_PATTERNS)

    # 2. AI filler phrases (moderate signal)
    ai_filler_hits = count_pattern_matches(text, AI_FILLER_PHRASES)

    # 3. Sentence length variance (low variance → possibly AI)
    sentence_lengths = get_sentence_lengths(text)
    length_variance = compute_variance(sentence_lengths)
    # High variance = human-like. Low variance = possibly AI.
    # Normalize: variance < 5 gets penalty, > 30 gets none.
    variance_penalty = max(0, 1 - (length_variance / 30))

    # 4. Type-token ratio (very high TTR can indicate AI's rich vocabulary)
    ttr = compute_type_token_ratio(text)
    # TTR > 0.85 with long text is unusual for spontaneous human answers
    ttr_penalty = 1.0 if (ttr > 0.85 and word_count > 60) else 0.0

    # 5. Submission speed
    speed_suspicious = is_suspiciously_fast(text, time_taken_seconds)

    # 6. Sentence structure repetition
    structure_rep = compute_structure_repetition(text)

    # ── Compute Scores ───────────────────────────────────────

    # AI score: weight each signal
    ai_score_raw = (
        ai_opener_hits * 25 +       # Very strong signal
        ai_filler_hits * 10 +       # Moderate signal
        variance_penalty * 20 +     # Low sentence variety → AI-like
        ttr_penalty * 15 +          # Suspiciously rich vocabulary
        structure_rep * 20          # Repetitive sentence structure
    )
    ai_score = int(min(100, ai_score_raw))

    # Overall plagiarism score adds the speed check
    plagiarism_score_raw = ai_score_raw + (30 if speed_suspicious else 0)
    plagiarism_score = int(min(100, plagiarism_score_raw))

    # Only flag as non-original above 75% — prevents false positives on short/common answers
    is_original = plagiarism_score < 75

    # ── Generate Feedback ────────────────────────────────────
    feedback = _generate_plagiarism_feedback(
        plagiarism_score, ai_score, ai_opener_hits,
        ai_filler_hits, speed_suspicious, structure_rep
    )

    logger.info(
        f"Plagiarism score: {plagiarism_score} | AI score: {ai_score} | "
        f"Original: {is_original} | Language: {detected_language}"
    )

    return {
        "score": plagiarism_score,
        "ai_score": ai_score,
        "is_original": is_original,
        "language": detected_language,
        "insufficient_content": False,
        "flags": {
            "ai_opener_detected": ai_opener_hits > 0,
            "suspicious_speed": speed_suspicious,
            "low_sentence_variance": length_variance < 5,
            "high_structure_repetition": structure_rep > 0.5,
        },
        "feedback": feedback,
    }


def _generate_plagiarism_feedback(
    score: int,
    ai_score: int,
    opener_hits: int,
    filler_hits: int,
    speed_suspicious: bool,
    structure_rep: float,
) -> str:
    """Generate a clear, non-accusatory feedback message."""

    if score < 25:
        return "Your answer appears original and genuine. Good job communicating in your own words."

    parts = []

    if score >= 25 and score < 50:
        parts.append("Your answer shows some patterns that may indicate external assistance.")
    elif score >= 50 and score < 75:
        parts.append("Your answer contains multiple patterns commonly associated with AI-generated or copied text.")
    else:
        parts.append("Your answer shows strong signals of being AI-generated or copied.")

    if opener_hits > 0:
        parts.append(
            "It starts with a phrase commonly used by AI assistants "
            "('Certainly!', 'Great question', 'Of course!', etc.)."
        )

    if filler_hits > 1:
        parts.append(
            f"It contains {filler_hits} generic AI-style transitional phrases "
            "('In conclusion', 'It's important to note', etc.)."
        )

    if speed_suspicious:
        parts.append(
            "The answer was submitted very quickly relative to its length, "
            "suggesting it may have been pasted rather than typed."
        )

    if structure_rep > 0.5:
        parts.append(
            "Many sentences follow the same grammatical pattern, "
            "which is a known characteristic of AI-generated text."
        )

    parts.append("For best results, answer in your own words using your genuine understanding.")

    return " ".join(parts)
