---
title: OpenAI Edge TTS
emoji: "\U0001F50A"
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
license: gpl-3.0
app_port: 7860
---

# OpenAI Edge TTS

OpenAI-compatible TTS API using Microsoft Edge's free online TTS service.

## API Endpoints

- `POST /v1/audio/speech` - Text to Speech (OpenAI compatible)
- `GET /v1/models` - List available models
- `GET /v1/audio/voices` - List available voices

## Usage

```bash
curl -X POST https://YOUR_SPACE_URL/v1/audio/speech \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key" \
  -d '{
    "input": "Hello, world!",
    "voice": "en-US-AvaNeural",
    "model": "tts-1"
  }' \
  --output speech.mp3
```
