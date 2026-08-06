# Hugging Face Spaces (Docker SDK) — InterStock ML prediction service.
# HF Spaces route traffic to port 7860.
FROM python:3.11-slim

WORKDIR /app

# System deps kept minimal; tensorflow-cpu wheels are self-contained.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV TF_CPP_MIN_LOG_LEVEL=3 \
    OMP_NUM_THREADS=2 \
    PORT=7860

EXPOSE 7860

# Long timeout: yfinance/Twelve Data fetch + LSTM inference.
CMD ["gunicorn", "server:app", "--bind", "0.0.0.0:7860", "--workers", "1", "--timeout", "180"]
