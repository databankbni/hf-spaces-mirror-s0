# Backend MedParcours AI — HF Space
FROM python:3.11-slim

# Cài đặt thư viện hệ thống cần thiết cho opencv-python-headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements và cài đặt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy TẤT CẢ các file code (bao gồm cả ecg_engine.py vừa tạo) vào container
COPY . .

EXPOSE 7860

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]