FROM python:3.11-slim

WORKDIR /app

RUN mkdir -p /app/.cache && chmod -R 777 /app/.cache

ENV HF_HOME=/app/.cache/huggingface
ENV TRANSFORMERS_CACHE=/app/.cache/huggingface

RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app_gradio.py .

EXPOSE 7860

CMD ["python", "app_gradio.py"]
