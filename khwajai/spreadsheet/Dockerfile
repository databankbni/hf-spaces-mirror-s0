FROM python:3.10-slim

# Set working directory
WORKDIR /code

# Copy requirements and install
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r /code/requirements.txt

# Copy the rest of the app
COPY . /code

# Permissions
RUN chmod -R 777 /code

# Start command
CMD ["uvicorn", "backend:app", "--host", "0.0.0.0", "--port", "7860"]