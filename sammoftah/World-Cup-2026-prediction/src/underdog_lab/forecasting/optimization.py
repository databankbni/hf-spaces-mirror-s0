"""Small dependency-free optimization helpers for scalar forecast tuning."""

from __future__ import annotations

from collections.abc import Callable


def bounded_minimize(
    objective: Callable[[float], float],
    lower: float,
    upper: float,
    *,
    tolerance: float = 1e-10,
    max_iterations: int = 200,
) -> float:
    """Minimize a unimodal scalar objective with golden-section search."""
    if lower >= upper:
        raise ValueError("lower bound must be less than upper bound")

    ratio = (5.0**0.5 - 1.0) / 2.0
    left = upper - ratio * (upper - lower)
    right = lower + ratio * (upper - lower)
    left_value = objective(left)
    right_value = objective(right)

    for _ in range(max_iterations):
        if upper - lower <= tolerance:
            break
        if left_value <= right_value:
            upper = right
            right = left
            right_value = left_value
            left = upper - ratio * (upper - lower)
            left_value = objective(left)
        else:
            lower = left
            left = right
            left_value = right_value
            right = lower + ratio * (upper - lower)
            right_value = objective(right)

    return (lower + upper) / 2.0
