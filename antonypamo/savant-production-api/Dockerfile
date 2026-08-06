FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all production assets
COPY app.py .
COPY logreg_rrf_savant.joblib .
COPY rrf_nodes.pt .
COPY savant_rrf_api_manifest_phi12.json .

# Expose port 7860 for Hugging Face Spaces
EXPOSE 7860

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
