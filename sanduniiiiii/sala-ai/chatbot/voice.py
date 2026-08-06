"""
Sala AI - Voice Generation (Azure Speech Neural TTS)
Replaces the old gTTS-based module. Uses official Microsoft Azure Neural voices,
which properly support Sinhala (si-LK) and Tamil (ta-IN), unlike gTTS.

Setup required:
    pip install azure-cognitiveservices-speech

Environment variables required (set these in your .env file / hosting env,
NEVER hardcode the key in this file or commit it to git):
    AZURE_SPEECH_KEY=<your key1 or key2 from Azure Portal>
    AZURE_SPEECH_REGION=southeastasia
"""
import io
import os
import logging

import azure.cognitiveservices.speech as speechsdk

log = logging.getLogger("SalaAI")

# Map our internal language codes to Azure Neural voice names.
# Feel free to swap Female/Male voices below.
AZURE_VOICE_MAP = {
    "si": "si-LK-SameeraNeural",   # Sinhala (Male) - use si-LK-ThiliniNeural for Female
    "ta": "ta-IN-ValluvarNeural",  # Tamil (Male) - use ta-IN-PallaviNeural for Female
    "en": "en-US-JennyNeural",     # English (Female)
}

AZURE_SPEECH_KEY = os.environ.get("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.environ.get("AZURE_SPEECH_REGION", "southeastasia")


def _synthesize(text: str, voice_name: str) -> bytes:
    """Low-level call to Azure Speech SDK. Returns mp3 bytes in-memory."""
    if not AZURE_SPEECH_KEY:
        raise RuntimeError(
            "AZURE_SPEECH_KEY is not set. Add it to your .env file / environment."
        )

    speech_config = speechsdk.SpeechConfig(
        subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION
    )
    speech_config.speech_synthesis_voice_name = voice_name
    # mp3 output so file sizes stay small and browsers can play it directly
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3
    )

    # No audio device output - we want the raw bytes back, not played on the server
    audio_config = None
    synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=speech_config, audio_config=audio_config
    )

    result = synthesizer.speak_text_async(text[:1000]).get()

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        return result.audio_data

    if result.reason == speechsdk.ResultReason.Canceled:
        cancellation = result.cancellation_details
        log.error(
            f"Azure TTS canceled: {cancellation.reason} - {cancellation.error_details}"
        )
        raise RuntimeError(f"Azure TTS failed: {cancellation.error_details}")

    raise RuntimeError(f"Azure TTS failed with reason: {result.reason}")


def generate_voice_bytes(text: str, language: str = "en") -> bytes:
    """
    Generates speech audio for the given text and returns raw mp3 bytes.
    Falls back to English if the requested language fails for any reason
    (e.g. transient Azure error), so the user always gets *some* audio back.
    """
    voice_name = AZURE_VOICE_MAP.get(language, AZURE_VOICE_MAP["en"])

    try:
        return _synthesize(text, voice_name)
    except Exception as e:
        log.error(f"Voice generation failed (lang={language}, voice={voice_name}): {e}")
        if voice_name != AZURE_VOICE_MAP["en"]:
            log.info("Falling back to English TTS")
            return _synthesize(text, AZURE_VOICE_MAP["en"])
        raise