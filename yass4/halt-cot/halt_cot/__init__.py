"""HALT-CoT: entropy-based early stopping for chain-of-thought reasoning."""

from .core import (
    AnswerCandidate,
    AnswerDistribution,
    EntropyHaltingController,
    HaltCoTConfig,
    HaltCoTResult,
    HaltCoTStep,
    HaltDecision,
    answer_distribution_from_scores,
    entropy_from_probabilities,
    format_reasoning,
    integer_candidates,
    multiple_choice_candidates,
    normalize_candidates,
    numeric_candidates_from_texts,
    softmax,
    yes_no_candidates,
)

__all__ = [
    "AnswerCandidate",
    "AnswerDistribution",
    "EntropyHaltingController",
    "HaltCoTConfig",
    "HaltCoTResult",
    "HaltCoTStep",
    "HaltDecision",
    "answer_distribution_from_scores",
    "entropy_from_probabilities",
    "format_reasoning",
    "integer_candidates",
    "multiple_choice_candidates",
    "normalize_candidates",
    "numeric_candidates_from_texts",
    "softmax",
    "yes_no_candidates",
]
