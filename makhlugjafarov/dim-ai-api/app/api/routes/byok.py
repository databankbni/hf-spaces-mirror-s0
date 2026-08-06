from typing import Literal

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field, SecretStr

from app.answer.domain.errors import GenerationError
from app.answer.domain.provider_policy import detect_provider
from app.answer.infrastructure.providers import _gemini_generation_config


router = APIRouter(prefix="/api/byok", tags=["byok"])

Provider = Literal["google", "openai", "anthropic"]


class ByokTestRequest(BaseModel):
    provider: Provider
    model: str = Field(min_length=1, max_length=120)
    api_key: SecretStr = Field(min_length=1)


class ByokTestResponse(BaseModel):
    ok: bool
    provider: Provider
    model: str
    message: str


@router.post("/test", response_model=ByokTestResponse)
def test_byok_key(request: ByokTestRequest) -> ByokTestResponse:
    try:
        detected_provider = detect_provider(request.model)
    except GenerationError as exc:
        return _failure(request, str(exc))

    if detected_provider != request.provider:
        return _failure(
            request,
            f"Selected provider does not match model prefix; detected {detected_provider}.",
        )

    api_key = request.api_key.get_secret_value()
    try:
        if request.provider == "google":
            _test_google_key(api_key=api_key, model=request.model)
        elif request.provider == "openai":
            _test_openai_key(api_key=api_key, model=request.model)
        else:
            _test_anthropic_key(api_key=api_key, model=request.model)
    except httpx.HTTPStatusError as exc:
        return _failure(request, f"Provider rejected the key or model with status {exc.response.status_code}.")
    except httpx.RequestError:
        return _failure(request, "Could not reach the provider. Try again later.")

    return ByokTestResponse(
        ok=True,
        provider=request.provider,
        model=request.model,
        message="Provider key test succeeded.",
    )


def _failure(request: ByokTestRequest, message: str) -> ByokTestResponse:
    return ByokTestResponse(ok=False, provider=request.provider, model=request.model, message=message)


def _test_google_key(*, api_key: str, model: str) -> None:
    response = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        json={
            "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
            "generationConfig": _gemini_generation_config(model=model, max_tokens=16),
        },
        timeout=20.0,
    )
    response.raise_for_status()


def _test_openai_key(*, api_key: str, model: str) -> None:
    response = httpx.get(
        f"https://api.openai.com/v1/models/{model}",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=20.0,
    )
    response.raise_for_status()


def _test_anthropic_key(*, api_key: str, model: str) -> None:
    response = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "ping"}],
        },
        timeout=20.0,
    )
    response.raise_for_status()
