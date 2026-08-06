from fastapi import FastAPI, UploadFile, File
from fastapi.responses import Response
from piper import PiperVoice
import whisper
import shutil
import os
import subprocess
import wave
import tempfile
from pathlib import Path

app = FastAPI(title="AI Services — STT + TTS")

# ── Paths ────────────────────────────────────────────────────────────────────
VOICE_MODEL = "/app/voices/en_US-amy-medium.onnx"   # mounted from voices/ dir

# ── Load models once at startup ──────────────────────────────────────────────
print("Loading Whisper tiny model on CPU...")
stt_model = whisper.load_model("tiny", device="cpu")
print("Whisper model loaded ✓")

print("Loading Piper voice model...")
try:
    tts_voice = PiperVoice.load(VOICE_MODEL)
    print("Piper voice model loaded ✓")
except Exception as e:
    print(f"WARNING: Failed to load Piper model: {e}")
    tts_voice = None


# ── Helpers ──────────────────────────────────────────────────────────────────
def get_extension(filename: str) -> str:
    return Path(filename).suffix or ".webm"


def convert_to_wav(input_path: str, output_path: str) -> bool:
    """Convert any audio format to WAV using ffmpeg."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, output_path],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception as e:
        print(f"ffmpeg error: {e}")
        return False


def convert_wav_to_mp3(wav_path: str, mp3_path: str) -> bool:
    """Convert WAV to MP3 using ffmpeg."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", wav_path,
             "-codec:a", "libmp3lame", "-qscale:a", "2", mp3_path],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception as e:
        print(f"ffmpeg mp3 conversion error: {e}")
        return False


# ── STT Endpoint ─────────────────────────────────────────────────────────────
@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """
    Speech-to-text via OpenAI Whisper (tiny, CPU).
    Accepts any audio format (webm, mp3, wav, ogg, etc.)
    Returns: { "text": "transcribed text" }
    """
    ext = get_extension(file.filename or "audio.webm")
    tmp_input = f"/tmp/stt_input{ext}"
    tmp_wav   = "/tmp/stt_converted.wav"

    try:
        # Save uploaded file
        with open(tmp_input, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Convert to WAV for Whisper if needed
        if ext.lower() in [".webm", ".ogg", ".mp4", ".m4a"]:
            success = convert_to_wav(tmp_input, tmp_wav)
            audio_file = tmp_wav if success else tmp_input
        else:
            audio_file = tmp_input

        print(f"Transcribing: {audio_file} ({os.path.getsize(audio_file)} bytes)")
        result = stt_model.transcribe(audio_file)
        text = result.get("text", "").strip()

        if not text:
            return {"error": "No speech detected in audio"}

        print(f"Transcription: {text[:60]}...")
        return {"text": text}

    except Exception as e:
        print(f"STT error: {e}")
        return {"error": f"Transcription failed: {str(e)}"}

    finally:
        for path in [tmp_input, tmp_wav]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass


# ── TTS Endpoint ─────────────────────────────────────────────────────────────
@app.post("/tts")
async def tts(payload: dict):
    """
    Text-to-speech via Piper TTS (en_US-amy-medium).
    Body: { "text": "Hello world" }
    Returns: audio/mpeg (MP3 binary)
    """
    if not tts_voice:
        return Response(
            content=b'{"error":"TTS model not loaded"}',
            status_code=503,
            media_type="application/json"
        )

    text = payload.get("text", "").strip()
    if not text:
        return Response(
            content=b'{"error":"text field is required"}',
            status_code=400,
            media_type="application/json"
        )

    if len(text) > 5000:
        return Response(
            content=b'{"error":"Text too long (max 5000 chars)"}',
            status_code=400,
            media_type="application/json"
        )

    tmp_wav = None
    tmp_mp3 = None

    try:
        # Generate temp file paths
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wf:
            tmp_wav = wf.name
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as mf:
            tmp_mp3 = mf.name

        print(f"Generating TTS for: {text[:50]}...")

        # Synthesize to WAV with Piper
        with wave.open(tmp_wav, "wb") as wav_file:
            tts_voice.synthesize(text, wav_file)

        # Convert WAV → MP3
        if not convert_wav_to_mp3(tmp_wav, tmp_mp3):
            raise RuntimeError("ffmpeg WAV→MP3 conversion failed")

        with open(tmp_mp3, "rb") as f:
            audio_bytes = f.read()

        print(f"TTS done — {len(audio_bytes)} bytes")
        return Response(content=audio_bytes, media_type="audio/mpeg")

    except Exception as e:
        print(f"TTS error: {e}")
        return Response(
            content=f'{{"error":"TTS failed: {str(e)}"}}'.encode(),
            status_code=500,
            media_type="application/json"
        )

    finally:
        for path in [tmp_wav, tmp_mp3]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass


# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status": "ok",
        "stt": {"model": "whisper-tiny", "device": "cpu"},
        "tts": {
            "model": "en_US-amy-medium",
            "loaded": tts_voice is not None
        }
    }


@app.get("/")
def root():
    return {
        "service": "AI Services — STT + TTS",
        "endpoints": {
            "POST /transcribe": "Speech-to-text (upload audio file)",
            "POST /tts":        "Text-to-speech (JSON body: {text})",
            "GET  /health":     "Service health check"
        }
    }
