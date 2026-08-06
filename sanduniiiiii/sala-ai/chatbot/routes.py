"""
Sala AI - Chatbot API Routes
"""
import asyncio
import logging
import os
import tempfile
from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from groq import Groq
from chatbot.language_detect import detect_language
from chatbot.prompts import build_system_prompt, NO_INFO_PHRASES
from chatbot.rag import (
    get_product_context,
    refresh_product_db,
    get_wiki_context,
    backfill_category_metadata,
    get_active_announcement,
)
from chatbot.history import new_session_id, get_history_text, add_exchange
from chatbot.auth import verify_admin
from core.model_router import get_ai_response
from core.translator import translate_text
from analytics.logger import log_interaction
from .voice import generate_voice_bytes

log = logging.getLogger("SalaAI")
router = APIRouter(prefix="/chat", tags=["chatbot"])


class ChatRequest(BaseModel):
    message: str
    language: str | None = None       # optional override: "si" | "en" | "ta"
    session_id: str | None = None     # pass back the session_id from the previous response


class ChatResponse(BaseModel):
    reply: str
    detected_language: str
    session_id: str


class AnnouncementResponse(BaseModel):
    active: bool
    title: str | None = None
    content: str | None = None


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    user_query = request.message.strip()
    session_id = request.session_id or new_session_id()

    # detect language unless explicitly overridden
    language = request.language or detect_language(user_query)

    # Product context and wiki context are independent of each other, and both
    # are blocking calls (embedding inference + local Chroma search). Running
    # them sequentially with plain calls would block the FastAPI event loop
    # for the full duration of both - other in-flight requests would stall
    # meanwhile. asyncio.to_thread() offloads each to a worker thread, and
    # asyncio.gather() runs the two concurrently instead of one after another.
    product_context, wiki_context = await asyncio.gather(
        asyncio.to_thread(get_product_context, user_query),
        asyncio.to_thread(get_wiki_context, user_query),
    )

    # merge both context sources (skip empty ones)
    context_parts = []
    if product_context:
        context_parts.append(f"Product information:\n{product_context}")
    if wiki_context:
        context_parts.append(f"Wiki / policy information:\n{wiki_context}")
    context_text = "\n\n---\n\n".join(context_parts) if context_parts else None

    # pull recent conversation history for this session (for follow-up questions)
    history_text = get_history_text(session_id)

    # build the system prompt - the LLM always answers in English
    system_prompt = build_system_prompt(context_text, history_text)

    # route through Groq -> Gemini -> OpenRouter (English response). This chain
    # makes blocking network calls (requests / SDK calls), so it also runs in
    # a worker thread rather than directly on the event loop.
    reply_en = await asyncio.to_thread(
        get_ai_response, prompt=user_query, system_prompt=system_prompt
    )

    if not reply_en or not reply_en.strip():
        reply_en = None
        reply = NO_INFO_PHRASES.get(language, NO_INFO_PHRASES["en"])
    else:
        reply_en = reply_en.strip()
        # translate to the user's language, protecting brand names/prices/codes.
        # GoogleTranslator does a blocking network call too - same reasoning.
        reply = await asyncio.to_thread(translate_text, reply_en, language)

    reply = reply.strip()

    # remember this exchange for follow-up questions in the same session
    add_exchange(session_id, user_query, reply_en or reply)

    # log this interaction for analytics, without slowing down the response
    background_tasks.add_task(
        log_interaction, query=user_query, reply=reply, language=language, source="web"
    )

    return ChatResponse(reply=reply, detected_language=language, session_id=session_id)


@router.get("/announcement", response_model=AnnouncementResponse)
async def announcement():
    """
    Returns the currently active announcement (if any), so the widget can
    show it automatically right after the greeting, before the user asks
    anything. No auth required - this is called by every visitor's widget
    on load.
    """
    result = get_active_announcement()
    if not result:
        return AnnouncementResponse(active=False)
    return AnnouncementResponse(
        active=True, title=result["title"], content=result["content"]
    )


@router.post("/backfill-categories")
async def backfill_categories(username: str = Depends(verify_admin)):
    """
    ONE-TIME FIX endpoint: backfills category metadata for already-indexed
    products by extracting it from each product's already-embedded
    "Category: ..." text line, instead of re-fetching from WooCommerce.
    Use this while the WooCommerce/hosting firewall issue (403 errors) is
    unresolved - it works entirely off data already in the vector DB, no
    WooCommerce API call needed. Safe to call multiple times.
    Protected: requires admin username/password (HTTP Basic Auth).
    """
    result = backfill_category_metadata()
    return result


@router.post("/refresh-products")
async def refresh_products(username: str = Depends(verify_admin)):
    """Manually trigger a WooCommerce product re-sync into the vector DB.
    Protected: requires admin username/password (HTTP Basic Auth).
    """
    store = refresh_product_db()
    if store is None:
        return {"status": "failed", "message": "No products fetched"}
    count = store._collection.count()
    return {"status": "success", "products_indexed": count}


# ---------------------------------------------------------------------------
# Voice input: speech-to-text via Groq's hosted Whisper model
# ---------------------------------------------------------------------------

_groq_transcribe_client = None


def get_groq_transcribe_client():
    """Lazy-init a Groq client for audio transcription (reuses the same
    GROQ_API_KEY already set for the chat LLM calls)."""
    global _groq_transcribe_client
    if _groq_transcribe_client is None:
        _groq_transcribe_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _groq_transcribe_client


class TranscribeResponse(BaseModel):
    text: str


# maps the widget's language codes to Whisper's ISO-639-1 codes.
# "auto" -> None lets Whisper auto-detect the spoken language.
WHISPER_LANG_MAP = {"si": "si", "en": "en", "ta": "ta", "auto": None}

# Whisper's "prompt" param biases transcription toward this vocabulary -
# it doesn't need to match the actual audio, it just primes the model to
# recognize these terms correctly instead of mangling them. Extend this
# list as more mispronounced/mistranscribed product terms come up.
WHISPER_VOCAB_PROMPT = (
    "Sala Enterprises, UPS, PBX, IP PBX, FXO, FXS, WiFi, WiFi 6, router, "
    "extender, access point, GPS tracker, projector, warranty, invoice, "
    "වගකීම, බැටරි, රවුටර්"
)


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str = "auto",
):
    """
    Accepts a short audio clip recorded in the browser (webm/ogg/mp4/wav)
    and returns the transcribed text using Groq's hosted Whisper model.
    No admin auth needed - this is called by regular site visitors using
    the voice input button in the chat widget.
    """
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    whisper_lang = WHISPER_LANG_MAP.get(language, None)
    suffix = os.path.splitext(file.filename or "audio.webm")[1] or ".webm"

    def _transcribe():
        client = get_groq_transcribe_client()
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            with open(tmp_path, "rb") as f:
                kwargs = {
                    "file": (os.path.basename(tmp_path), f.read()),
                    "model": "whisper-large-v3-turbo",
                    "response_format": "text",
                    "prompt": WHISPER_VOCAB_PROMPT,
                }
                if whisper_lang:
                    kwargs["language"] = whisper_lang
                result = client.audio.transcriptions.create(**kwargs)
            return str(result).strip()
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    text = await asyncio.to_thread(_transcribe)

    if not text:
        raise HTTPException(status_code=422, detail="Could not transcribe audio - please try again")

    return TranscribeResponse(text=text)


# ---------------------------------------------------------------------------
# Voice output: text-to-speech via Azure Neural TTS (si-LK / ta-IN / en-US)
# ---------------------------------------------------------------------------

class VoiceRequest(BaseModel):
    text: str
    language: str = "en"   # "si" | "ta" | "en"


@router.post("/voice")
async def voice_output(request: VoiceRequest):
    """
    Converts the given text to speech using Azure Neural TTS and returns raw
    mp3 bytes. Replaces the old gTTS-based implementation, which didn't
    reliably support Sinhala and caused CloudFront 504 timeouts.
    """
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    try:
        audio_bytes = await asyncio.to_thread(
            generate_voice_bytes, text, request.language
        )
    except Exception as e:
        log.error(f"Voice output failed (lang={request.language}): {e}")
        raise HTTPException(status_code=502, detail="Voice generation failed - please try again")

    return Response(content=audio_bytes, media_type="audio/mpeg")