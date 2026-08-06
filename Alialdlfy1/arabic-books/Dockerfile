# Use the official lightweight Python image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860

# Set work directory
WORKDIR /app

# Install system dependencies (required for compiling some packages or running fitz/PyMuPDF)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . /app/

# Create temporary and logs folders with correct permissions
RUN mkdir -p /app/temp /app/logs && \
    chmod -R 777 /app/temp /app/logs

# Expose port 7860 (HuggingFace Spaces default port)
EXPOSE 7860

# Run the application
CMD ["python", "app.py"]
