# crop_normalizer.py
# ─────────────────────────────────────────────────────────────────────────────
# Single responsibility: match any user crop input to a canonical key.
#
# To change the AI fallback model → change MODEL constant below, nothing else.
# To change matching logic → edit normalize_crop_name() only.
# ─────────────────────────────────────────────────────────────────────────────

import os
from groq import Groq
from dotenv import load_dotenv

from crop_aliases import CROP_ALIASES
from language_utils import detect_language, get_display_name

load_dotenv()

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ── Change model here and nowhere else ────────────────────────────────────────
MODEL = "llama-3.3-70b-versatile"

MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _chat(messages):
    for model in MODELS:
        try:
            response = groq_client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=20,
                temperature=0,
            )
            return response
        except Exception as e:
            if "rate_limit" in str(e).lower() or "429" in str(e):
                print(f"[CROP AI] {model} rate limited, trying next...")
                continue
            raise
    raise Exception("All models exhausted")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def normalize_crop_name(raw_name: str, crop_requirements: dict):
    """
    Matches any user input to a canonical crop key.
    Returns (matched_key, display_name) or (None, None) if no match.

    Step 1 — direct key match       (instant, free)
    Step 2 — alias dict lookup      (instant, free, covers 95%+ of inputs)
    Step 3 — Groq AI fallback       (only fires when steps 1 and 2 fail)
    """
    cleaned = raw_name.strip().lower()
    lang    = detect_language(cleaned)

    # ── Step 1: direct key match ───────────────────────────────────────────
    if cleaned in crop_requirements:
        display = get_display_name(cleaned, lang)
        return cleaned, display

    # ── Step 2: alias dict ─────────────────────────────────────────────────
    if cleaned in CROP_ALIASES:
        matched_key = CROP_ALIASES[cleaned]
        display     = get_display_name(matched_key, lang)
        return matched_key, display

    # ── Step 3: AI fallback ────────────────────────────────────────────────
    crop_list_str = ', '.join(crop_requirements.keys())

    try:
        response = _chat(messages=[
            {
                "role": "system",
                "content": (
                    "You are a crop name matcher for Filipino farmers in Mindanao and Visayas.\n"
                    "Reply in EXACTLY this format with no other text: key|lang\n\n"
                    "- key: exact key from the crop list, nothing else\n"
                    "- lang: one of: bisaya, tagalog, english\n"
                    "- No match: none|none\n\n"
                    "No explanation. No punctuation. Only key|lang."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Farmer typed: '{raw_name}'\n\n"
                    f"Crop list: {crop_list_str}\n\n"
                    f"Phonetic rules:\n"
                    f"1. Bisaya: a/e/i and o/u freely interchange; k/g, p/b, t/d swap\n"
                    f"2. Doubled or missing letters are common: taloong = talong\n"
                    f"3. Spaces mid-word: 'luy a' = 'luya'\n"
                    f"4. Say it aloud — if it sounds like a crop, match it\n"
                    f"5. English phonetic misspellings are valid: 'muringa' = moringa\n\n"
                    f"Reply only: key|lang"
                )
            }
        ])

        raw_result = response.choices[0].message.content.strip()
        print(f"[CROP AI] input='{raw_name}' → raw='{raw_result}'")

        cleaned_result = (
            raw_result.lower().strip()
            .strip('"').strip("'").strip('`').strip('.')
        )

        if '|' not in cleaned_result:
            return None, None

        parts = cleaned_result.split('|')
        if len(parts) >= 2:
            matched_key = parts[0].strip().strip('"').strip("'")
            ai_lang     = parts[1].strip()

            print(f"[CROP AI] key='{matched_key}' lang='{ai_lang}'")

            if matched_key in crop_requirements:
                display = get_display_name(matched_key, ai_lang)
                return matched_key, display.capitalize()

            elif matched_key in CROP_ALIASES:
                matched_key = CROP_ALIASES[matched_key]
                if matched_key in crop_requirements:
                    display = get_display_name(matched_key, ai_lang)
                    return matched_key, display.capitalize()

    except Exception as e:
        print(f"[CROP AI] Exception: {e}")

    return None, None