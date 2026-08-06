# ─────────────────────────────────────────────────────────────
# Smart Restaurant AI Waiter Service — production image
# Works on Hugging Face Spaces (Docker SDK, app_port 7860),
# and any other container host (Railway, Render, Fly, VPS...).
#
# HF Spaces setup:
#   1. Create a Space → SDK: Docker → push this repo.
#   2. Space Settings → Variables & secrets:
#        GROQ_API_WAITER   = gsk_...           (secret)
#        BACKEND_BASE_URL  = https://your-django-backend.com
#   3. The chat UI is served at  https://<space>.hf.space/ui
# ─────────────────────────────────────────────────────────────

# ---- Build stage ----
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY tsconfig.json ./
COPY src ./src
RUN npm run build && npm prune --omit=dev

# ---- Runtime stage ----
FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=7860
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY public ./public
COPY package.json ./

# Run as non-root (required by HF Spaces best practice)
RUN addgroup -S app && adduser -S app -G app \
    && mkdir -p /app/data && chown -R app:app /app/data
USER app

EXPOSE 7860
CMD ["node", "dist/server.js"]
