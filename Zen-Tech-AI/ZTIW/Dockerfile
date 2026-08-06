# Start with a standard Python environment
FROM python:3.10-slim

# Set the working directory inside the server
WORKDIR /app

# Copy your requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your main.py code into the server
COPY . .

# Give the server permission to create your "zentech_data" folder
RUN chmod -R 777 /app

# Tell the server to start FastAPI on port 7860 (Hugging Face's default port)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]