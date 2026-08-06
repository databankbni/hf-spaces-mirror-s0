"""Precision/recall metrics for curriculum-node resolution (GRO-224 / S5a).

Each labelled question names the true owning ``node_path`` for an enumeration or
multi-fact demand. The eval compares a resolver's ``primary_node_id`` (mapped back
to ``node_path``) against that gold label. Skipped resolutions (no FK, low
confidence) count as false negatives for recall and are excluded from the
precision denominator.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class LabelledNodeQuestion:
    question_id: str
    source_id: str
    expected_node_path: str
    # When the gold node is a parent and several descendant paths are acceptable.
    acceptable_node_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class QuestionNodeScore:
    question_id: str
    expected_node_path: str
    predicted_node_path: str | None
    policy: str
    correct: bool
    skipped: bool
    skipped_reason: str | None
    fallback_method: str | None
    confidence: float


@dataclass(frozen=True)
class NodeResolutionSummary:
    policy: str
    total: int
    predicted: int
    correct: int
    skipped: int
    precision: float
    recall: float


def _path_matches(expected: str, predicted: str | None, acceptable: Sequence[str]) -> bool:
    if predicted is None:
        return False
    if predicted == expected:
        return True
    return predicted in acceptable


def score_question(
    *,
    label: LabelledNodeQuestion,
    predicted_node_path: str | None,
    policy: str,
    skipped: bool,
    skipped_reason: str | None,
    fallback_method: str | None,
    confidence: float,
) -> QuestionNodeScore:
    correct = _path_matches(
        label.expected_node_path,
        predicted_node_path,
        label.acceptable_node_paths,
    )
    return QuestionNodeScore(
        question_id=label.question_id,
        expected_node_path=label.expected_node_path,
        predicted_node_path=predicted_node_path,
        policy=policy,
        correct=correct,
        skipped=skipped,
        skipped_reason=skipped_reason,
        fallback_method=fallback_method,
        confidence=confidence,
    )


def summarize_policy(scores: Iterable[QuestionNodeScore]) -> NodeResolutionSummary:
    rows = list(scores)
    if not rows:
        return NodeResolutionSummary(
            policy="",
            total=0,
            predicted=0,
            correct=0,
            skipped=0,
            precision=0.0,
            recall=0.0,
        )
    policy = rows[0].policy
    total = len(rows)
    skipped = sum(1 for r in rows if r.skipped)
    predicted = total - skipped
    correct = sum(1 for r in rows if r.correct)
    # Precision: of non-skipped predictions, how many hit the gold node.
    precision = correct / predicted if predicted else 0.0
    # Recall: of all labelled questions, how many resolved to the gold node.
    recall = correct / total if total else 0.0
    return NodeResolutionSummary(
        policy=policy,
        total=total,
        predicted=predicted,
        correct=correct,
        skipped=skipped,
        precision=round(precision, 4),
        recall=round(recall, 4),
    )
