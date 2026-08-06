# Gunakan sistem operasi Python
FROM python:3.9

# Buat folder kerja
WORKDIR /app

# Copy file requirements dan install library
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy semua sisa file (termasuk kode .py dan .csv)
COPY . .

# Jalankan server Gunicorn (Hugging Face mewajibkan port 7860)
CMD ["gunicorn", "-b", "0.0.0.0:7860", "iphone_resale:server"]