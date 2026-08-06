# Stage 1 — build the cyberpunk React frontend from its unmodified sources.
# The frontend folder is a copy of cyberpunk-frontend/ (no node_modules, no
# screenshots, no logs). We only inject VITE_API_URL=/api at build time so
# axios calls go to the same-origin /api/* path inside this Space.
FROM node:22-slim AS frontend-builder

WORKDIR /build

# Cache npm install layer (using npm install because the upstream
# package-lock.json is slightly out of sync with package.json — npm ci is
# strictly read-only and would fail. The frontend sources are untouched;
# this is build-tooling configuration only.)
COPY frontend_src/package.json frontend_src/package-lock.json ./
RUN npm install --no-audit --no-fund --legacy-peer-deps

# Copy the rest of the unmodified frontend sources and build
COPY frontend_src/ ./

# Same-origin path: browser will hit /api/* on the Space domain, our FastAPI
# middleware (see app.py) rewrites /api/* → /* so server.py routes answer.
ENV VITE_API_URL=/api
RUN npm run build


# Stage 2 — Python runtime with the full RAG backend and the freshly built
# static frontend copied in from the builder stage.
FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Backend deps (pinned to real, existing versions — see requirements.txt)
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Pre-download the same full-quality models as before
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('intfloat/multilingual-e5-large-instruct', device='cpu', cache_folder='/app/.cache')"

RUN python -c "from sentence_transformers import CrossEncoder; \
    CrossEncoder('BAAI/bge-reranker-v2-m3', device='cpu', max_length=512)" \
    || python -c "from sentence_transformers import CrossEncoder; \
    CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2', device='cpu')"

# Copy app code, chroma_db, source docs, frontend_src (for provenance)
COPY . .

# Drop the freshly built frontend into /app/static (overrides any prior copy)
COPY --from=frontend-builder /build/dist ./static

ENV API_PORT=7860
ENV API_HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/app/.cache
ENV TRANSFORMERS_CACHE=/app/.cache
ENV SENTENCE_TRANSFORMERS_HOME=/app/.cache
ENV LOG_LEVEL=info
ENV CORS_ALLOWED_ORIGINS=*

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=3 \
    CMD curl -fsS http://localhost:7860/api/health || exit 1

CMD ["python", "app.py"]