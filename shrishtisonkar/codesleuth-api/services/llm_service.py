"""
LLM Service — wraps the OpenAI API (gpt-4o-mini by default).
Drop in a different model name in .env OPENAI_MODEL to switch models.
"""
import re
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from config import get_settings
from utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

MODE_SYSTEM_PROMPTS = {
    "intern": (
        "You are a friendly senior developer explaining code to a new intern. "
        "Use simple language, real-world analogies, and avoid heavy technical jargon. "
        "Explain WHY things work, not just WHAT they do. Keep it encouraging. "
        "IMPORTANT FORMATTING RULE: Do NOT use markdown bolding (no **stars**). "
        "Keep your response as natural, readable paragraphs rather than bulleted lists."
    ),
    "engineer": (
        "You are a senior software engineer performing a technical code review. "
        "Be precise, use correct terminology, reference design patterns where relevant, "
        "and discuss tradeoffs and performance implications. "
        "IMPORTANT FORMATTING RULE: Do NOT use markdown bolding (no **stars**). "
        "Use plain text paragraphs to explain your thoughts clearly."
    ),
    "architect": (
        "You are a principal software architect analyzing this codebase. "
        "Focus on system design, scalability, coupling, cohesion, SOLID principles, "
        "architectural patterns, and long-term maintainability. "
        "Identify systemic risks and strategic improvement opportunities. "
        "IMPORTANT FORMATTING RULE: Do NOT use markdown bolding (no **stars**). "
        "Use clear, readable text."
    ),
}


class LLMService:
    def __init__(self):
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        self.model = settings.openai_model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> tuple[str, int]:
        """
        Call OpenAI chat completion.
        Returns (response_text, tokens_used).
        """
        logger.debug(f"OpenAI chat | model={self.model} | messages={len(messages)}")
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content or ""
        
        # Strip <think>...</think> blocks, making the closing tag optional in case it gets cut off
        content = re.sub(r'<think>.*?(?:</think>|$)\s*', '', content, flags=re.DOTALL)
        
        tokens = response.usage.total_tokens if response.usage else 0
        return content.strip(), tokens

    async def chat_with_mode(
        self,
        user_prompt: str,
        mode: str = "engineer",
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> tuple[str, int]:
        """Build mode-specific system prompt and call chat."""
        system_prompt = MODE_SYSTEM_PROMPTS.get(mode, MODE_SYSTEM_PROMPTS["engineer"])
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return await self.chat(messages, temperature=temperature, max_tokens=max_tokens)

    async def summarize(self, text: str, max_sentences: int = 3) -> str:
        """Produce a brief summary of arbitrary text."""
        prompt = (
            f"Summarize the following text in {max_sentences} sentences or fewer. "
            f"Be concise and factual.\n\n{text}"
        )
        result, _ = await self.chat(
            [
                {"role": "system", "content": "You are a concise technical summarizer."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=256,
        )
        return result


_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service