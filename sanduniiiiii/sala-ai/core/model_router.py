"""
Sala AI - Model Fallback Router
Groq (primary) -> Gemini (quota-tracked) -> OpenRouter (free models, extra capacity)
"""

import os
from groq import Groq
import google.generativeai as genai
import requests

from core.quota_tracker import record_usage, get_quota_summary

# ---------- Config ----------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_DAILY_TOKEN_LIMIT = int(os.getenv("GEMINI_DAILY_TOKEN_LIMIT", "900000"))
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

SAFE_THRESHOLD = 0.9  # switch away from a provider at 90% of its daily quota

# OpenRouter free models to try, in order
OPENROUTER_FREE_MODELS = [
    "openrouter/free",
    "meta-llama/llama-3.3-70b:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
]

groq_client = Groq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.5-flash")


def _quota_available(provider: str) -> bool:
    """Check if a provider is still under its safe usage threshold for today."""
    summary = get_quota_summary()
    info = summary["providers"].get(provider)
    if not info:
        return True
    limit = info["tokens_limit"] or info["requests_limit"]
    used_pct = info["tokens_pct_used"] if info["tokens_limit"] else info["requests_pct_used"]
    if limit is None or used_pct is None:
        return True  # no known limit -> assume available
    return used_pct < SAFE_THRESHOLD * 100


# ---------- Tier 1: Groq ----------
def _try_groq(prompt, system_prompt):
    if not _quota_available("groq"):
        print("[Groq] Daily quota threshold reached, skipping")
        return None
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        tokens_used = 0
        if getattr(response, "usage", None):
            tokens_used = getattr(response.usage, "total_tokens", 0) or 0
        record_usage("groq", requests=1, tokens=tokens_used)
        return response.choices[0].message.content
    except Exception as e:
        print(f"[Groq failed] {e}")
        return None


# ---------- Tier 2: Gemini ----------
def _try_gemini(prompt, system_prompt):
    if not _quota_available("gemini"):
        print("[Gemini] Daily quota threshold reached, skipping")
        return None
    try:
        full_prompt = f"{system_prompt}\n\nUser: {prompt}"
        response = gemini_model.generate_content(full_prompt)
        token_count = response.usage_metadata.total_token_count
        record_usage("gemini", requests=1, tokens=token_count)
        return response.text
    except Exception as e:
        print(f"[Gemini failed] {e}")
        return None


# ---------- Tier 3: OpenRouter (free models) ----------
def _try_openrouter(prompt, system_prompt):
    if not _quota_available("openrouter"):
        print("[OpenRouter] Daily quota threshold reached, skipping")
        return None
    for model in OPENROUTER_FREE_MODELS:
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            tokens_used = 0
            if data.get("usage"):
                tokens_used = data["usage"].get("total_tokens", 0) or 0
            record_usage("openrouter", requests=1, tokens=tokens_used)
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[OpenRouter model {model} failed] {e}")
            continue  # try next free model
    return None


# ---------- Public entrypoint ----------
def get_ai_response(prompt: str, system_prompt: str) -> str:
    """
    Routes through Groq -> Gemini -> OpenRouter in order.
    Returns the first successful response.
    """
    result = _try_groq(prompt, system_prompt)
    if result:
        return result

    result = _try_gemini(prompt, system_prompt)
    if result:
        return result

    result = _try_openrouter(prompt, system_prompt)
    if result:
        return result

    return "සමාවෙන්න, දැනට සේවාව ලබා දිය නොහැක. පසුව උත්සාහ කරන්න."