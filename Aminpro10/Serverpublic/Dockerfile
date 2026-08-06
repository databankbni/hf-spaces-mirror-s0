# =========================================================
# Dockerfile — AI Image Hub (CPU-only, HF Spaces free tier)
# =========================================================
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/code/.cache/huggingface \
    TORCH_HOME=/code/.cache/torch \
    U2NET_HOME=/code/.cache/rembg \
    XDG_CACHE_HOME=/code/.cache

WORKDIR /code

# ---------------------------------------------------------
# System dependencies
#   - git: needed by pip to fetch a couple of GitHub-based deps
#   - wget/curl: needed to fetch model weights at build time
#   - ffmpeg, libgl1, libglib2.0-0: required by opencv / basicsr / rembg
#   - libsndfile1: safe default for some audio/image codecs used by deps
# ---------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    wget \
    curl \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /code/requirements.txt

RUN pip install --upgrade pip

# ---------------------------------------------------------
# Install PyTorch CPU-only wheels FIRST, from the official PyTorch
# CPU index. This prevents pip from silently pulling the much larger
# CUDA build (which also fails/hangs on the free CPU Space due to
# size and irrelevant NVIDIA dependencies).
# ---------------------------------------------------------
RUN pip install --no-cache-dir \
    torch==2.3.1+cpu torchvision==0.18.1+cpu \
    --index-url https://download.pytorch.org/whl/cpu

# ---------------------------------------------------------
# Install opencv-python-headless BEFORE the rest of requirements.txt.
# basicsr (a transitive dep of realesrgan/gfpgan) lists plain
# "opencv-python" as a dependency with no version pin. If it installs
# first, pip ends up with BOTH opencv-python and opencv-python-headless
# side by side (they ship the same "cv2" module under different
# package names), which bloats the image with unneeded GUI/Qt
# libraries and risks a broken cv2 import. Installing the headless
# build first satisfies basicsr's requirement and pip skips the
# GUI variant entirely.
# ---------------------------------------------------------
RUN pip install --no-cache-dir opencv-python-headless==4.10.0.84

# ---------------------------------------------------------
# Install the rest of the Python dependencies
# ---------------------------------------------------------
RUN pip install --no-cache-dir -r /code/requirements.txt

# ---------------------------------------------------------
# Patch basicsr (used by realesrgan + gfpgan) for compatibility with
# modern torchvision. basicsr==1.4.2 is unmaintained upstream and still
# imports `functional_tensor`, which was removed in torchvision>=0.17.
# This one-line patch (rewriting the import path) is the same fix
# widely used across current Real-ESRGAN/GFPGAN Spaces on Hugging Face.
# Without it the app installs fine but crashes at runtime with:
#   ImportError: cannot import name 'rgb_to_grayscale' from
#   'torchvision.transforms.functional_tensor'
# ---------------------------------------------------------
RUN python -c "import basicsr, os; print(os.path.dirname(basicsr.__file__))" \
    && BASICSR_DIR=$(python -c "import basicsr, os; print(os.path.dirname(basicsr.__file__))") \
    && sed -i \
       "s/from torchvision.transforms.functional_tensor import rgb_to_grayscale/from torchvision.transforms.functional import rgb_to_grayscale/g" \
       "${BASICSR_DIR}/data/degradations.py" || true

# ---------------------------------------------------------
# Pre-download model weights at build time so the first user request
# doesn't time out. Cached under /code/.cache and /code/weights.
# ---------------------------------------------------------
RUN mkdir -p /code/weights

# Real-ESRGAN (general x4 photo model) + anime x4 variant
RUN wget -q -O /code/weights/RealESRGAN_x4plus.pth \
    https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth \
    && wget -q -O /code/weights/RealESRGAN_x4plus_anime_6B.pth \
    https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth

# GFPGAN (face restoration)
RUN wget -q -O /code/weights/GFPGANv1.4.pth \
    https://github.com/TencentARC/GFPGAN/releases/download/v1.3.4/GFPGANv1.4.pth

# rembg (background removal) — downloads its own u2net.onnx into
# U2NET_HOME on first run; pre-warm it here so build already has it cached.
RUN python -c "from rembg import new_session; new_session('u2net')" || true

# simple-lama-inpainting (LaMa) — pre-download the big-lama weights
RUN python -c "from simple_lama_inpainting import SimpleLama; SimpleLama()" || true

# ---------------------------------------------------------
# NOTE on SwinIR:
# SwinIR has no official PyPI package and its GitHub repo is not
# pip-installable (no valid setup.py/pyproject.toml), which is why the
# previous requirements.txt failed the build with "metadata-generation-
# failed". Its practical role here (general-purpose super-resolution /
# JPEG artifact removal) is already covered by Real-ESRGAN, which uses
# the same underlying RRDB/Swin-style architecture family, ships proper
# pip packaging, and is lighter on CPU. We recommend using
# Real-ESRGAN for this feature instead of adding SwinIR separately.
#
# NOTE on DiffBIR:
# DiffBIR is a full latent-diffusion restoration pipeline (~50 denoising
# steps per image, multi-GB checkpoints, official docs assume a CUDA
# GPU). On the free CPU tier a single image would take many minutes and
# would very likely exceed HF Spaces' request/build time and storage
# limits, and it has no pip package (git-clone + manual weights only).
# It is NOT included here. If "Pro" quality restoration is required,
# the practical CPU-friendly path is:
#   Real-ESRGAN (upscale) -> GFPGAN (face restore) -> simple-lama (inpaint)
# chained together, which this requirements.txt already supports, or
# upgrading the Space to a paid GPU tier specifically for a DiffBIR
# endpoint.
# ---------------------------------------------------------

COPY . .

EXPOSE 7860

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
