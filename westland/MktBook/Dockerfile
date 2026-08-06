FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    sqlite3 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set up working directory
WORKDIR /app

# Copy dependency file
COPY mktbook/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create application user for Hugging Face compatibility (UID 1000)
RUN useradd -m -u 1000 user

# Copy application source code
COPY --chown=user:user . .

# Ensure permissions are correct
RUN chown -R user:user /app

# Switch to non-root user
USER user

# Set environment variables
ENV HOME=/app
ENV PYTHONUNBUFFERED=1
ENV PORT=7860
ENV HOST=0.0.0.0
ENV DATABASE_PATH=/app/mktbook.db
ENV LTI_PRIVATE_KEY_PATH=/app/lti_private_key.pem
ENV OPENAI_API_KEY=""
ENV OPENAI_API_BASE="https://api.deepseek.com"
ENV OPENAI_MODEL="deepseek-chat"

# Make sure start.sh is executable
RUN chmod +x start.sh

# Run startup script
CMD ["./start.sh"]
