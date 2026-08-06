# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PORT 7860

# Set the working directory in the container
WORKDIR /app

# Install system dependencies (for PyMuPDF/fitz and PDF processing)
# Also include libgl1 for fitz (PyMuPDF) and ca-certificates for SSL
RUN apt-get update && apt-get install -y \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    libgl1 \
    libglib2.0-0 \
    ca-certificates \
    ghostscript \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Create uploads and output directories
RUN mkdir -p uploads output

# Expose the port the app runs on
EXPOSE 7860

# Define the command to run the app
# Set REQUESTS_CA_BUNDLE to the local custom bundle if it exists
ENV REQUESTS_CA_BUNDLE=/app/custom_bundle.pem
CMD ["python", "app.py"]
