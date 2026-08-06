FROM python:3.11-slim

WORKDIR /app

# rdkit drawing needs a couple of system libs
RUN apt-get update && apt-get install -y --no-install-recommends \
      libxrender1 libxext6 libexpat1 libxau6 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# HuggingFace Spaces expects the app on port 7860
EXPOSE 7860

RUN python download_molformer.py

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]

# cache-bust 1783301098
