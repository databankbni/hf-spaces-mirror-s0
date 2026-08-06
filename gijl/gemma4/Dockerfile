# syntax=docker/dockerfile:1.4
FROM ghcr.io/ggml-org/llama.cpp:full

WORKDIR /app

RUN apt update && apt install -y python3 python3-pip python3-venv
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install -U pip huggingface_hub hf_transfer
ENV HF_HUB_ENABLE_HF_TRANSFER=1

RUN cat <<'EOF' > /app/download_model.py
from huggingface_hub import hf_hub_download
from concurrent.futures import ThreadPoolExecutor

repo = "gijl/gemma-4-E4B-it-GGUF"
files = ["gemma-4-E4B-it-BF16.gguf", "mmproj-BF16.gguf"]

def download(f):
    hf_hub_download(repo_id=repo, filename=f, local_dir="/app")

with ThreadPoolExecutor(max_workers=2) as ex:
    list(ex.map(download, files))
EOF
RUN python3 /app/download_model.py

CMD ["--server", \
     "-m", "/app/gemma-4-E4B-it-BF16.gguf", \
     "--mmproj", "/app/mmproj-BF16.gguf", \
     "--host", "0.0.0.0", \
     "--port", "7860", \
     "-t", "2", \
     "--cache-type-k", "q8_0", \
     "--cache-type-v", "iq4_nl", \
     "-c", "64800", \
     "-n", "50912"]