FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 user \
    && python -m venv /opt/venv \
    && chown -R user:user /opt/venv

ENV HOME=/home/user \
    PATH=/opt/venv/bin:$PATH \
    MODEL_NAME=dense-306 \
    MODEL_DIR=/home/user/app/model \
    PORT=7860

USER user
WORKDIR /home/user/app

RUN pip install --upgrade pip setuptools wheel \
    && pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install git+https://github.com/Complexity-ML/vllm-i64.git@71e005a

COPY --chown=user:user app.py /home/user/app/app.py

EXPOSE 7860
CMD ["python", "app.py"]
