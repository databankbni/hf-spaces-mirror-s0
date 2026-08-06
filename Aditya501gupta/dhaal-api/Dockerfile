# DHAAL API — Hugging Face Spaces (Docker SDK) / any container host
FROM python:3.11-slim

WORKDIR /code
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY frontend/demo.html ./frontend/demo.html
COPY data ./data

# HF Spaces expects the app on port 7860
EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
