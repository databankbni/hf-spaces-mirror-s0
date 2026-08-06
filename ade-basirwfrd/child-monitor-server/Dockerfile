# Hugging Face Spaces health-check mengharapkan port 7860.
# Fly/Railway: override via env PORT (lihat fly.toml PORT=8080).
FROM node:20-slim

WORKDIR /app

RUN mkdir -p /data

COPY backend/package*.json ./
RUN npm install --omit=dev

COPY backend/ .

ENV PORT=7860
EXPOSE 7860

CMD ["node", "index.js"]
