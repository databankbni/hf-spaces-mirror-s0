import json
import logging
from typing import Optional

from google import genai
from google.genai import types

from core.config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)


class GeminiClient:
    def __init__(self):
        self.api_key = GEMINI_API_KEY
        self.model = GEMINI_MODEL
        self._client: Optional[genai.Client] = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            if not self.api_key:
                raise RuntimeError(
                    "GEMINI_API_KEY not set. Create a .env file with your key."
                )
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, temperature: float = 0.5, max_tokens: int = 2048) -> str:
        resp = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
        return resp.text or ""

    def generate_json(self, prompt: str, temperature: float = 0.3) -> dict:
        raw = self.generate(prompt, temperature=temperature)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
        if cleaned.endswith("```"):
            cleaned = cleaned.removesuffix("```").strip()
        return json.loads(cleaned)

    def generate_with_images(
        self, prompt: str, image_bytes_list: list[bytes], temperature: float = 0.3
    ) -> str:
        contents = [prompt]
        for img_bytes in image_bytes_list:
            contents.append(
                types.Part.from_bytes(
                    data=img_bytes,
                    mime_type="image/png",
                )
            )
        resp = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(temperature=temperature),
        )
        return resp.text or ""


gemini = GeminiClient()
