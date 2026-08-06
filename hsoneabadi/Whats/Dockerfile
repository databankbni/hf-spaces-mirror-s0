FROM node:22-slim

RUN corepack enable && corepack prepare pnpm@10 --activate

RUN apt-get update && apt-get install -y \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    fonts-liberation fonts-noto-core fonts-noto-cjk xdg-utils \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package.json pnpm-lock.yaml postinstall.js ./
RUN pnpm install --no-frozen-lockfile

COPY . .

EXPOSE 7860

CMD ["node", "index.js"]