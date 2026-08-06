# The System — portfolio agent, sized for a free Hugging Face Docker Space.
FROM python:3.11-slim

# Non-root user (HF requirement / good hygiene)
RUN useradd -m -u 1000 user

# uv for fast, locked installs
COPY --from=ghcr.io/astral-sh/uv:0.7.13 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project -o requirements.txt \
    && uv pip install --system -r requirements.txt \
    && rm requirements.txt

COPY app ./app

USER user
EXPOSE 7860

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
