"""Configuration for mktbook_5: The Bayesian Showdown."""
from __future__ import annotations

import pathlib

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = pathlib.Path(__file__).parent / ".env_5"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str
    database_path: str = "mktbook.db"
    host: str = "0.0.0.0"
    port: int = 8004

    # A/B test settings
    pitch_interval: int = 45          # seconds between pitches
    bayesian_prior_mean: float = 50.0
    bayesian_prior_variance: float = 100.0

    openai_model: str = "gpt-4o-mini"


settings = Settings()  # type: ignore[call-arg]
