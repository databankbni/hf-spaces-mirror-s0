# ──────────────────────────────────────────────────────────────────────────────
# Stage 1 — dependency builder
#   Compiles wheels once; the final image copies only the installed packages.
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# ADDED CMAKE HERE (Required for face_recognition/dlib)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .

# ── ADD THIS LINE: Restrict CMake to a single thread to prevent OOM errors ──
ENV CMAKE_BUILD_PARALLEL_LEVEL=1

# ADDED --default-timeout=1000 to prevent network timeouts on huge packages
RUN pip install --default-timeout=1000 --no-cache-dir --prefix=/install -r requirements.txt

# ──────────────────────────────────────────────────────────────────────────────
# Stage 2 — runtime image
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# System libs required by OpenCV and FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy the YOLO weight file (must exist locally — avoids a runtime download)
COPY yolov8n.pt .
COPY weapon.pt .
# plate.pt is optional — copy only if present (Docker will skip if missing via .dockerignore trick)
# If you have the file, add: COPY plate.pt .
COPY plate.pt .

ENV YOLO_CONFIG_DIR=/tmp/Ultralytics

# Smoke-test: verify the model loads correctly at build time
RUN python -c "from ultralytics import YOLO; m = YOLO('yolov8n.pt'); print('Model OK')"

# Copy application source
COPY app.py .

# Expose FastAPI port
EXPOSE 7860

# Run with Uvicorn — 1 worker (threading handles concurrency internally)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]