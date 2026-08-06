FROM python:3.11-slim

# HuggingFace Spaces run containers as user ID 1000
RUN useradd -m -u 1000 user

WORKDIR /home/user/app

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV HF_HOME=/home/user/app/.cache/huggingface
ENV SENTENCE_TRANSFORMERS_HOME=/home/user/app/.cache/sentence-transformers
ENV TRANSFORMERS_CACHE=/home/user/app/.cache/huggingface

# Bake retrieval models into the image so HF_HUB_OFFLINE=1 works at runtime.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('BAAI/bge-small-en-v1.5'); CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2'); print('Models cached OK')" \
    && chown -R user:user /home/user/app/.cache

COPY --chown=user . .

# Fetch ChromaDB index from GitHub (HF git rejects binary blobs in its own repo)
RUN mkdir -p data/index \
    && git clone --depth 1 --branch main https://github.com/janvip08/spotify-review-engine.git /tmp/index-src \
    && cp -r /tmp/index-src/data/index/. data/index/ \
    && rm -rf /tmp/index-src \
    && chown -R user:user data/index \
    && test -s data/index/chroma/chroma.sqlite3

USER user

ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1
ENV HF_HUB_DISABLE_SSL_VERIFICATION=1
EXPOSE 7860
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "7860"]
