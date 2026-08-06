"""Core HALT-CoT primitives.

The functions in this module are dependency-free so they can be used in API
integrations, tests, and backends that are not based on Hugging Face
Transformers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Iterable, Mapping, Sequence


EntropyUnit = str


@dataclass(frozen=True)
class AnswerCandidate:
    """A possible final answer and optional textual aliases for token scoring."""

    label: str
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        label = self.label.strip()
        if not label:
            raise ValueError("AnswerCandidate.label must not be empty")
        object.__setattr__(self, "label", label)
        object.__setattr__(
            self,
            "aliases",
            tuple(alias.strip() for alias in self.aliases if alias.strip()),
        )

    @property
    def texts(self) -> tuple[str, ...]:
        return (self.label, *self.aliases)


@dataclass(frozen=True)
class AnswerDistribution:
    """Normalized answer probabilities and their entropy."""

    probabilities: dict[str, float]
    entropy: float
    prediction: str


@dataclass(frozen=True)
class HaltCoTConfig:
    """Configuration for entropy-based chain-of-thought halting."""

    theta: float = 0.6
    max_steps: int = 12
    min_steps: int = 1
    consecutive_low_entropy: int = 2
    entropy_unit: EntropyUnit = "bits"
    step_max_new_tokens: int = 96
    step_min_new_tokens: int = 4
    prompt_template: str = "{question}\n\nLet's think step by step.\n"
    step_prefix: str = "Step {step}: "
    step_stop_strings: tuple[str, ...] = ("\nStep", "\nAnswer:", "\nFinal answer:", "\n")
    answer_probe: str = "\nTherefore, the final answer is "
    do_sample: bool = False
    temperature: float = 0.0
    top_p: float = 1.0

    def __post_init__(self) -> None:
        if self.theta < 0:
            raise ValueError("theta must be non-negative")
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        if self.min_steps < 1:
            raise ValueError("min_steps must be at least 1")
        if self.min_steps > self.max_steps:
            raise ValueError("min_steps cannot exceed max_steps")
        if self.consecutive_low_entropy < 1:
            raise ValueError("consecutive_low_entropy must be at least 1")
        if self.entropy_unit not in {"bits", "nats"}:
            raise ValueError("entropy_unit must be 'bits' or 'nats'")
        if self.step_max_new_tokens < 1:
            raise ValueError("step_max_new_tokens must be at least 1")
        if self.step_min_new_tokens < 0:
            raise ValueError("step_min_new_tokens must be non-negative")
        if self.temperature < 0:
            raise ValueError("temperature must be non-negative")
        if not 0 < self.top_p <= 1:
            raise ValueError("top_p must be in (0, 1]")


@dataclass(frozen=True)
class HaltDecision:
    """Controller state after observing one entropy value."""

    should_halt: bool
    low_entropy_streak: int


@dataclass(frozen=True)
class HaltCoTStep:
    """One generated reasoning step plus HALT-CoT diagnostics."""

    index: int
    text: str
    entropy: float
    prediction: str
    probabilities: dict[str, float]
    halted: bool
    generated_tokens: int = 0


@dataclass(frozen=True)
class HaltCoTResult:
    """Final output of a HALT-CoT run."""

    answer: str
    halted: bool
    steps: tuple[HaltCoTStep, ...]
    reasoning: str
    generated_tokens: int


class EntropyHaltingController:
    """Implements the threshold and consecutive-step guard from the paper."""

    def __init__(self, config: HaltCoTConfig):
        self.config = config
        self.low_entropy_streak = 0

    def observe(self, entropy: float, step_index: int) -> HaltDecision:
        if step_index < self.config.min_steps:
            self.low_entropy_streak = 0
            return HaltDecision(False, self.low_entropy_streak)

        if entropy < self.config.theta:
            self.low_entropy_streak += 1
        else:
            self.low_entropy_streak = 0

        return HaltDecision(
            should_halt=self.low_entropy_streak >= self.config.consecutive_low_entropy,
            low_entropy_streak=self.low_entropy_streak,
        )


def normalize_candidates(
    candidates: Sequence[str | AnswerCandidate],
) -> tuple[AnswerCandidate, ...]:
    """Convert user-provided strings or candidates into validated candidates."""

    normalized: list[AnswerCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        item = candidate if isinstance(candidate, AnswerCandidate) else AnswerCandidate(str(candidate))
        key = item.label.casefold()
        if key in seen:
            raise ValueError(f"Duplicate answer candidate: {item.label!r}")
        seen.add(key)
        normalized.append(item)

    if len(normalized) < 2:
        raise ValueError("At least two answer candidates are required")
    return tuple(normalized)


def softmax(scores: Mapping[str, float]) -> dict[str, float]:
    """Stable softmax over a label-to-score mapping."""

    if not scores:
        raise ValueError("scores must not be empty")

    max_score = max(scores.values())
    weights = {label: math.exp(score - max_score) for label, score in scores.items()}
    total = sum(weights.values())
    if total == 0 or not math.isfinite(total):
        raise ValueError("scores produced an invalid softmax normalization")
    return {label: weight / total for label, weight in weights.items()}


def entropy_from_probabilities(
    probabilities: Mapping[str, float],
    entropy_unit: EntropyUnit = "bits",
) -> float:
    """Compute Shannon entropy for an answer distribution."""

    if entropy_unit not in {"bits", "nats"}:
        raise ValueError("entropy_unit must be 'bits' or 'nats'")
    if not probabilities:
        raise ValueError("probabilities must not be empty")

    total = sum(probabilities.values())
    if not math.isclose(total, 1.0, rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError(f"probabilities must sum to 1, got {total}")

    log = math.log2 if entropy_unit == "bits" else math.log
    return -sum(p * log(p) for p in probabilities.values() if p > 0)


def answer_distribution_from_scores(
    scores: Mapping[str, float],
    entropy_unit: EntropyUnit = "bits",
) -> AnswerDistribution:
    """Turn answer logits/scores into probabilities, entropy, and argmax answer."""

    probabilities = softmax(scores)
    entropy = entropy_from_probabilities(probabilities, entropy_unit)
    prediction = max(probabilities, key=probabilities.__getitem__)
    return AnswerDistribution(
        probabilities=dict(probabilities),
        entropy=entropy,
        prediction=prediction,
    )


def yes_no_candidates() -> tuple[AnswerCandidate, AnswerCandidate]:
    """Standard StrategyQA-style answer set."""

    return (
        AnswerCandidate("Yes", aliases=("yes", "YES")),
        AnswerCandidate("No", aliases=("no", "NO")),
    )


def multiple_choice_candidates(
    labels: Iterable[str] = ("A", "B", "C", "D", "E"),
) -> tuple[AnswerCandidate, ...]:
    """Create option candidates with common first-token answer spellings."""

    candidates = []
    for raw_label in labels:
        label = raw_label.strip()
        if not label:
            continue
        candidates.append(
            AnswerCandidate(
                label,
                aliases=(
                    label.lower(),
                    f"({label})",
                    f"{label}.",
                    f"{label})",
                ),
            )
        )
    return normalize_candidates(candidates)


def integer_candidates(start: int = 0, end: int = 100) -> tuple[AnswerCandidate, ...]:
    """Numeric answer candidates for math-style tasks."""

    if start > end:
        raise ValueError("start cannot exceed end")
    return tuple(AnswerCandidate(str(value)) for value in range(start, end + 1))


_NUMBER_RE = re.compile(r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")


def numeric_candidates_from_texts(
    texts: Iterable[str],
    extra_integers: tuple[int, int] | None = (0, 100),
    max_candidates: int | None = None,
) -> tuple[AnswerCandidate, ...]:
    """Build a numeric candidate set from answer strings plus an integer range."""

    labels: dict[str, None] = {}
    for text in texts:
        for match in _NUMBER_RE.findall(text):
            labels[match.replace(",", "")] = None

    if extra_integers is not None:
        start, end = extra_integers
        for value in range(start, end + 1):
            labels[str(value)] = None

    sorted_labels = sorted(labels, key=_numeric_sort_key)
    if max_candidates is not None:
        sorted_labels = sorted_labels[:max_candidates]
    return normalize_candidates([AnswerCandidate(label) for label in sorted_labels])


def _numeric_sort_key(label: str) -> tuple[int, float | str]:
    try:
        return (0, float(label))
    except ValueError:
        return (1, label)


def format_reasoning(steps: Sequence[HaltCoTStep]) -> str:
    """Render generated steps for logs, demos, and model cards."""

    return "\n".join(f"Step {step.index}: {step.text}".rstrip() for step in steps)
