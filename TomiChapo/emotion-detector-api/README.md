---
title: Emotion Detector Api
emoji: 😊
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 4.44.0
app_file: app_gradio.py
pinned: false
---


# Emotion Detector API

API de detección de emociones en español usando BERT fine-tuned.

## Modelo
- **Base:** dccuchile/bert-base-spanish-wwm-cased
- **Emociones:** alegría, tristeza, enojo, miedo, sorpresa, asco, neutral
- **Accuracy:** 99.99%
- **Dataset:** 195K ejemplos (chat + business español multi-regional)

## Uso

### Endpoint: POST /api/predict

```bash
curl -X POST "https://tomichapo-emotion-detector-api.hf.space/api/predict" \
  -H "Content-Type: application/json" \
  -d '{"text": "Estoy muy feliz con este servicio"}'
```

### Respuesta

```json
{
  "text": "Estoy muy feliz con este servicio",
  "emotion": "alegría",
  "confidence": 0.9876
}
```

## Endpoints

- `GET /` - Health check
- `POST /api/predict` - Detectar emoción
- `POST /api/feedback` - Enviar feedback (requiere MongoDB)

## Desarrollado por
TomiChapo - 2025
