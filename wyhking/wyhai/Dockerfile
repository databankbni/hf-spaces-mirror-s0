FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src:/app \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    PRICING_MODEL_VERSION=v194 \
    ASR_PROVIDER=disabled \
    HOSTED_FAST_PRICING=1 \
    DEPLOY_LITE_MODE=1 \
    DEFAULT_TO_AGENT_UI=1 \
    INTERNAL_AUTH_ENABLED=1 \
    PRICING_PRELOAD_SERVICE=0 \
    ENABLE_V195_REVIEWED_BUSINESS_SURFACE=true \
    ENABLE_V195_ON_DEMAND_EXACT_CELL=true \
    ENABLE_V195_SUPERVISED_COMMERCIAL_ROUTE=true \
    V195_USE_MANUAL_IDENTITY_PANELS=true \
    V195_MANUAL_IDENTITY_PANEL_PATH=/app/data/manual_price_book/manual_identity_price_panels_v195438.parquet \
    V195_SINGLE_ANSWER_BOOK_PATH=/app/data/v195/unified_single_answer_price_book_v195439.parquet \
    HF_HOME=/tmp/huggingface

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Keep the heavyweight dependency layer identical to the previous production
# image, then override runtime preload switches afterward so HF can reuse it.
ENV PRICING_PRELOAD_SERVICE=1 \
    PRICING_BACKGROUND_PRELOAD=1 \
    PRICING_AGENT_ENABLE_LLM=false \
    SELECTION_PRELOAD_SERVICE=1 \
    SELECTION_BACKGROUND_PRELOAD=1

COPY . /app

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/feedback_records /app/outputs \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["sh", "-c", "python scripts/prepare_hf_runtime_assets.py && exec gunicorn --bind 0.0.0.0:${APP_PORT:-8000} --workers 1 --threads 4 --timeout 180 --graceful-timeout 30 --access-logfile - --error-logfile - app:app"]
