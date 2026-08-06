FROM ghcr.io/berriai/litellm:main-latest
COPY config.yaml /app/config.yaml
ENV MALLOC_ARENA_MAX=2
CMD ["--config", "/app/config.yaml", "--port", "7860"]
