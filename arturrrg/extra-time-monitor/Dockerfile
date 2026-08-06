FROM node:24-bookworm-slim

WORKDIR /app

ENV NODE_ENV=production \
    PORT=7860 \
    DATA_DIR=/data \
    ONEWIN_MAX_ODDS_PAGES=0 \
    ONEWIN_MAX_FULL_TRACKER_PAGES=0 \
    ONEWIN_ENABLE_BROWSER_SEARCH=0

COPY package*.json ./
RUN npm install --omit=dev

COPY . .

# Audit log + calibrated model live here. Mount HF persistent storage at /data so
# collected labels and tuned coefficients survive restarts (else it is ephemeral).
RUN mkdir -p /data

EXPOSE 7860

CMD ["npm", "start"]
