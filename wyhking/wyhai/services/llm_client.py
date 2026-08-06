from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional


ROOT = Path(__file__).resolve().parents[1]


MODEL_CONFIG: Dict[str, list[str]] = {
    "intent_routing": [
        # qwen-flash is currently the fastest healthy free-quota endpoint in
        # the deployed DashScope account. Keep the newer aliases as fallbacks
        # because availability differs by account/region.
        "qwen-flash",
        "qwen3.6-flash",
        "qwen3.5-flash",
        "tongyi-intent-detect-v3",
    ],
    "slot_extraction": [
        "qwen3.6-flash",
        "qwen-plus-latest",
        "qwen3.7-plus",
        "qwen3.6-plus",
    ],
    "light_reply": [
        "qwen-flash",
        "qwen3.6-flash",
        "qwen3.5-flash",
    ],
    "business_explanation": [
        "qwen-plus-latest",
        "qwen3.6-flash",
        "qwen3.7-plus",
        "qwen3.6-plus",
    ],
    "customer_script": [
        "qwen-plus-latest",
        "qwen3.6-flash",
        "qwen3.7-plus",
        "qwen3.6-plus",
    ],
    "report_generation": [
        "qwen-plus-latest",
        "qwen3.6-flash",
        "qwen3.7-plus",
        "qwen3.6-plus",
        "qwen3.7-max",
    ],
    "complex_fallback": [
        "qwen3.7-max-2026-06-08",
        "qwen3.7-max",
        "qwen3-max",
        "qwen-max",
        "qwen3-235b-a22b-thinking-2507",
        "qwen3-235b-a22b-instruct-2507",
    ],
}

NON_FREE_MODEL_BLOCKLIST = {"qwen-turbo"}


_MODEL_CIRCUIT_LOCK = threading.Lock()
_MODEL_FAILURE_UNTIL: Dict[str, float] = {}
_MODEL_FAILURE_REASON: Dict[str, str] = {}


@dataclass
class LLMResult:
    ok: bool
    content: str = ""
    model: str = ""
    fallback_used: bool = False
    fallback_reason: str = ""
    latency_ms: int = 0


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.environ.get(name, default)))
    except Exception:
        return default


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value not in (None, ""):
            return str(value)
    return default


def _load_runtime_env() -> None:
    """Load local runtime secrets/config without overriding exported env vars."""
    path = ROOT / "runtime" / "local_secrets.env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and not os.environ.get(key):
            os.environ[key] = value


def _parse_model_list(value: str) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except Exception:
        pass
    return [part.strip() for part in re.split(r"[,;\s]+", value) if part.strip()]


def _unique_models(models: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for model in models:
        value = str(model or "").strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _load_model_config() -> Dict[str, list[str]]:
    config = {key: list(value) for key, value in MODEL_CONFIG.items()}
    raw_json = os.environ.get("LLM_MODEL_CONFIG_JSON", "").strip()
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict):
                for key, value in parsed.items():
                    models = value if isinstance(value, list) else _parse_model_list(str(value))
                    config[str(key)] = [str(item).strip() for item in models if str(item).strip()]
        except Exception:
            pass
    for key in list(config):
        env_key = f"LLM_MODELS_{key.upper()}"
        env_models = _parse_model_list(os.environ.get(env_key, ""))
        if env_models:
            config[key] = env_models
    return config


_load_runtime_env()


def strip_think(text: str) -> str:
    """Remove Qwen-style reasoning tags from model output."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S | re.I)
    return text.replace("<think>", "").replace("</think>", "").strip()


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort JSON object extraction without accepting non-JSON payloads."""
    text = strip_think(text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


class Qwen3LocalClient:
    """OpenAI-compatible enterprise intent/rewrite LLM client.

    The client never silently hides failures: callers receive fallback_used and
    fallback_reason so the interaction response can expose degraded mode.
    """

    def __init__(self) -> None:
        self.provider = os.environ.get("LLM_PROVIDER", "openai_compatible").strip().lower()
        self.api_key = _first_env("LLM_API_KEY", "QWEN_API_KEY", "DASHSCOPE_API_KEY", "OPENAI_API_KEY", default="local")
        has_dashscope_key = bool(_first_env("QWEN_API_KEY", "DASHSCOPE_API_KEY"))
        self.model_config = _load_model_config()
        default_base_url = (
            "https://dashscope.aliyuncs.com/compatible-mode/v1"
            if self.provider == "dashscope" or has_dashscope_key
            else "http://localhost:8000/v1"
        )
        self.base_url = os.environ.get("LLM_BASE_URL", default_base_url).rstrip("/")
        default_model = (
            self.model_config.get("light_reply", ["qwen3.6-flash"])[0]
            if "dashscope.aliyuncs.com" in self.base_url
            else "Qwen/Qwen3-32B"
        )
        self.model = os.environ.get("LLM_MODEL", os.environ.get("QWEN_MODEL", default_model))
        default_fallback = (
            self.model_config.get("light_reply", [self.model, self.model])[-1]
            if "dashscope.aliyuncs.com" in self.base_url
            else self.model
        )
        self.fallback_model = os.environ.get("LLM_FALLBACK_MODEL", default_fallback)
        self.free_only = os.environ.get("LLM_FREE_ONLY", os.environ.get("QWEN_FREE_ONLY", "true")).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.allow_paid_models = os.environ.get("LLM_ALLOW_PAID_MODELS", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.temperature_extract = _env_float("LLM_TEMPERATURE_EXTRACT", 0.1)
        self.temperature_reply = _env_float("LLM_TEMPERATURE_REPLY", 0.5)
        self.max_tokens_extract = _env_int("LLM_MAX_TOKENS_EXTRACT", 800)
        self.max_tokens_reply = _env_int("LLM_MAX_TOKENS_REPLY", 1000)
        self.timeout_seconds = _env_int("LLM_TIMEOUT_SECONDS", 8)
        self.enable_structured_output = os.environ.get("LLM_ENABLE_STRUCTURED_OUTPUT", "true").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.enable_rewrite = os.environ.get("LLM_ENABLE_REWRITE", "true").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def config_snapshot(self) -> Dict[str, Any]:
        """Return non-secret runtime configuration for audit/status APIs."""
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "fallback_model": self.fallback_model,
            "temperature_extract": self.temperature_extract,
            "temperature_reply": self.temperature_reply,
            "timeout_seconds": self.timeout_seconds,
            "structured_output_enabled": self.enable_structured_output,
            "rewrite_enabled": self.enable_rewrite,
            "free_only": self.free_only,
            "allow_paid_models": self.allow_paid_models,
            "model_config": self.model_config,
            "api_key_configured": bool(self.api_key and self.api_key != "local"),
            "recommended_enterprise_model": "task-routed free-quota Qwen models on DashScope, with per-task fallback",
            "recommended_single_node_model": "Qwen/Qwen3-32B",
            "openai_compatible_examples": [
                "DashScope: LLM_PROVIDER=dashscope LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1",
                "vLLM: LLM_BASE_URL=http://localhost:8000/v1",
                "Ollama: LLM_BASE_URL=http://localhost:11434/v1 LLM_MODEL=qwen3:32b",
            ],
        }

    def models_for_task(self, task_type: str | None = None) -> list[str]:
        task = (task_type or "light_reply").strip().lower()
        aliases = {
            "intent": "intent_routing",
            "routing": "intent_routing",
            "slot": "slot_extraction",
            "extract": "slot_extraction",
            "rewrite": "business_explanation",
            "reply": "light_reply",
            "report": "report_generation",
            "script": "customer_script",
            "explanation": "business_explanation",
        }
        task = aliases.get(task, task)
        configured = list(self.model_config.get(task) or self.model_config.get("light_reply") or [])
        explicit = [self.model, self.fallback_model]
        if not self.free_only and self.model_config.get("complex_fallback"):
            configured += self.model_config["complex_fallback"]
        models = _unique_models(configured or explicit)
        if self.free_only and not self.allow_paid_models:
            models = [model for model in models if model not in NON_FREE_MODEL_BLOCKLIST]
        if not models:
            models = list(self.model_config.get("light_reply") or ["qwen3.6-flash"])
        return _unique_models(models)

    def _infer_task_from_payload(self, payload: Dict[str, Any]) -> str:
        text = " ".join(
            str(payload.get(key, ""))
            for key in ("task_type", "task", "intent", "module", "purpose", "mode")
            if payload.get(key) is not None
        ).lower()
        if "intent" in text or "route" in text:
            return "intent_routing"
        if "slot" in text or "extract" in text or "vehicle" in text:
            return "slot_extraction"
        if "report" in text or "日报" in text:
            return "report_generation"
        if "script" in text or "话术" in text:
            return "customer_script"
        if "explain" in text or "解释" in text or "business" in text:
            return "business_explanation"
        return "slot_extraction"

    def health_check(self) -> Dict[str, Any]:
        """Ping the configured LLM endpoint with a tiny structured request."""
        started = time.time()
        if self.provider not in {"openai_compatible", "openai_compatible_local", "openai_compatible_remote", "dashscope"}:
            return {
                "ok": False,
                **self.config_snapshot(),
                "latency_ms": 0,
                "reason": f"unsupported provider: {self.provider}",
            }
        result = self.structured_extract(
            "你是健康检查接口。只输出 JSON：{\"ok\": true}",
            {"task": "health_check", "required_output": {"ok": True}},
        )
        parsed = extract_json_object(result.content) if result.ok else None
        return {
            "ok": bool(result.ok and isinstance(parsed, dict)),
            **self.config_snapshot(),
            "served_model": result.model,
            "latency_ms": result.latency_ms or int((time.time() - started) * 1000),
            "reason": "" if result.ok else result.fallback_reason,
            "raw_response_valid_json": isinstance(parsed, dict),
        }

    def _post_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        timeout_seconds: int | None = None,
    ) -> LLMResult:
        started = time.time()
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if self.enable_structured_output and temperature <= 0.11:
            payload["response_format"] = {"type": "json_object"}
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds or self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
            content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
            return LLMResult(
                ok=True,
                content=strip_think(content),
                model=model,
                latency_ms=int((time.time() - started) * 1000),
            )
        except Exception as exc:
            return LLMResult(
                ok=False,
                model=model,
                fallback_used=True,
                fallback_reason=f"{type(exc).__name__}: {exc}",
                latency_ms=int((time.time() - started) * 1000),
            )

    @staticmethod
    def _model_cooldown(model: str) -> tuple[bool, str]:
        now = time.time()
        with _MODEL_CIRCUIT_LOCK:
            until = float(_MODEL_FAILURE_UNTIL.get(model) or 0)
            if until <= now:
                _MODEL_FAILURE_UNTIL.pop(model, None)
                _MODEL_FAILURE_REASON.pop(model, None)
                return False, ""
            return True, _MODEL_FAILURE_REASON.get(model, "recent_model_failure")

    @staticmethod
    def _record_model_result(model: str, result: LLMResult) -> None:
        with _MODEL_CIRCUIT_LOCK:
            if result.ok:
                _MODEL_FAILURE_UNTIL.pop(model, None)
                _MODEL_FAILURE_REASON.pop(model, None)
                return
            reason = str(result.fallback_reason or "model_failure")
            lowered = reason.lower()
            if any(token in lowered for token in ("429", "quota", "insufficient", "rate limit")):
                cooldown = 15 * 60
            elif any(token in lowered for token in ("401", "403", "404", "invalid model", "model not")):
                cooldown = 10 * 60
            elif any(token in lowered for token in ("timeout", "timed out", "connection refused", "urlerror")):
                cooldown = 60
            else:
                cooldown = 2 * 60
            _MODEL_FAILURE_UNTIL[model] = time.time() + cooldown
            _MODEL_FAILURE_REASON[model] = reason[:240]

    def _post_chat_with_fallback(
        self,
        *,
        task_type: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> LLMResult:
        failures: list[str] = []
        last_result: LLMResult | None = None
        fast_task = task_type in {"intent_routing", "light_reply", "slot_extraction"}
        default_fast_timeout = 6 if task_type == "slot_extraction" else 4
        per_model_timeout = min(self.timeout_seconds, _env_int("LLM_FAST_TASK_TIMEOUT_SECONDS", default_fast_timeout)) if fast_task else self.timeout_seconds
        max_attempts = _env_int("LLM_MAX_MODEL_ATTEMPTS", 2 if fast_task else 4)
        for index, model in enumerate(self.models_for_task(task_type)[:max_attempts]):
            cooling_down, cooldown_reason = self._model_cooldown(model)
            if cooling_down:
                failures.append(f"{model}: circuit_open({cooldown_reason})")
                continue
            result = self._post_chat(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_seconds=per_model_timeout,
            )
            self._record_model_result(model, result)
            result.fallback_used = index > 0
            if result.ok:
                if failures:
                    result.fallback_reason = "; ".join(failures)
                return result
            failures.append(f"{model}: {result.fallback_reason}")
            last_result = result
        if last_result is None:
            return LLMResult(ok=False, model="", fallback_used=True, fallback_reason="no models configured")
        last_result.fallback_used = True
        last_result.fallback_reason = "; ".join(failures)
        return last_result

    def structured_extract(self, system_prompt: str, user_payload: Dict[str, Any]) -> LLMResult:
        if self.provider not in {"openai_compatible", "openai_compatible_local", "openai_compatible_remote", "dashscope"}:
            return LLMResult(
                ok=False,
                model=self.model,
                fallback_used=True,
                fallback_reason=f"unsupported provider: {self.provider}",
            )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ]
        return self._post_chat_with_fallback(
            task_type=self._infer_task_from_payload(user_payload),
            messages=messages,
            temperature=self.temperature_extract,
            max_tokens=self.max_tokens_extract,
        )

    def structured_extract_until(
        self,
        system_prompt: str,
        user_payload: Dict[str, Any],
        accept_json: Callable[[Dict[str, Any]], bool],
    ) -> LLMResult:
        if self.provider not in {"openai_compatible", "openai_compatible_local", "openai_compatible_remote", "dashscope"}:
            return LLMResult(
                ok=False,
                model=self.model,
                fallback_used=True,
                fallback_reason=f"unsupported provider: {self.provider}",
            )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ]
        task_type = self._infer_task_from_payload(user_payload)
        failures: list[str] = []
        last_result: LLMResult | None = None
        fast_task = task_type in {"intent_routing", "light_reply", "slot_extraction"}
        default_fast_timeout = 6 if task_type == "slot_extraction" else 4
        per_model_timeout = min(self.timeout_seconds, _env_int("LLM_FAST_TASK_TIMEOUT_SECONDS", default_fast_timeout)) if fast_task else self.timeout_seconds
        max_attempts = _env_int("LLM_MAX_MODEL_ATTEMPTS", 2 if fast_task else 4)
        for index, model in enumerate(self.models_for_task(task_type)[:max_attempts]):
            cooling_down, cooldown_reason = self._model_cooldown(model)
            if cooling_down:
                failures.append(f"{model}: circuit_open({cooldown_reason})")
                continue
            result = self._post_chat(
                model=model,
                messages=messages,
                temperature=self.temperature_extract,
                max_tokens=self.max_tokens_extract,
                timeout_seconds=per_model_timeout,
            )
            self._record_model_result(model, result)
            result.fallback_used = index > 0
            if not result.ok:
                failures.append(f"{model}: {result.fallback_reason}")
                last_result = result
                continue
            parsed = extract_json_object(result.content)
            if isinstance(parsed, dict) and accept_json(parsed):
                if failures:
                    result.fallback_reason = "; ".join(failures)
                return result
            reason = "non_json" if parsed is None else "validator_rejected"
            failures.append(f"{model}: {reason}")
            last_result = result
        if last_result is None:
            return LLMResult(ok=False, model="", fallback_used=True, fallback_reason="no models configured")
        last_result.fallback_used = True
        last_result.fallback_reason = "; ".join(failures)
        return last_result

    def rewrite_reply(
        self,
        system_prompt: str,
        facts: Dict[str, Any],
        *,
        task_type: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResult:
        if not self.enable_rewrite:
            return LLMResult(
                ok=False,
                model=self.model,
                fallback_used=True,
                fallback_reason="LLM_ENABLE_REWRITE=false",
            )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
        ]
        return self._post_chat_with_fallback(
            task_type=task_type or self._infer_task_from_payload(facts).replace("slot_extraction", "business_explanation"),
            messages=messages,
            temperature=self.temperature_reply if temperature is None else float(temperature),
            max_tokens=self.max_tokens_reply if max_tokens is None else int(max_tokens),
        )


def load_prompt(relative_path: str) -> str:
    path = ROOT / relative_path
    return path.read_text(encoding="utf-8")
