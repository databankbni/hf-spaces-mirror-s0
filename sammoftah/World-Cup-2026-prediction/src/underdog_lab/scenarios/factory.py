from __future__ import annotations

from underdog_lab.config import EXTRACTOR_BACKEND
from underdog_lab.scenarios.extractor import ScenarioExtractor
from underdog_lab.scenarios.llama_cpp_extractor import LlamaCppExtractor
from underdog_lab.scenarios.mock_extractor import MockScenarioExtractor
from underdog_lab.scenarios.python_llama_cpp_extractor import PythonLlamaCppExtractor


class FallbackExtractor:
    name = "SmolLM2-360M via llama.cpp (validated fallback enabled)"

    def __init__(self) -> None:
        self.primary = PythonLlamaCppExtractor()
        self.fallback = MockScenarioExtractor()
        self.last_backend = self.primary.name
        self.last_error: str | None = None
        # `cached_property` does not cache exceptions, so a failed model
        # load (e.g. blocked download) would otherwise be retried -- with
        # huggingface_hub's exponential backoff on 429/5xx -- on every
        # single request. Remember a hard failure so we go straight to the
        # deterministic fallback for the rest of this process's life.
        self.primary_unavailable = False

    def extract(self, text, match):
        if self.primary_unavailable:
            self.last_backend = self.fallback.name
            return self.fallback.extract(text, match)
        try:
            result = self.primary.extract(text, match)
            recovery = self.fallback.extract(text, match)
            meaningful_factors = [
                factor
                for factor in result.factors
                if factor.severity * factor.certainty >= 0.05
            ]
            if not meaningful_factors and recovery.factors:
                self.last_backend = self.fallback.name
                self.last_error = (
                    "Local model returned no meaningful supported factors; "
                    "deterministic recovery applied."
                )
                return recovery
            self.last_backend = self.primary.name
            self.last_error = None
            return result
        except Exception as error:
            self.primary_unavailable = True
            self.last_backend = self.fallback.name
            self.last_error = (
                f"{type(error).__name__}: {error} "
                "(primary extractor disabled for the rest of this session; "
                "using deterministic fallback)"
            )
            return self.fallback.extract(text, match)

    def warmup(self) -> None:
        try:
            self.primary.warmup()
            self.last_backend = self.primary.name
            self.last_error = None
        except Exception as error:
            self.primary_unavailable = True
            self.last_backend = self.fallback.name
            self.last_error = f"{type(error).__name__}: {error}"


def build_extractor() -> ScenarioExtractor:
    if EXTRACTOR_BACKEND == "auto":
        return FallbackExtractor()
    if EXTRACTOR_BACKEND == "python_llama_cpp":
        return PythonLlamaCppExtractor()
    if EXTRACTOR_BACKEND == "llama_cpp":
        return LlamaCppExtractor()
    return MockScenarioExtractor()
