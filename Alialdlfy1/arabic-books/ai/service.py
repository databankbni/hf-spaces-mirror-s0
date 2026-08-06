import logging
import hashlib
import json
import asyncio
import re
from datetime import datetime
from typing import Dict, Any, Optional
import google.generativeai as genai
from core.interfaces import IAIService, IBookRepository
from utils.credentials import credential_pool, CredentialType
from ai.prompt_manager import get_system_prompt, format_user_prompt
import config

logger = logging.getLogger("AI")

class GeminiAIService(IAIService):
    def __init__(self, repository: IBookRepository):
        self.repo = repository

    def _get_description_hash(self, title: str, author: str, description: Optional[str]) -> str:
        """Generates a SHA-256 hash of normalized book information for cache keying."""
        desc = description or ""
        raw_str = f"{title.strip().lower()}_{author.strip().lower()}_{desc.strip().lower()}"
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    async def process_book(self, title: str, author: str, description: Optional[str], intro_text: Optional[str] = None) -> Dict[str, Any]:
        """
        Processes book details using AI with a multi-provider failover chain.
        1. Checks Firestore cache.
        2. Tries Gemini API keys.
        3. Tries OpenRouter API keys.
        4. Tries Groq API keys.
        5. Falls back to Google Books / DDG web lookup.
        """
        # Calculate cache hash
        desc_hash = self._get_description_hash(title, author, description)
        
        # 1. Check AI Cache
        cached_result = await self.repo.get_ai_cache(desc_hash)
        if cached_result:
            if cached_result.get("prompt_version") == config.PROMPT_VERSION:
                logger.debug(f"AI Cache Hit for '{title}' by {author}.")
                return {
                    "summary": cached_result["summary"],
                    "category": cached_result["category"],
                    "hashtags": cached_result["hashtags"]
                }
            else:
                logger.debug(f"AI Cache found for '{title}', but prompt version mismatched. Recalculating...")

        # If AI features are disabled, use fallback immediately
        if not config.ENABLE_AI:
            logger.warning("AI features are disabled. Returning fallback book details.")
            return await self._generate_fallback(title, author)
            
        system_prompt = get_system_prompt(config.PROMPT_VERSION)
        user_prompt = format_user_prompt(title, author, description or "", intro_text or "")

        # --- FAILOVER CHAIN ---

        # 1. Gemini
        gemini_keys = credential_pool.credentials[CredentialType.GEMINI_API_KEY]
        logger.debug(f"Failover Chain: Trying Gemini keys (total={len(gemini_keys)})...")
        for key_cred in gemini_keys:
            if not key_cred.is_available():
                continue
            key_cred.mark_busy()
            try:
                logger.debug(f"Invoking Gemini with key: {key_cred.name}...")
                data = await self._call_gemini(key_cred.value, system_prompt, user_prompt)
                return await self._save_ai_success(key_cred, desc_hash, title, author, data)
            except Exception as e:
                logger.warning(f"Gemini API key {key_cred.name} failed: {e}")
                credential_pool.report_failure(key_cred, str(e))
            finally:
                key_cred.mark_idle()

        # 2. OpenRouter
        or_keys = credential_pool.credentials[CredentialType.OPENROUTER_API_KEY]
        logger.debug(f"Failover Chain: Trying OpenRouter keys (total={len(or_keys)})...")
        for key_cred in or_keys:
            if not key_cred.is_available():
                continue
            key_cred.mark_busy()
            try:
                logger.debug(f"Invoking OpenRouter with key: {key_cred.name}...")
                data = await self._call_openrouter(key_cred.value, system_prompt, user_prompt)
                return await self._save_ai_success(key_cred, desc_hash, title, author, data)
            except Exception as e:
                logger.warning(f"OpenRouter API key {key_cred.name} failed: {e}")
                credential_pool.report_failure(key_cred, str(e))
            finally:
                key_cred.mark_idle()

        # 3. Try Groq
        groq_keys = credential_pool.credentials[CredentialType.GROQ_API_KEY]
        logger.debug(f"Failover Chain: Trying Groq keys (total={len(groq_keys)})...")
        for key_cred in groq_keys:
            if not key_cred.is_available():
                continue
            key_cred.mark_busy()
            try:
                logger.debug(f"Invoking Groq with key: {key_cred.name}...")
                data = await self._call_groq(key_cred.value, system_prompt, user_prompt)
                return await self._save_ai_success(key_cred, desc_hash, title, author, data)
            except Exception as e:
                logger.warning(f"Groq API key {key_cred.name} failed: {e}")
                credential_pool.report_failure(key_cred, str(e))
            finally:
                key_cred.mark_idle()

        # 4. Web Search Fallback (if all AI APIs fail)
        logger.error(f"All AI providers and keys failed for '{title}'. Using Web-Search Fallback.")
        return await self._generate_fallback(title, author)

    async def extract_title_author_from_text(self, text: str, cover_image_path: Optional[str] = None) -> Dict[str, str]:
        """Uses AI (multimodal vision + text) to extract the real Arabic title and author from cover image and text extract."""
        if not text and not cover_image_path:
            return {}
            
        from ai.prompt_manager import get_system_prompt
        system_prompt = get_system_prompt("title_extraction")
        
        user_prompt = f"Extract metadata from this book text:\n{text[:2500]}"
        if cover_image_path:
            user_prompt = f"Examine the attached cover image and the extracted book text below to determine the clean Arabic Title and Author.\nText Extract:\n{text[:2000]}"
            
        # 1. Try Gemini
        gemini_keys = credential_pool.credentials[CredentialType.GEMINI_API_KEY]
        for key_cred in gemini_keys:
            if not key_cred.is_available():
                continue
            key_cred.mark_busy()
            try:
                data = await self._call_gemini(key_cred.value, system_prompt, user_prompt, cover_image_path)
                if data.get("title"):
                    credential_pool.report_success(key_cred)
                    return {
                        "title": data.get("title", "").strip(),
                        "author": data.get("author", "").strip(),
                        "translator": data.get("translator", "").strip(),
                        "verifier": data.get("verifier", "").strip()
                    }
            except Exception as e:
                logger.warning(f"Gemini API key {key_cred.name} failed during title extraction: {e}")
                credential_pool.report_failure(key_cred, str(e))
            finally:
                key_cred.mark_idle()

        # 2. Try OpenRouter
        or_keys = credential_pool.credentials[CredentialType.OPENROUTER_API_KEY]
        for key_cred in or_keys:
            if not key_cred.is_available():
                continue
            key_cred.mark_busy()
            try:
                data = await self._call_openrouter(key_cred.value, system_prompt, user_prompt, cover_image_path)
                if data.get("title"):
                    credential_pool.report_success(key_cred)
                    return {
                        "title": data.get("title", "").strip(),
                        "author": data.get("author", "").strip(),
                        "translator": data.get("translator", "").strip(),
                        "verifier": data.get("verifier", "").strip()
                    }
            except Exception as e:
                logger.warning(f"OpenRouter key {key_cred.name} failed during title extraction: {e}")
                credential_pool.report_failure(key_cred, str(e))
            finally:
                key_cred.mark_idle()

        # 3. Try Groq (No vision support, text only fallback)
        groq_keys = credential_pool.credentials[CredentialType.GROQ_API_KEY]
        for key_cred in groq_keys:
            if not key_cred.is_available():
                continue
            key_cred.mark_busy()
            try:
                data = await self._call_groq(key_cred.value, system_prompt, user_prompt)
                if data.get("title"):
                    credential_pool.report_success(key_cred)
                    return {
                        "title": data.get("title", "").strip(),
                        "author": data.get("author", "").strip(),
                        "translator": data.get("translator", "").strip(),
                        "verifier": data.get("verifier", "").strip()
                    }
            except Exception as e:
                logger.warning(f"Groq key {key_cred.name} failed during title extraction: {e}")
                credential_pool.report_failure(key_cred, str(e))
            finally:
                key_cred.mark_idle()

        return {}

    async def _call_gemini(self, api_key: str, system_prompt: str, user_prompt: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Calls Gemini API directly via HTTP using aiohttp, trying multiple models, supporting vision."""
        import aiohttp
        import base64
        models = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
        last_err = None
        
        parts = [{"text": user_prompt}]
        if image_path:
            try:
                with open(image_path, "rb") as img_file:
                    img_data = base64.b64encode(img_file.read()).decode("utf-8")
                parts.append({
                    "inlineData": {
                        "mimeType": "image/png",
                        "data": img_data
                    }
                })
            except Exception as e:
                logger.warning(f"Failed to read image for Gemini inlineData: {e}")
                
        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{"parts": parts}],
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0.2 if image_path else 0.3,
                    "maxOutputTokens": 800
                },
                "safetySettings": [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                ]
            }
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=payload, timeout=30) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            content = result["candidates"][0]["content"]["parts"][0]["text"]
                            return self._parse_json_response(content)
                        else:
                            err_text = await resp.text()
                            logger.warning(f"Gemini model {model} returned status {resp.status}: {err_text}")
                            last_err = RuntimeError(f"Gemini model {model} failed: {err_text}")
            except Exception as e:
                logger.warning(f"Gemini model {model} request failed: {e}")
                last_err = e
        raise last_err or RuntimeError("All Gemini models failed.")

    async def _call_openrouter(self, api_key: str, system_prompt: str, user_prompt: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Calls OpenRouter API using direct aiohttp requests, trying multiple models, supporting vision."""
        import aiohttp
        import base64
        
        models = ["google/gemini-2.5-flash", "meta-llama/llama-3.3-70b-instruct", "deepseek/deepseek-chat"]
        if image_path:
            models = ["google/gemini-2.5-flash", "meta-llama/llama-3.2-11b-vision-instruct"]
            
        last_err = None
        
        user_content = user_prompt
        if image_path:
            try:
                with open(image_path, "rb") as img_file:
                    img_data = base64.b64encode(img_file.read()).decode("utf-8")
                user_content = [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{img_data}"
                        }
                    }
                ]
            except Exception as e:
                logger.warning(f"Failed to read image for OpenRouter Vision payload: {e}")
                
        for model in models:
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://huggingface.co/spaces/arabic-books",
                "X-Title": "Arabic Books Publisher"
            }
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.2 if image_path else 0.3,
                "max_tokens": 800
            }
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=payload, timeout=30) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            content = result["choices"][0]["message"]["content"]
                            return self._parse_json_response(content)
                        else:
                            err_text = await resp.text()
                            logger.warning(f"OpenRouter model {model} returned status {resp.status}: {err_text}")
                            last_err = RuntimeError(f"OpenRouter model {model} failed: {err_text}")
            except Exception as e:
                logger.warning(f"OpenRouter model {model} request failed: {e}")
                last_err = e
        raise last_err or RuntimeError("All OpenRouter models failed.")

    async def _call_groq(self, api_key: str, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Calls Groq API using direct aiohttp requests, trying multiple models."""
        import aiohttp
        models = ["llama-3.3-70b-versatile", "llama-3-8b-8192", "mixtral-8x7b-32768"]
        last_err = None
        for model in models:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.3,
                "max_tokens": 1000
            }
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=payload, timeout=30) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            content = result["choices"][0]["message"]["content"]
                            return self._parse_json_response(content)
                        else:
                            err_text = await resp.text()
                            logger.warning(f"Groq model {model} returned status {resp.status}: {err_text}")
                            last_err = RuntimeError(f"Groq model {model} failed: {err_text}")
            except Exception as e:
                logger.warning(f"Groq model {model} request failed: {e}")
                last_err = e
        raise last_err or RuntimeError("All Groq models failed.")

    def _parse_json_response(self, result_text: str) -> Dict[str, Any]:
        """Cleans and parses raw JSON text returned by model APIs, falling back to regex extraction if JSON is invalid."""
        result_text = result_text.strip()
        if result_text.startswith("```"):
            lines = result_text.splitlines()
            if lines[0].startswith("```json") or lines[0].startswith("```"):
                result_text = "\n".join(lines[1:-1])
        result_text = result_text.strip()
        
        # We need regular expression matching for regex fallback
        import re
        try:
            return json.loads(result_text)
        except Exception as je:
            logger.warning(f"Standard JSON parsing failed in _parse_json_response: {je}. Attempting regex fallback on: {result_text[:200]}")
            extracted = {}
            # Match "key": "value" (supporting lazy matching for values, lookahead for next key or closing brace)
            for key in ["title", "author", "translator", "verifier", "summary", "category"]:
                # Match double quotes with lookahead
                match = re.search(rf'"{key}"\s*:\s*"(.*?)"(?=\s*,\s*"\w+"\s*:|\s*}}\s*$)', result_text, re.DOTALL)
                if match:
                    extracted[key] = match.group(1).strip()
                else:
                    # Match single quotes with lookahead
                    match = re.search(rf"'{key}'\s*:\s*'(.*?)'(?=\s*,\s*'\w+'\s*:|\s*}}\s*$)", result_text, re.DOTALL)
                    if match:
                        extracted[key] = match.group(1).strip()
                        
            # Extract hashtags array if present
            hash_match = re.search(r'"hashtags"\s*:\s*\[(.*?)\]', result_text, re.DOTALL)
            if hash_match:
                tags = re.findall(r'"([^"]+)"', hash_match.group(1))
                if not tags:
                    tags = re.findall(r"'([^']+)'", hash_match.group(1))
                extracted["hashtags"] = tags
                
            return extracted

    async def _save_ai_success(self, key_cred, desc_hash: str, title: str, author: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validates AI response, formats hashtags, caches result, and reports success."""
        summary = data.get("summary", "").strip()
        category = data.get("category", "أدب").strip()
        hashtags = data.get("hashtags", [])
        
        # Robust character length validation check (instead of hardcoded newlines splitlines)
        if not summary or len(summary) < 60:
            raise ValueError("Summary is empty or too short.")
        
        clean_hashtags = []
        for tag in hashtags:
            clean_tag = tag.replace("#", "").strip().replace(" ", "_")
            if clean_tag:
                clean_hashtags.append(clean_tag)
        
        book_tag = title.replace(" ", "_")
        author_tag = author.replace(" ", "_")
        
        if book_tag not in clean_hashtags:
            clean_hashtags.insert(0, book_tag)
        if author_tag not in clean_hashtags:
            clean_hashtags.insert(1, author_tag)
            
        unique_tags = list(dict.fromkeys(clean_hashtags))
        final_tags = unique_tags[:6]
        
        result = {
            "summary": summary,
            "category": category,
            "hashtags": final_tags
        }
        
        # Report success
        credential_pool.report_success(key_cred)
        
        # Cache results
        cache_data = {
            **result,
            "prompt_version": config.PROMPT_VERSION,
            "provider": key_cred.type.name.lower(),
            "cached_at": datetime.now()
        }
        await self.repo.set_ai_cache(desc_hash, cache_data)
        logger.success(f"AI generation succeeded using {key_cred.name} ({key_cred.type.name}) and cached for '{title}'.")
        return result

    async def _generate_fallback(self, title: str, author: str) -> Dict[str, Any]:
        """Generates a rich web-search fallback description if Gemini/OpenRouter/Groq fail or are disabled."""
        safe_title = title.strip()
        safe_author = author.strip() if author else "مؤلف مجهول"
        
        logger.info(f"Generating web-search summary fallback for '{safe_title}'...")
        summary = await self._search_web_for_summary(safe_title, safe_author)
        
        tag_title = re.sub(r"\s+", "_", normalize_word(safe_title))
        tag_author = re.sub(r"\s+", "_", normalize_word(safe_author))
        
        return {
            "summary": summary,
            "category": "أدب",
            "hashtags": [tag_title, tag_author, "كتب_عربية", "قراءة_كتب", "ثقافة", "تحميل_pdf"]
        }

    async def _search_web_for_summary(self, title: str, author: str) -> str:
        """
        Searches Google Books API and DuckDuckGo HTML for a summary of the book.
        Splits and returns a clean 6-10 lines text.
        """
        import aiohttp
        safe_title = title.strip()
        safe_author = author.strip()
        
        # 1. Search Google Books API
        url = f"https://www.googleapis.com/books/v1/volumes?q=intitle:{safe_title}+inauthor:{safe_author}&langRestrict=ar"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        items = data.get("items", [])
                        for item in items:
                            volume_info = item.get("volumeInfo", {})
                            desc = volume_info.get("description", "")
                            if desc and len(desc.strip()) > 50:
                                clean_desc = re.sub(r'<[^>]*>', '', desc).strip()
                                return self._format_summary_lines(clean_desc, title, author)
        except Exception as e:
            logger.warning(f"Google Books API fallback search failed: {e}")
            
        # 2. Search DuckDuckGo text/html search for snippets if Google Books failed
        try:
            search_url = f"https://html.duckduckgo.com/html/?q={safe_title} {safe_author} ملخص كتاب"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
                        if snippets:
                            combined = " ".join([re.sub(r'<[^>]*>', '', s).strip() for s in snippets[:2]])
                            if len(combined) > 50:
                                return self._format_summary_lines(combined, title, author)
        except Exception as e:
            logger.warning(f"DuckDuckGo fallback search failed: {e}")
            
        # 3. Ultimate Fallback (if all search failed)
        return (
            f"هذا الكتاب بعنوان '<b>{safe_title}</b>' للمؤلف <b>{safe_author}</b>:\n"
            f"• يتناول الكتاب بالتحليل والدراسة المفاهيم الأساسية والأفكار الجوهرية التي يقدمها المؤلف.\n"
            f"• يُنصح بقراءته ومراجعته لكل مهتم بهذا المجال ومحب للاطلاع على المعارف والكتب النافعة."
        )

    def _format_summary_lines(self, text: str, title: str, author: str) -> str:
        """Helper to structure raw text into a clean 3-4 lines Arabic summary."""
        text = re.sub(r'\s+', ' ', text).strip()
        sentences = re.split(r'(?<=[.!?؟])\s+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
        
        if len(sentences) < 2:
            sentences = re.split(r'[,،]\s+', text)
            sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
            
        lines = []
        lines.append(f"هذا الكتاب بعنوان '<b>{title}</b>' للمؤلف <b>{author}</b>:")
        
        for s in sentences[:2]:
            lines.append(f"• {s}")
            
        while len(lines) < 3:
            lines.append("• يُقدّم الكتاب نظرة مرجعية شاملة حول هذا الموضوع الهام.")
            
        return "\n".join(lines[:4])

def normalize_word(text: str) -> str:
    """Helper to remove punctuation for hashtags."""
    return re.sub(r"[^\w\s\u0621-\u064A]", "", text)
