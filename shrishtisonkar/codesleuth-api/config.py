"""
CodeSleuth AI — Configuration
Reads from .env file via pydantic-settings.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── OpenAI / Groq ─────────────────────────────────────────────────────────
    openai_api_key: str = ""
    openai_model: str = "qwen/qwen3-32b"
    openai_base_url: str = "https://api.groq.com/openai/v1"

    # ── GitHub ────────────────────────────────────────────────────────────────
    github_token: str = ""

    # ── Storage ───────────────────────────────────────────────────────────────
    storage_path: str = "./storage"
    chroma_persist_dir: str = "./storage/.vectors"   # now used for numpy store
    disk_cache_dir: str = "./storage/.cache"

    # ── App ───────────────────────────────────────────────────────────────────
    port: int = 8000
    log_level: str = "INFO"

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # ── Analysis thresholds ───────────────────────────────────────────────────
    oversized_file_threshold: int = 500
    coupling_threshold: int = 10
    max_repo_size_mb: int = 500

    # ── Embeddings ────────────────────────────────────────────────────────────
    embedding_model: str = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
