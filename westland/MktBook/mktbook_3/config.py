"""Configuration for mktbook_3: The Agentic Economy."""
from __future__ import annotations

import pathlib

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = pathlib.Path(__file__).parent / ".env_3"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str
    database_path: str = "mktbook.db"
    host: str = "0.0.0.0"
    port: int = 8002

    negotiation_cooldown: int = 30
    max_negotiation_turns: int = 15

    openai_model: str = "gpt-4o-mini"


settings = Settings()  # type: ignore[call-arg]
