FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# HF Spaces runs the container as a non-root user; /tmp is always writable.
# If you buy persistent storage for the Space, change this to /data instead.
ENV DATA_DIR=/tmp/data
ENV PYTHONUNBUFFERED=1

EXPOSE 7860

# Single worker + threads: the app serializes JSON writes with an in-process
# lock, which only protects data if all requests share one process.
CMD ["gunicorn", "-b", "0.0.0.0:7860", "-w", "1", "--threads", "8", "app:app"]
