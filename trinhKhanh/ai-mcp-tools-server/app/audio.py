import io
import asyncio
import edge_tts
import speech_recognition as sr
from . import state

logger = state.logger


def _sync_stt(audio_bytes: bytes) -> str:
    if not audio_bytes:
        return ""
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
            audio = recognizer.record(source)
        return recognizer.recognize_google(audio, language="vi-VN")
    except sr.UnknownValueError:
        return "Chú Robot không nghe rõ con nói gì."
    except Exception as e:
        logger.warning(f"⚠️ [AUDIO] Lỗi STT: {e}")
        return "Chú Robot không nghe rõ con nói gì."


async def audio_to_text(audio_bytes: bytes) -> str:
    return await asyncio.get_event_loop().run_in_executor(None, _sync_stt, audio_bytes)


async def text_to_audio_bytes(text: str, max_retries: int = 2) -> bytes:
    clean = (text or "").strip().replace("°C", " độ C").replace("°", " độ")
    if not clean:
        return b""
    for attempt in range(max_retries):
        try:
            communicate = edge_tts.Communicate(clean, "vi-VN-HoaiMyNeural")
            data = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    data.extend(chunk["data"])
            if data:
                return bytes(data)
        except Exception as e:
            logger.warning(f"⚠️ [AUDIO] Lỗi TTS lần {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
            else:
                logger.error("❌ [AUDIO] Đã hết số lần thử lại TTS.")
    return b""