from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PRIMARY_MODEL = "qwen-turbo"
FALLBACK_MODEL_1 = "qwen3.5-plus"
FALLBACK_MODEL_2 = "RULE_FALLBACK"
SEMANTIC_LAYER_VERSION = "v193"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "y"}


def stable_json_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class QwenConfig:
    api_key: str
    model: str
    enable_web_search: bool
    search_strategy: str
    cache_dir: Path
    base_url: str
    max_cost_per_run: float | None
    max_live_calls: int
    free_only: bool
    timeout_seconds: float
    max_tokens: int

    @classmethod
    def from_env(cls) -> "QwenConfig":
        root = _project_root()
        cache_dir = Path(os.environ.get("QWEN_CACHE_DIR") or root / "data/v193/qwen_cache")
        max_cost = os.environ.get("QWEN_MAX_COST_PER_RUN")
        return cls(
            api_key=(os.environ.get("QWEN_API_KEY") or os.environ.get("DASHSCOPE_API_KEY") or "").strip(),
            model=os.environ.get("QWEN_MODEL", PRIMARY_MODEL).strip() or PRIMARY_MODEL,
            enable_web_search=_truthy(os.environ.get("QWEN_ENABLE_WEB_SEARCH", "false")),
            search_strategy=os.environ.get("QWEN_SEARCH_STRATEGY", "agent_max").strip() or "agent_max",
            cache_dir=cache_dir,
            base_url=os.environ.get(
                "QWEN_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            ).strip(),
            max_cost_per_run=float(max_cost) if max_cost else None,
            max_live_calls=int(os.environ.get("QWEN_MAX_LIVE_CALLS", "12")),
            free_only=_truthy(os.environ.get("QWEN_FREE_ONLY", "true")),
            timeout_seconds=float(os.environ.get("QWEN_TIMEOUT_SECONDS", "15")),
            max_tokens=int(os.environ.get("QWEN_MAX_TOKENS", "512")),
        )


class QwenJsonValidationError(ValueError):
    pass


def validate_schema(data: dict[str, Any], required: dict[str, type | tuple[type, ...]]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise QwenJsonValidationError("Qwen result is not a JSON object")
    for key, expected_type in required.items():
        if key not in data:
            raise QwenJsonValidationError(f"missing key: {key}")
        if expected_type is not object and data[key] is not None and not isinstance(data[key], expected_type):
            raise QwenJsonValidationError(f"invalid type for {key}: {type(data[key]).__name__}")
    return data


class QwenSemanticClient:
    """Small, auditable Qwen wrapper.

    The client is intentionally optional. If `QWEN_API_KEY` is missing, callers
    receive deterministic RULE_FALLBACK metadata. Qwen outputs may enrich
    semantic evidence only; production price calculation remains structural.
    """

    def __init__(self, config: QwenConfig | None = None) -> None:
        self.config = config or QwenConfig.from_env()
        self.config.cache_dir.mkdir(parents=True, exist_ok=True)
        self._calls = 0
        self._cache_hits = 0

    @property
    def model_name(self) -> str:
        return self.config.model if self.config.api_key else FALLBACK_MODEL_2

    @property
    def cache_hit_rate(self) -> float:
        total = self._calls + self._cache_hits
        return round(self._cache_hits / total, 6) if total else 0.0

    def _cache_path(self, kind: str, payload: dict[str, Any]) -> Path:
        key_fingerprint = (
            hashlib.sha256(self.config.api_key.encode("utf-8")).hexdigest()[:12]
            if self.config.api_key
            else "no_key"
        )
        key = stable_json_hash(
            {
                "kind": kind,
                "model": self.config.model,
                "api_key_present": bool(self.config.api_key),
                "api_key_fingerprint": key_fingerprint,
                "enable_web_search": self.config.enable_web_search,
                "search_strategy": self.config.search_strategy,
                "client_request_version": "v193_no_response_format_max_tokens_v4",
                "payload": payload,
            }
        )
        return self.config.cache_dir / f"{kind}_{key}.json"

    def cached_json(self, kind: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        path = self._cache_path(kind, payload)
        if path.exists():
            self._cache_hits += 1
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def write_cache(self, kind: str, payload: dict[str, Any], data: dict[str, Any]) -> None:
        path = self._cache_path(kind, payload)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    def complete_json(
        self,
        *,
        kind: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        schema: dict[str, type | tuple[type, ...]],
        force_web_search: bool = False,
    ) -> dict[str, Any]:
        cached = self.cached_json(kind, user_payload)
        if cached is not None:
            return cached
        if not self.config.api_key:
            fallback = {
                "_qwen_status": "RULE_FALLBACK_NO_API_KEY",
                "_semantic_model": FALLBACK_MODEL_2,
                "_web_search_enabled": False,
                "_qwen_cache_hit": False,
            }
            self.write_cache(kind, user_payload, fallback)
            return fallback
        if self._calls >= self.config.max_live_calls:
            fallback = {
                "_qwen_status": "RULE_FALLBACK_LIVE_CALL_BUDGET_EXHAUSTED",
                "_semantic_model": FALLBACK_MODEL_2,
                "_web_search_enabled": False,
                "_qwen_cache_hit": False,
                "_free_only": self.config.free_only,
                "_max_live_calls": self.config.max_live_calls,
            }
            self.write_cache(kind, user_payload, fallback)
            return fallback
        self._calls += 1
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ]
        request_body: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": self.config.max_tokens,
        }
        if force_web_search or self.config.enable_web_search:
            # DashScope/OpenAI-compatible Model Studio deployments have changed
            # option names across releases. Keep both a generic extra_body shape
            # and explicit search metadata in cache/audits; unsupported fields
            # are harmlessly ignored by compatible endpoints.
            request_body["extra_body"] = {
                "enable_search": True,
                "search_options": {"search_strategy": self.config.search_strategy},
            }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        content = ""
        try:
            request = urllib.request.Request(
                self.config.base_url,
                data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = json.loads(response.read().decode("utf-8"))
            content = raw["choices"][0]["message"]["content"]
            data = json.loads(content)
            validate_schema(data, schema)
            data["_qwen_status"] = "OK"
            data["_semantic_model"] = self.config.model
            data["_web_search_enabled"] = bool(force_web_search or self.config.enable_web_search)
            data["_search_strategy"] = self.config.search_strategy
            data["_source_raw_response_id"] = raw.get("id", "")
            self.write_cache(kind, user_payload, data)
            return data
        except QwenJsonValidationError as error:
            fallback = {
                "_qwen_status": "QWEN_CALL_FAILED:QwenJsonValidationError",
                "_schema_error": str(error),
                "_raw_content_excerpt": content[:1000],
                "_semantic_model": FALLBACK_MODEL_2,
                "_web_search_enabled": False,
                "_qwen_cache_hit": False,
            }
            self.write_cache(kind, user_payload, fallback)
            return fallback
        except urllib.error.HTTPError as error:
            try:
                body = error.read().decode("utf-8", errors="replace")[:800]
            except Exception:
                body = ""
            fallback = {
                "_qwen_status": "QWEN_CALL_FAILED:HTTPError",
                "_http_status": error.code,
                "_http_reason": str(error.reason),
                "_http_body_excerpt": body,
                "_semantic_model": FALLBACK_MODEL_2,
                "_web_search_enabled": False,
                "_qwen_cache_hit": False,
            }
            self.write_cache(kind, user_payload, fallback)
            return fallback
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, OSError) as error:
            fallback = {
                "_qwen_status": f"QWEN_CALL_FAILED:{type(error).__name__}",
                "_error_excerpt": str(error)[:500],
                "_semantic_model": FALLBACK_MODEL_2,
                "_web_search_enabled": False,
                "_qwen_cache_hit": False,
            }
            self.write_cache(kind, user_payload, fallback)
            return fallback

    def web_search(self, query: str, *, ttl_seconds: int = 86_400) -> dict[str, Any]:
        payload = {"query": query, "search_strategy": self.config.search_strategy}
        path = self._cache_path("web_search", payload)
        if path.exists() and time.time() - path.stat().st_mtime <= ttl_seconds:
            self._cache_hits += 1
            return json.loads(path.read_text(encoding="utf-8"))
        prompt = (
            "You structure public used-car market search evidence. Return JSON with "
            "a list named results, each item having source_url,title,snippet,price,city,brand,series,model_year,trim."
        )
        result = self.complete_json(
            kind="web_search",
            system_prompt=prompt,
            user_payload=payload,
            schema={"results": list},
            force_web_search=True,
        )
        if "results" not in result:
            result["results"] = []
        result["crawl_time"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        result["model_name"] = self.model_name
        result["search_strategy"] = self.config.search_strategy
        self.write_cache("web_search", payload, result)
        return result
