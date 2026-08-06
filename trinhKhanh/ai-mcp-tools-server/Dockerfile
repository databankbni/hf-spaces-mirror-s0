FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# HF Spaces yêu cầu non-root user UID 1000
RUN useradd -m -u 1000 -s /bin/bash appuser

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser . .
RUN mkdir -p /app/static && chown -R appuser:appuser /app/static

USER 1000

CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"