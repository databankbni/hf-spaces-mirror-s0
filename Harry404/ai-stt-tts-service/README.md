---
title: AI Services STT TTS
emoji: 🎙️
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
app_port: 7860
---

# AI Services — Speech-to-Text + Text-to-Speech

A combined FastAPI service providing:

- **`POST /transcribe`** — Speech-to-text via OpenAI Whisper (tiny, CPU)
- **`POST /tts`** — Text-to-speech via Piper TTS (`en_US-amy-medium`)
- **`GET /health`** — Health check

## Usage

### STT
```bash
curl -X POST https://YOUR-SPACE.hf.space/transcribe \
  -F "file=@audio.webm"
```

### TTS
```bash
curl -X POST https://YOUR-SPACE.hf.space/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world"}' \
  --output response.mp3
```
