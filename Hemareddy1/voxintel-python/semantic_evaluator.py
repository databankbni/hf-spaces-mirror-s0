"""
semantic_evaluator.py
----------------------
Evaluates user interview answers using semantic similarity.

Key design choice:
  - Uses sentence-transformers (SBERT) for embedding-based semantic scoring.
  - Falls back to TF-IDF cosine similarity if sentence-transformers unavailable.
  - Also computes keyword coverage score and answer completeness score.
  - Combines all three into an overall weighted score.

Why semantic over keyword-only?
  Paraphrased correct answers should score well, not just exact keyword matches.
"""

import re
import logging
import math
from typing import Dict, List

logger = logging.getLogger(__name__)

# Common words that carry no real subject-matter content on their own —
# used to detect near-empty/gibberish answers (e.g. "k", "idk", "ok") that
# SBERT can otherwise embed as spuriously similar to a real answer (a very
# short or out-of-vocabulary token doesn't land far from *everything* in
# embedding space, so raw cosine similarity alone isn't a reliable signal
# for near-zero-content input).
_STOPWORDS = {
    "a", "an", "the", "is", "it", "im", "i'm", "to", "of", "in", "on", "for",
    "and", "or", "but", "so", "ok", "okay", "k", "kk", "yes", "no", "yeah",
    "idk", "um", "uh", "well", "just", "like", "that", "this", "be", "am",
    "are", "was", "were", "not", "sure", "maybe",
}


def _content_word_count(text: str) -> int:
    """Count words that aren't stopwords/filler — a proxy for how much real
    subject-matter content an answer actually contains."""
    words = re.findall(r"[a-zA-Z']+", text.lower())
    return sum(1 for w in words if w not in _STOPWORDS and len(w) > 1)

# ── Model Loading (Lazy, with Fallback) ─────────────────────

_sbert_model = None  # loaded on first use

def _get_sbert_model():
    """Load the sentence-transformer model (downloads on first run ~90MB)."""
    global _sbert_model
    if _sbert_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading sentence-transformer model...")
            _sbert_model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Sentence-transformer model loaded.")
        except Exception as e:
            logger.warning(f"Sentence-transformers not available: {e}")
            _sbert_model = "unavailable"
    return _sbert_model if _sbert_model != "unavailable" else None

# ── Semantic Similarity ──────────────────────────────────────

def compute_semantic_similarity(user_answer: str, ideal_answer: str) -> float:
    """
    Compute cosine similarity between user answer and ideal answer using SBERT.
    Returns a score 0.0 - 1.0.
    Falls back to simple overlap ratio if SBERT unavailable.
    """
    if not ideal_answer.strip():
        # No ideal answer to compare against — neutral score
        return 0.5

    model = _get_sbert_model()

    if model:
        try:
            from sklearn.metrics.pairwise import cosine_similarity
            import numpy as np

            # Encode both answers into 384-dim vectors
            embeddings = model.encode([user_answer, ideal_answer])
            sim = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]

            # Clamp to [0, 1] (cosine can be slightly negative for very different texts)
            return float(max(0.0, min(1.0, sim)))
        except Exception as e:
            logger.warning(f"SBERT similarity failed: {e}")

    # Fallback: word overlap ratio (Jaccard similarity)
    user_words = set(user_answer.lower().split())
    ideal_words = set(ideal_answer.lower().split())
    if not ideal_words:
        return 0.5
    intersection = user_words & ideal_words
    union = user_words | ideal_words
    return len(intersection) / len(union) if union else 0.0


# ── Keyword Score ────────────────────────────────────────────

def compute_keyword_score(user_answer: str, keywords: List[str]) -> float:
    """
    Check what fraction of important keywords appear in the user's answer.
    Returns a score 0.0 - 1.0.
    """
    if not keywords:
        return 0.5  # no keywords to check — neutral

    lower_answer = user_answer.lower()
    matched = 0

    for kw in keywords:
        # Use word-boundary matching for short keywords
        pattern = r"\b" + re.escape(kw.lower()) + r"\b"
        if re.search(pattern, lower_answer):
            matched += 1

    return matched / len(keywords)


# ── Completeness Score ───────────────────────────────────────

def compute_completeness_score(user_answer: str, ideal_answer: str) -> float:
    """
    Estimate answer completeness based on:
    - Length relative to ideal answer
    - Sentence count
    - Presence of structural cues (examples, because, therefore, etc.)

    Returns a score 0.0 - 1.0.
    """
    user_words = len(user_answer.split())
    ideal_words = len(ideal_answer.split()) if ideal_answer else 50

    # Length score: penalize very short answers, reward approaching ideal length
    # Cap at 1.0 if answer is same length or longer than ideal
    length_ratio = min(1.0, user_words / max(ideal_words, 1))

    # Structural quality cues — signs of a well-formed answer
    cues = [
        r"\bbecause\b", r"\bfor example\b", r"\bsuch as\b", r"\btherefore\b",
        r"\bfor instance\b", r"\bin other words\b", r"\bspecifically\b",
        r"\bhowever\b", r"\bon the other hand\b", r"\bfirst\b.*\bsecond\b"
    ]
    cue_matches = sum(1 for cue in cues if re.search(cue, user_answer.lower()))
    cue_score = min(1.0, cue_matches / 3)  # 3 cues = full marks

    # Combine: 70% length-based, 30% structural quality
    return 0.7 * length_ratio + 0.3 * cue_score


# ── Main Evaluation Function ─────────────────────────────────

def evaluate_answer(user_answer: str, ideal_answer: str, keywords: List[str]) -> Dict:
    """
    Full answer evaluation pipeline.
    Returns a dict with individual scores and an overall weighted score.
    """
    if not user_answer or not user_answer.strip():
        return {
            "semantic_score": 0,
            "keyword_score": 0,
            "completeness_score": 0,
            "overall_score": 0,
        }

    # Run all three evaluations
    semantic_raw = compute_semantic_similarity(user_answer, ideal_answer)
    keyword_raw = compute_keyword_score(user_answer, keywords)
    completeness_raw = compute_completeness_score(user_answer, ideal_answer)

    # SBERT embeds even a single meaningless token ("k", "idk") somewhere in
    # semantic space that isn't orthogonal to a real answer, so raw cosine
    # similarity alone can look deceptively decent (~0.3-0.4) for answers with
    # no real content. Cap (never raise) the semantic score based on how much
    # actual subject-matter content the answer contains, so a near-empty
    # answer can't score respectably just because SBERT didn't hate it.
    content_words = _content_word_count(user_answer)
    if content_words == 0:
        semantic_raw = min(semantic_raw, 0.05)
    elif content_words == 1:
        semantic_raw = min(semantic_raw, 0.30)
    elif content_words == 2:
        semantic_raw = min(semantic_raw, 0.55)

    # Convert to 0-100 scale
    semantic_score = round(semantic_raw * 100)
    keyword_score = round(keyword_raw * 100)
    completeness_score = round(completeness_raw * 100)

    # Weighted overall score:
    # Semantic similarity is the most important (40%)
    # Keywords show technical vocabulary (35%)
    # Completeness shows depth (25%)
    overall_score = round(
        0.40 * semantic_score +
        0.35 * keyword_score +
        0.25 * completeness_score
    )

    logger.info(
        f"Scores → Semantic: {semantic_score}, "
        f"Keyword: {keyword_score}, "
        f"Completeness: {completeness_score}, "
        f"Overall: {overall_score}"
    )

    return {
        "semantic_score": semantic_score,
        "keyword_score": keyword_score,
        "completeness_score": completeness_score,
        "overall_score": overall_score,
    }
