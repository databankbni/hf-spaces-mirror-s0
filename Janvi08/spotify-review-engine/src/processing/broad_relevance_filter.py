"""Broad relevance classifier — semantic re-evaluation of irrelevant-tagged records."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from groq import Groq

logger = logging.getLogger(__name__)


class BroadRelevanceFilter:
    """Re-classify records using a broader music-discovery relevance definition."""

    def __init__(self) -> None:
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is missing from environment variables.")

        self.client = Groq(api_key=self.api_key)
        self.model = "llama-3.3-70b-versatile"
        self.batch_size = 15
        self.batch_delay = 4.0

    def _mark_quota_exhausted(self, records: list[dict[str, Any]]) -> None:
        for record in records:
            record["relevant_broad"] = None
            record["relevant_broad_status"] = "quota_exhausted"

    def process_batch(self, records: list[dict[str, Any]]) -> bool:
        """Classify a batch in place. Returns True if quota was exhausted (caller should stop)."""
        if not records:
            return False

        record_map = {str(index): record for index, record in enumerate(records)}

        prompt = (
            "You are a semantic data classifier for Spotify user feedback.\n"
            "I will provide a JSON object where keys are IDs and values are review/comment texts.\n\n"
            "For EACH text, decide if it describes ANY of the following themes — even implicitly, "
            "without requiring exact keywords like 'discover' or 'recommendation':\n"
            "1. Repetitive listening behavior (same songs/artists on repeat, loops, playlists that never change)\n"
            "2. Algorithm or recommendation complaints (bad suggestions, irrelevant playlists, "
            "Discover Weekly misses, shuffle issues tied to personalization)\n"
            "3. Passive music consumption habits (background listening, not engaging with new music)\n"
            "4. Only listening to familiar music / comfort-zone listening / no variety\n"
            "5. Explicit struggles with music discovery (can't find new music, stuck in a rut, "
            "want to branch out but can't)\n\n"
            "Mark relevant_broad=true if ANY of the above apply semantically.\n"
            "Mark relevant_broad=false ONLY if the text is clearly about unrelated topics "
            "(billing, ads, login bugs, crashes, audio quality, UI unrelated to listening habits, "
            "customer service, premium pricing) with NO connection to listening behavior or discovery.\n\n"
            "Return ONLY a valid JSON object mapping the exact same IDs to:\n"
            '{"relevant_broad": boolean}\n\n'
            "Do NOT include markdown formatting. Return raw JSON only.\n\n"
            "Input Texts:\n"
        )

        input_data = {
            record_id: (record.get("text") or "")[:1000]
            for record_id, record in record_map.items()
        }
        prompt += json.dumps(input_data, ensure_ascii=False)

        time.sleep(self.batch_delay)

        try:
            response = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            result_json = response.choices[0].message.content or "{}"

            if result_json.startswith("```json"):
                result_json = result_json[7:-3].strip()
            elif result_json.startswith("```"):
                result_json = result_json[3:-3].strip()

            classifications = json.loads(result_json)

            for record_id, record in record_map.items():
                classification = classifications.get(record_id, {})
                relevant_broad = classification.get("relevant_broad")
                if isinstance(relevant_broad, str):
                    relevant_broad = relevant_broad.strip().lower() in {"true", "1", "yes"}
                elif relevant_broad is not None:
                    relevant_broad = bool(relevant_broad)

                record["relevant_broad"] = relevant_broad
                record["relevant_broad_status"] = "classified"

        except Exception as exc:
            error_text = str(exc).lower()
            if "429" in str(exc) or "rate limit" in error_text or "quota" in error_text:
                logger.error("Groq API quota/rate limit hit: %s", exc)
                self._mark_quota_exhausted(records)
                return True

            logger.error("Groq API batch failed: %s", exc)
            raise

        return False
