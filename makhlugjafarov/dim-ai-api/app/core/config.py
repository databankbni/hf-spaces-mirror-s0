from functools import lru_cache
from typing import Annotated

from pydantic import AliasChoices, AnyHttpUrl, BeforeValidator, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_csv(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise TypeError("Expected a comma-separated string or list")


CsvList = Annotated[list[str], BeforeValidator(_parse_csv)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DIM_AI_API_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "DIM AI API"
    app_version: str = "0.1.0"
    environment: str = "local"
    log_level: str = "INFO"
    dim_debug: bool = False

    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DIM_AI_API_DATABASE_URL", "DATABASE_URL", "SUPABASE_DB_URL"),
    )
    supabase_url: AnyHttpUrl | None = None
    supabase_jwt_secret: SecretStr | None = None
    supabase_jwt_audience: str | None = "authenticated"
    supabase_service_role_key: SecretStr | None = None

    # CORS — comma-separated list of allowed origins
    allowed_origins: CsvList = Field(
        default_factory=lambda: ["http://localhost:8080", "http://127.0.0.1:8080"]
    )

    # Abuse controls
    max_request_body_bytes: int = 1_048_576  # 1 MB
    rate_limit_requests_per_minute: int = 30  # per IP

    embedding_model_id: str = "bge-m3-dim-v1"
    allowed_llm_providers: CsvList = Field(
        default_factory=lambda: ["openai", "anthropic", "google", "openrouter", "openai_compatible"]
    )

    # LLM provider keys — used for local/dev when no per-user BYOK key is available
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("DIM_AI_API_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
    )
    gemini_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("DIM_AI_API_GEMINI_API_KEY", "GEMINI_API_KEY"),
    )
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("DIM_AI_API_OPENAI_API_KEY", "OPENAI_API_KEY"),
    )
    default_llm_model: str = "gemini-2.5-flash"

    @property
    def is_database_configured(self) -> bool:
        return bool(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
