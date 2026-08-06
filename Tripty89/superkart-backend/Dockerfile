# Use a minimal base image with Python 3.9 installed
FROM python:3.9-slim

# Set the working directory inside the container to /app
WORKDIR /app

# Copy all files from the current directory on the host to the container's /app directory
COPY . .

# Install Python dependencies listed in requirements.txt
RUN pip3 install -r requirements.txt

# Expose the port the Flask app listens on (Hugging Face Docker Spaces default)
EXPOSE 7860

# Define the command to run the Flask app, served via Gunicorn, on port 7860
CMD ["gunicorn", "-b", "0.0.0.0:7860", "app:app"]
