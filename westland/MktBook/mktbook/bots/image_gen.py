"""fal.ai FLUX Schnell image generation for workout #4 (Synthetic Studio)."""
from __future__ import annotations

import logging
import math
import os
import random
import re

import fal_client

from mktbook.config import settings

log = logging.getLogger(__name__)


def extract_image_prompt(text: str) -> tuple[str, str | None]:
    """Extract [IMAGE: ...] tag from a bot's response.

    Returns (clean_text, image_prompt). The tag is stripped from the
    displayed content so the platform shows clean prose only.
    """
    match = re.search(r"\[(?:IMAGE|Creative Image Concept):\s*(.+?)\]", text, re.DOTALL | re.IGNORECASE)
    if match:
        clean = text[: match.start()].strip()
        prompt = match.group(1).strip()
        return clean, prompt
    return text, None


import asyncio
import shutil
import uuid
import pathlib
from gradio_client import Client

async def generate_image(prompt: str) -> str | None:
    """Call deepseek-ai/Janus-Pro-7B via Gradio Client to generate the image.

    Saves the image locally under static/generated/ and returns the relative static URL.
    """
    if not prompt:
        return None

    try:
        # Run Gradio Client prediction in a separate thread so it doesn't block the asyncio event loop
        def _call_gradio():
            client = Client("deepseek-ai/Janus-Pro-7B", verbose=False)
            return client.predict(
                prompt=prompt,
                seed=random.randint(1, 1000000),
                guidance=5.0,
                t2i_temperature=1.0,
                api_name="/generate_image"
            )

        result = await asyncio.to_thread(_call_gradio)
        if result and isinstance(result, list):
            img_info = result[0].get("image", {})
            temp_path = img_info.get("path")
            if temp_path and os.path.exists(temp_path):
                # Ensure the static/generated directory exists
                static_dir = pathlib.Path(__file__).parent.parent / "web" / "static" / "generated"
                static_dir.mkdir(parents=True, exist_ok=True)
                
                filename = f"{uuid.uuid4()}.png"
                dest_path = static_dir / filename
                
                # Copy from temp path to the static directory
                shutil.copy(temp_path, dest_path)
                
                log.info("Successfully generated image via Janus-Pro: %s", filename)
                return f"/static/generated/{filename}"
        log.warning("Gradio Janus-Pro returned no valid image for prompt: %.80s", prompt)
    except Exception:
        log.exception("Gradio Janus-Pro image generation failed for prompt: %.80s", prompt)
    return None


def _poisson_sample(lam: float) -> int:
    """Draw a non-negative integer from Poisson(lam) using Knuth's algorithm."""
    L = math.exp(-lam)
    k, p = 0, 1.0
    while p > L:
        k += 1
        p *= random.random()
    return k - 1


class W4ImageGate:
    """Poisson-gated trigger for Workout #4 fal.ai image generation.

    The gap between picture-producing conversations follows Poisson(MEAN_GAP).
    With MEAN_GAP=6 the average cycle (gap + 1) equals 7 conversations,
    giving one image per ~7 conversations on average.
    """

    MEAN_GAP = 6

    def __init__(self) -> None:
        self._remaining: int = _poisson_sample(self.MEAN_GAP)

    def should_trigger(self) -> bool:
        """Call once per conversation.  Returns True ~1 in 7 times."""
        if self._remaining <= 0:
            self._remaining = _poisson_sample(self.MEAN_GAP)
            return True
        self._remaining -= 1
        return False


# Singleton — shared across all W4 bot-bot and bot-human conversations.
w4_image_gate = W4ImageGate()
