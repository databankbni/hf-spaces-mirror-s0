# Use an official lightweight Python image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files and starting database
COPY main.py videos.json .

# Expose port 7860 (Hugging Face Spaces default container port)
EXPOSE 7860

# Run the application
CMD ["python", "main.py"]
