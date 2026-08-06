FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Copy requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all files into the container
COPY . .

# Expose port 7860 which Hugging Face Spaces expects
EXPOSE 7860

# Command to run the Flask app using Gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:7860", "--workers", "2", "--threads", "4", "app:app"]
