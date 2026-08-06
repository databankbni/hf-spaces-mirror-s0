FROM python:3.11-slim

# git is required — GitPython shells out to it for repo cloning
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only torch first: the default PyPI wheel bundles CUDA (~2 GB)
COPY requirements.txt .
RUN pip install --no-cache-dir torch==2.3.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# HF Spaces runs containers as UID 1000 — make everything writable for it
RUN useradd -m -u 1000 user && chown -R user:user /app
USER user
ENV HF_HOME=/app/.cache \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache \
    STORAGE_PATH=/app/storage \
    DISK_CACHE_DIR=/app/storage/.cache \
    CHROMA_PERSIST_DIR=/app/storage/.vectors

# Pre-bake the embedding model so cold starts don't download ~90 MB
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY --chown=user:user . .

EXPOSE 7860

# Single worker: ingestion runs in-process and state lives on local disk
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
