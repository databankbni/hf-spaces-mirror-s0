FROM python:3.11-slim

# ── 안전민국 · Hugging Face Space(Docker) 런타임 이미지 ────────────────
#   진입점: uvicorn app:app  (FastAPI 단일 페이지 + /api/*)
#   포트   : 7860 (HF Space 기본, README.md app_port 와 일치)
#   비밀키 : env 우선 로더 → HF Settings의 Secrets 로 주입 (코드 수정 불필요)
#            DATA_GO_KR_KEY(기상청·통계연보), JUSO_KEY(도로명주소) 만 넣는다.
#            ⛔ ANTHROPIC_API_KEY 는 넣지 않는다 — 규칙 폴백으로 0원 동작(과금 방지).
# ──────────────────────────────────────────────────────────────────────

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 1) 의존성 먼저 (레이어 캐시)
COPY requirements-deploy.txt ./
RUN pip install --no-cache-dir -r requirements-deploy.txt

# 2) 런타임 코드·데이터 (data/raw·tests·build 스크립트는 .dockerignore 로 제외)
COPY app.py ./
COPY engine ./engine
COPY data ./data
COPY disasters ./disasters
COPY static ./static

EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
