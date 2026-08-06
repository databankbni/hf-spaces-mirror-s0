#!/usr/bin/env python3
"""
Gateway client — route LLM calls through LBJLincoln26/llm-gateway.

Single entry point `gateway_call()` for every Nomos42 LLM consumer
(trading floors, councils, CLIs). Handles:
  - Gradio 5.x two-step /call/{fn}  + /call/{fn}/{event_id} SSE polling
  - Model-key mapping (TF-style "openrouter:nemotron-120b" → gateway registry)
  - Graceful fallback to direct provider cfg on 5xx / timeout / empty

This file is vendored into each HF Space (TF NBA, TF Political) so it travels
with the Space source; HF Spaces cannot import from the monorepo at runtime.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Callable, Dict, List, Optional

import requests

GATEWAY_URL = os.environ.get("GATEWAY_URL", "").rstrip("/")

# Aliases: callers may use short provider keys that differ slightly from the
# gateway registry. Keep in sync with hf-llm-gateway/app.py MODELS dict.
_MODEL_ALIASES: Dict[str, str] = {
    "openrouter:nemotron-120b": "openrouter:nemotron-120b:free",
    "openrouter:glm-4.5-air":   "openrouter:glm-4.5-air:free",
    "openrouter:gpt-oss-20b":   "openrouter:gpt-oss-20b:free",
    "openrouter:gemma-4-26b":   "openrouter:gemma-4-26b:free",
    "openrouter:minimax-m2.5":  "openrouter:minimax-m2.5:free",
    "openrouter:qwen3-80b":     "openrouter:qwen3-80b:free",
    "openrouter:llama-3.3-70b": "openrouter:llama-3.3-70b:free",
}


def _resolve(model_key: str) -> str:
    return _MODEL_ALIASES.get(model_key, model_key)


def _messages_to_prompts(messages: List[Dict[str, str]]) -> tuple[str, str]:
    """Split OpenAI-style messages into (system, user) for gateway's Gradio fn."""
    sys_parts, usr_parts = [], []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            sys_parts.append(content)
        else:
            usr_parts.append(content)
    return "\n\n".join(sys_parts), "\n\n".join(usr_parts)


def _gateway_post(model_key: str, system: str, user: str, max_tokens: int,
                  timeout: float) -> Optional[Dict[str, Any]]:
    """Fast FastAPI call via /api/chat (2026-04-18: was /gradio_api 45-60s stream, now ~2s JSON)."""
    resolved = _resolve(model_key)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    if user:
        messages.append({"role": "user", "content": user})
    resp = requests.post(
        f"{GATEWAY_URL}/api/chat",
        json={"model": resolved, "messages": messages, "max_tokens": int(max_tokens)},
        timeout=timeout,
    )
    if resp.status_code >= 500 or resp.status_code in (502, 503, 504):
        return None
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("content"):
        return payload
    return None


def gateway_call(model_key: str, messages: List[Dict[str, str]],
                 temperature: float = 0.7, max_tokens: int = 4096,
                 fallback_direct: bool = True,
                 direct_fn: Optional[Callable[[str, str], Optional[str]]] = None,
                 timeout: float = 60.0) -> Dict[str, Any]:
    """
    Call an LLM through the Nomos42 gateway, with optional direct fallback.

    model_key: e.g. "cerebras:qwen-3-235b", "google:gemini-3-flash"
    messages:  OpenAI-style [{"role": "system"|"user", "content": "..."}]
    direct_fn: callable(system_prompt, user_prompt) -> text, used as fallback
               when gateway 5xx/timeouts AND fallback_direct=True.

    Returns: {"text": str|None, "routed_via": "gateway"|"direct"|"failed",
              "model_used": str, "latency_ms": int, "error": str|None}
    """
    system, user = _messages_to_prompts(messages)
    t0 = time.time()

    if GATEWAY_URL:
        try:
            result = _gateway_post(model_key, system, user, max_tokens, timeout)
            if result and result.get("content"):
                return {
                    "text": result["content"],
                    "routed_via": "gateway",
                    "model_used": result.get("model_used") or model_key,
                    "latency_ms": int((time.time() - t0) * 1000),
                    "error": None,
                }
            gw_err = ((result or {}).get("errors") or (result or {}).get("error") or "empty response") if isinstance(result, dict) else "empty response"
        except Exception as e:
            gw_err = f"{type(e).__name__}: {str(e)[:120]}"
    else:
        gw_err = "GATEWAY_URL not set"

    if fallback_direct and direct_fn is not None:
        try:
            text = direct_fn(system, user)
            if text:
                return {
                    "text": text,
                    "routed_via": "direct",
                    "model_used": model_key,
                    "latency_ms": int((time.time() - t0) * 1000),
                    "error": f"gateway fallback: {gw_err}",
                }
        except Exception as e:
            gw_err = f"{gw_err}; direct: {type(e).__name__}: {str(e)[:80]}"

    return {
        "text": None,
        "routed_via": "failed",
        "model_used": model_key,
        "latency_ms": int((time.time() - t0) * 1000),
        "error": gw_err,
    }
