# Use an official lightweight Python image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies + Git tools needed for fetching your code
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libgl1 \
    libglib2.0-0 \
    git \
    git-lfs \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face requires an unprivileged user (ID 1000) for security compliance
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Set our secure internal work directory
WORKDIR $HOME/app

# Install the Hugging Face Hub CLI tool
RUN pip install --no-cache-dir huggingface_hub

# --- THE SECRET SECURE FETCH ---
# This temporarily mounts your HF_TOKEN at build time to download your code 
# without caching the credential inside the final public docker image layer.
# --- THE SECRET SECURE FETCH (UPDATED FOR NEW HF CLI) ---
# This temporarily mounts your HF_TOKEN at build time to download your code 
# using the new 'hf download' utility.
RUN --mount=type=secret,id=HF_TOKEN,mode=0444,required=true \
    hf download \
    --token=$(cat /run/secrets/HF_TOKEN) \
    --repo-type=dataset \
    salvoaics/salvowebsite \
    --local-dir .

# Install Python dependencies that were just downloaded from your private repo
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 7860 - Hugging Face requires this exact port
EXPOSE 7860

# Change into the Django project directory so gunicorn can resolve salvo_website.wsgi
WORKDIR $HOME/app/salvo_website

# Run migrations for both databases, collect static files,
# create the admin user if it doesn't exist, and start Gunicorn
CMD python manage.py migrate && \
    python manage.py migrate --database=tracker && \
    python manage.py collectstatic --noinput && \
    python -c "import os, django; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'salvo_website.settings'); django.setup(); from django.contrib.auth import get_user_model; User = get_user_model(); username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin'); password = os.environ.get('DJANGO_SUPERUSER_PASSWORD'); email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com'); (User.objects.create_superuser(username, email, password) if password and not User.objects.filter(username=username).exists() else print('Superuser already exists or password missing.'))" && \
    gunicorn --bind 0.0.0.0:7860 salvo_website.wsgi:application --workers 3 --threads 2
