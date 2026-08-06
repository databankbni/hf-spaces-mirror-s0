from __future__ import annotations

from underdog_lab.domain import Forecast, MatchRecord
from underdog_lab.forecasting.poisson import forecast_from_lambdas
from underdog_lab.scenarios.adjustments import apply_extraction
from underdog_lab.scenarios.extractor import ScenarioExtractor
from underdog_lab.scenarios.schemas import AdjustmentResult, ScenarioExtraction


def baseline_forecast(match: MatchRecord) -> Forecast:
    return forecast_from_lambdas(match.lambda_home, match.lambda_away)


def analyze_scenario(
    match: MatchRecord,
    text: str,
    extractor: ScenarioExtractor,
) -> tuple[ScenarioExtraction, AdjustmentResult, Forecast]:
    extraction = extractor.extract(text, match)
    result = apply_extraction(match, extraction)
    forecast = forecast_from_lambdas(result.lambda_home, result.lambda_away)
    return extraction, result, forecast
