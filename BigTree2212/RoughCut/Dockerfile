FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl unzip \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces (Docker SDK) runs the container as a non-root user.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# bgutil-pot: PO-Token provider for yt-dlp (Rust rewrite -- single static
# binary, no Node/Deno runtime needed). YouTube now requires a valid PO
# token for most player-client requests, and Hugging Face Spaces' outbound
# IP range gets flagged as datacenter traffic far more aggressively than a
# residential IP -- without a real token, extraction just hangs/fails
# ("Sign in to confirm you're not a bot") regardless of which yt-dlp player
# client is selected. start.sh runs this as a background sidecar bound to
# 127.0.0.1 only -- it's never reached from outside the container, yt-dlp
# calls it over loopback via the youtubepot-bgutilhttp extractor-args (see
# downloader.py).
RUN mkdir -p $HOME/.local/bin \
    && curl -fsSL -o $HOME/.local/bin/bgutil-pot \
       https://github.com/jim60105/bgutil-ytdlp-pot-provider-rs/releases/latest/download/bgutil-pot-linux-x86_64 \
    && chmod +x $HOME/.local/bin/bgutil-pot

WORKDIR $HOME/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .

RUN mkdir -p data/silence_cutter/uploads data/silence_cutter/outputs \
             data/transcript/uploads data/transcript/outputs \
             data/video_downloader/downloads

ENV PORT=7860 \
    WHISPER_MODEL_SIZE=medium \
    WHISPER_DEVICE=cpu \
    WHISPER_COMPUTE_TYPE=int8 \
    WHISPER_LANGUAGE=id

# Hugging Face Spaces (Docker SDK) expects the app on port 7860
EXPOSE 7860

RUN chmod +x start.sh
CMD ["./start.sh"]
