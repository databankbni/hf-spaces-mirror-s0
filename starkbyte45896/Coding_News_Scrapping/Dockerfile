FROM python:3.9

# Create user with ID 1000 to avoid permission issues in HuggingFace Spaces
RUN useradd -m -u 1000 user
USER user

ENV HOME=/home/user \
	PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Copy files and set ownership
COPY --chown=user . $HOME/app

# Install dependencies
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Start the application
CMD ["gunicorn", "-b", "0.0.0.0:7860", "app:app"]
