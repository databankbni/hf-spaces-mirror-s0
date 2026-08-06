# Use official Python runtime as a parent image
# Slim version is smaller and safer
FROM python:3.13-slim

# Set the working directory in the container
WORKDIR /app

# Copy the file with the dependencies to the container
COPY requirements.txt .

# Install the Python dependencies
# --no-cache-dir keeps the image size down
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Hugging Face Spaces expects the app to run on port 7860
EXPOSE 7860

# Define the environment variable for Flask
ENV FLASK_APP=app.py

# Run the application using Gunicorn
# -w 2: 2 worker processes (adjust based on RAM/CPU, 2 is safe for HF free tier)
# -b 0.0.0.0:7860: Bind to all interfaces on port 7860
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:7860", "app:app"]
