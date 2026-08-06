# Hugging Face Spaces (Docker SDK) expects the app to listen on port 7860
# and the container to run without relying on root-owned host volumes.
FROM python:3.11-slim

WORKDIR /app

# system deps kept minimal; this app has no native build requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# HF Spaces containers run as a non-root user by default (UID 1000).
# Create that user explicitly and make sure the app dir (incl. data/) is writable.
RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/data/uploads /app/data/outputs \
    && chown -R appuser:appuser /app

USER appuser

ENV PORT=7860 \
    DATA_DIR=/app/data \
    PYTHONUNBUFFERED=1

EXPOSE 7860

# workers=1 is required: job state lives in an in-memory dict per process.
# threads=4 lets chunk uploads + status polling be handled concurrently
# without needing multiple processes (which would split the job state).
CMD ["gunicorn", "app:app", "--worker-class", "gthread", "--workers", "1", "--threads", "4", "--timeout", "120", "--bind", "0.0.0.0:7860"]
