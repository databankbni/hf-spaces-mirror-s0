# utils.py
#
# Security: HF_TOKEN is read exclusively from the environment.
# It is never accepted as a function argument, never logged, never returned.

import os
import json
import re
import logging
from huggingface_hub import InferenceClient
from dotenv import load_dotenv

load_dotenv()

_IM_END = "<|" + "im_end" + "|>"

INFERENCE_ATTEMPTS = [
    # Tier 0 — free hf-inference serverless (no partner credits)
    {"provider": "hf-inference", "model": "katanemo/Arch-Router-1.5B",        "method": "chat"},
    {"provider": "hf-inference", "model": "HuggingFaceBio/Carbon-3B",         "method": "text_generation"},
    {"provider": "hf-inference", "model": "katanemo/Arch-Router-1.5B",        "method": "text_generation"},
    # Tier 1 — low-cost explicit providers
    {"provider": "nscale",        "model": "Qwen/Qwen2.5-Coder-3B-Instruct",  "method": "chat"},
    {"provider": "nscale",        "model": "Qwen/Qwen2.5-Coder-7B-Instruct",  "method": "chat"},
    {"provider": "featherless-ai","model": "Qwen/Qwen2.5-7B-Instruct",        "method": "chat"},
    {"provider": "featherless-ai","model": "Qwen/Qwen3-0.6B",                 "method": "chat"},
    # Tier 2 — auto-router fallback
    {"provider": None,            "model": "Qwen/Qwen2.5-Coder-7B-Instruct",  "method": "chat"},
    {"provider": None,            "model": "meta-llama/Llama-3.2-3B-Instruct","method": "chat"},
]

FREE_TIER_PROVIDERS = {"hf-inference"}
logger = logging.getLogger(__name__)


# ─── Token management ────────────────────────────────────────────────────────

def _load_token() -> str:
    token = os.getenv("HF_TOKEN", "").strip()
    if not token:
        raise RuntimeError("API configuration missing. Contact administrator.")
    return token


# ─── Chat template helpers ───────────────────────────────────────────────────

def _apply_chat_template(model_name: str, prompt: str) -> str:
    m = model_name.lower()
    if "codellama" in m or "code-llama" in m:
        return f"[INST] {prompt} [/INST]"
    if "llama" in m:
        return (
            "<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n\n"
            f"{prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
        )
    if "qwen" in m:
        return (
            f"<|im_start|>system\nYou are a helpful assistant.{_IM_END}\n"
            f"<|im_start|>user\n{prompt}{_IM_END}\n"
            "<|im_start|>assistant\n"
        )
    if "gemma" in m:
        return f"<start_of_turn>user\n{prompt}<end_of_turn>\n<start_of_turn>model\n"
    if "zephyr" in m or "mistral" in m:
        return f"<|system|></s><|user|>\n{prompt}</s><|assistant|>\n"
    return f"### Instruction:\n{prompt}\n\n### Response:\n"


# ─── Error classifiers ───────────────────────────────────────────────────────

def _is_auth_error(e: Exception) -> bool:
    if hasattr(e, "response") and getattr(e.response, "status_code", None) in (401, 403):
        return True
    msg = str(e).lower()
    return "unauthorized" in msg or "forbidden" in msg or re.search(r'\b40[13]\b', msg) is not None

def _is_credit_error(e: Exception) -> bool:
    if hasattr(e, "response") and getattr(e.response, "status_code", None) == 402:
        return True
    msg = str(e).lower()
    return "payment required" in msg or "credits" in msg or re.search(r'\b402\b', msg) is not None

def _is_unsupported_model_error(e: Exception) -> bool:
    if hasattr(e, "response") and getattr(e.response, "status_code", None) in (410, 404):
        return True
    msg = str(e).lower()
    return "not supported" in msg or "model not found" in msg or "deprecated" in msg or re.search(r'\b410\b|\b404\b', msg) is not None


# ─── Low-level inference calls ───────────────────────────────────────────────

def _chat_complete(client: InferenceClient, model: str, prompt: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1800,
    )
    if response and response.choices and response.choices[0].message.content:
        return response.choices[0].message.content
    raise RuntimeError("Empty chat completion response.")


def _text_generate(client: InferenceClient, model: str, prompt: str) -> str:
    formatted = _apply_chat_template(model, prompt)
    result = client.text_generation(
        formatted,
        model=model,
        max_new_tokens=1800,
        return_full_text=False,
        stop_sequences=["<|eot_id|>", _IM_END, "<end_of_turn>", "</s>"],
    )
    if result and result.strip():
        return result.strip()
    raise RuntimeError("Empty text_generation response.")


def _make_client(token: str, provider: str | None) -> InferenceClient:
    if provider:
        return InferenceClient(provider=provider, api_key=token)
    return InferenceClient(api_key=token)


def _attempt_label(attempt: dict) -> str:
    return f"{attempt['provider'] or 'auto-router'}/{attempt['model']} ({attempt['method']})"


# ─── Core inference runner ───────────────────────────────────────────────────

def _run_inference(prompt: str) -> str:
    """
    Internal inference runner. Token is resolved here — never exposed to callers.
    Tries all configured models in tier order, skipping credit-billed ones after 402.
    """
    token = _load_token()
    last_exception = None
    credits_depleted = False
    clients: dict[str | None, InferenceClient] = {}

    for attempt in INFERENCE_ATTEMPTS:
        provider = attempt["provider"]
        model    = attempt["model"]
        method   = attempt["method"]
        label    = _attempt_label(attempt)

        if credits_depleted and provider not in FREE_TIER_PROVIDERS:
            logger.debug("[SKIP] %s — credits depleted.", label)
            continue

        try:
            if provider not in clients:
                clients[provider] = _make_client(token, provider)
            client = clients[provider]

            logger.debug("[TRY] %s", label)
            result = _chat_complete(client, model, prompt) if method == "chat" else _text_generate(client, model, prompt)
            logger.debug("[OK] %s", label)
            return result

        except Exception as e:
            msg = str(e)
            logger.debug("[FAIL] %s: %s", label, msg[:160])

            if _is_auth_error(e):
                raise RuntimeError("API configuration missing. Contact administrator.") from e
            if _is_credit_error(e):
                credits_depleted = True
                last_exception = e
                continue
            last_exception = e
            if _is_unsupported_model_error(e):
                continue

    final = str(last_exception) if last_exception else "Unknown error"
    if credits_depleted:
        raise RuntimeError(
            "Hugging Face Inference Provider credits are exhausted (HTTP 402).\n\n"
            "Options:\n"
            "1. Wait for monthly credits to reset: https://huggingface.co/settings/billing\n"
            "2. Purchase pre-paid inference credits\n"
            "3. Retry later — free serverless capacity can be temporarily busy\n\n"
            f"Last error: {final}"
        )
    raise RuntimeError(f"All inference attempts failed.\nLast error: {final}")


# ─── Public API (feature-level functions) ────────────────────────────────────

def generate_explanation(prompt: str) -> str:
    """Generate code explanation. Token is backend-only."""
    return _run_inference(prompt)


def generate_translation(prompt: str) -> str:
    """Generate code translation. Token is backend-only."""
    return _run_inference(prompt)


def generate_complexity_analysis(prompt: str) -> str:
    """Generate structured complexity analysis. Token is backend-only."""
    return _run_inference(prompt)

# Flow feature has been removed from the platform
