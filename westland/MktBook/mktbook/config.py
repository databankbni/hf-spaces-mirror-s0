from __future__ import annotations

import pathlib

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = pathlib.Path(__file__).parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    fal_api_key: str = ""
    database_path: str = "mktbook.db"
    host: str = "0.0.0.0"
    port: int = 8000

    conversation_min_interval: int = 30
    conversation_max_interval: int = 120
    conversation_turns: int = 4

    openai_model: str = "deepseek-chat"
    openai_api_base: str = "https://api.deepseek.com"

    # Admin auth
    admin_password: str = "mktbook"
    secret_key: str = "mktbook-secret-change-me"

    # LTI 1.3
    lti_private_key_path: str = "/opt/mktbook/lti_private_key.pem"
    lti_tool_base_url: str = "https://yourdomain.com"

    # Telemetry (usage email notifications)
    telemetry_enabled: bool = False
    telemetry_recipient: str = "mktbook_simulation@proton.me"
    gmail_user: str = ""          # Gmail address to send FROM (e.g. yourname@gmail.com)
    gmail_app_password: str = ""  # Google App Password (16-char, not your regular password)


settings = Settings()  # type: ignore[call-arg]

# Resolve HF_Revised environment variable if present
import os
hf_revised_val = os.environ.get("HF_Revised")
if hf_revised_val:
    settings.openai_api_key = hf_revised_val

if settings.openai_api_key == "HF_Revised":
    settings.openai_api_key = os.environ.get("HF_Revised", "HF_Revised")
