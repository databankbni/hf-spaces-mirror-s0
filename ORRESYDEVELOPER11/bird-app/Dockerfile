FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir tensorflow-cpu==2.13.0 2>/dev/null || pip install --no-cache-dir tensorflow==2.13.0
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Decode cached embeddings from base64 text (avoids binary files in git)
RUN python _embeddings_data.py

EXPOSE 7860

ENV PORT=7860 FLASK_DEBUG=0 TF_CPP_MIN_LOG_LEVEL=2

CMD ["python", "app.py", "--no-ssl"]