FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies & Node.js for frontend static export
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . .

# Build frontend static export
RUN cd frontend && npm install && npm run build

# Expose port 7860 (Hugging Face Spaces default port)
EXPOSE 7860

# Run FastAPI server (which serves the mounted frontend and API endpoints)
CMD if [ "$RUN_TELEGRAM_PUBLIC_BOT" = "true" ]; then python -m core.bot & fi; uvicorn core.api:app --host 0.0.0.0 --port 7860
