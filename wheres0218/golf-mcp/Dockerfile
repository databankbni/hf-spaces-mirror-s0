FROM python:3.11-slim

WORKDIR /app

# System deps for chromadb/onnxruntime and for mediapipe/opencv (libGL + glib).
RUN apt-get update && apt-get install -y --no-install-recommends \
build-essential \
libgl1 \
libglib2.0-0 \
&& rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Build the vector DB from the single JSON data file at image-build time.
# This also downloads the embedding model into the image, so the first search
# on the deployed server is instant and needs no runtime download.
COPY build_db.py heo_tips_full.json ./
RUN python build_db.py

# App code (reads the heo_db folder created by the build step above)
COPY golf_mcp.py .

# Hugging Face Spaces route traffic to port 7860 (app_port in README).
# golf_mcp.py binds $PORT, so setting it here makes the server listen on 7860.
ENV PORT=7860
EXPOSE 7860

CMD ["python", "golf_mcp.py"]
