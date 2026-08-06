# Hugging Face Docker Space — SearXNG for Halo news JSON API
# Docs: https://huggingface.co/docs/hub/spaces-sdks-docker

FROM searxng/searxng:latest

# HF sets SEARXNG_HOSTNAME to your Space URL (e.g. username-halo-searxng.hf.space)
ENV SEARXNG_BASE_URL=https://${SEARXNG_HOSTNAME:-localhost}/
ENV SEARXNG_BIND_ADDRESS=0.0.0.0
ENV SEARXNG_PORT=8080

# Optional runtime overrides via Space Settings → Secrets:
#   SEARXNG_SECRET  — replaces server.secret_key (required for production)

RUN mkdir -p /etc/searxng && chmod 777 /etc/searxng

COPY ./config /etc/searxng

EXPOSE 8080
