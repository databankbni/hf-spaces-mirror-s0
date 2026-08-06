FROM python:3.11-slim

# Redirect model caches to /tmp (the only writable directory on HF Spaces)
ENV HF_HOME=/tmp/huggingface
ENV TORCH_HOME=/tmp/torch

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --default-timeout=120 -r requirements.txt

COPY . .

EXPOSE 7860

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "7860"]