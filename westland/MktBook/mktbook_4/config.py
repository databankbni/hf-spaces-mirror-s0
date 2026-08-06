"""Configuration for mktbook_4: The Synthetic Studio Economy."""
from __future__ import annotations

import pathlib

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = pathlib.Path(__file__).parent / ".env_4"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str
    database_path: str = "mktbook.db"
    host: str = "0.0.0.0"
    port: int = 8003

    # Fashion / image generation
    image_generation_model: str = "dall-e-3"
    image_size: str = "1024x1024"
    image_quality: str = "standard"
    image_storage_path: str = "/opt/mktbook/generated_images"

    # Cycle timing
    trend_cycle_interval: int = 300   # seconds between full trend cycles

    openai_model: str = "gpt-4o-mini"

    # Grading weights
    creativity_weight: float = 0.35
    influence_weight: float = 0.35
    aesthetic_weight: float = 0.20
    ethics_weight: float = 0.10


settings = Settings()  # type: ignore[call-arg]
