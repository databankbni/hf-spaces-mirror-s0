# ── Base image ────────────────────────────────────────────────────────────────
# Python 3.11 slim keeps the image small while supporting all dependencies
FROM python:3.11-slim

# ── System dependencies ───────────────────────────────────────────────────────
# ffmpeg     : audio format conversion for Whisper (webm→wav) and TTS (wav→mp3)
# espeak-ng  : phoneme engine required by piper-tts pip package
# libsndfile1: required by soundfile / piper audio backend
RUN apt-get update && apt-get install -y \
    ffmpeg \
    espeak-ng \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────────
# Copy requirements first so Docker caches this layer (faster rebuilds)
COPY requirements.txt .
# Upgrade pip and install setuptools first (openai-whisper needs pkg_resources)
RUN pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

# ── Voice model ───────────────────────────────────────────────────────────────
# Copy your local en_US-amy-medium model (63MB) into the image
# This avoids runtime downloads and makes the Space load instantly
COPY en_US-amy-medium.onnx /app/voices/en_US-amy-medium.onnx
COPY en_US-amy-medium.onnx.json /app/voices/en_US-amy-medium.onnx.json

# ── Application code ──────────────────────────────────────────────────────────
COPY app.py .

# ── Hugging Face Spaces runs on port 7860 ─────────────────────────────────────
EXPOSE 7860

# ── Start the FastAPI server ──────────────────────────────────────────────────
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
