from __future__ import annotations

import math

from underdog_lab.domain import Forecast, Outcome

OUTCOMES: tuple[Outcome, ...] = ("home", "draw", "away")


def apply_vector_scaling(forecast: Forecast, parameters: list[float]) -> Forecast:
    if len(parameters) != 5:
        raise ValueError("vector scaling requires five parameters")
    scales = parameters[:3]
    biases = (parameters[3], parameters[4], 0.0)
    probabilities = (forecast.p_home, forecast.p_draw, forecast.p_away)
    logits = [
        scale * math.log(max(probability, 1e-15)) + bias
        for scale, probability, bias in zip(scales, probabilities, biases)
    ]
    maximum = max(logits)
    raw = [math.exp(value - maximum) for value in logits]
    total = sum(raw)
    data = forecast.model_dump()
    data.update(
        {
            "p_home": raw[0] / total,
            "p_draw": raw[1] / total,
            "p_away": raw[2] / total,
        }
    )
    return Forecast(**data)


def fit_vector_scaling(
    rows: list[tuple[Forecast, Outcome]],
    *,
    regularization: float,
    iterations: int = 350,
    learning_rate: float = 0.03,
) -> list[float]:
    if not rows:
        raise ValueError("at least one forecast row is required")
    parameters = [1.0, 1.0, 1.0, 0.0, 0.0]
    first = [0.0] * 5
    second = [0.0] * 5
    beta1 = 0.9
    beta2 = 0.999
    for step in range(1, iterations + 1):
        gradient = [0.0] * 5
        for forecast, outcome in rows:
            calibrated = apply_vector_scaling(forecast, parameters)
            probs = (calibrated.p_home, calibrated.p_draw, calibrated.p_away)
            logs = (
                math.log(max(forecast.p_home, 1e-15)),
                math.log(max(forecast.p_draw, 1e-15)),
                math.log(max(forecast.p_away, 1e-15)),
            )
            target = OUTCOMES.index(outcome)
            differences = [
                probability - (1.0 if index == target else 0.0)
                for index, probability in enumerate(probs)
            ]
            for index in range(3):
                gradient[index] += differences[index] * logs[index]
            gradient[3] += differences[0]
            gradient[4] += differences[1]
        count = len(rows)
        for index in range(5):
            center = 1.0 if index < 3 else 0.0
            gradient[index] = (
                gradient[index] / count
                + regularization * (parameters[index] - center)
            )
            first[index] = beta1 * first[index] + (1 - beta1) * gradient[index]
            second[index] = (
                beta2 * second[index] + (1 - beta2) * gradient[index] ** 2
            )
            corrected_first = first[index] / (1 - beta1**step)
            corrected_second = second[index] / (1 - beta2**step)
            parameters[index] -= (
                learning_rate
                * corrected_first
                / (corrected_second**0.5 + 1e-8)
            )
    return parameters
