FROM node:22-slim

WORKDIR /app

ENV PORT=7860

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build:app
RUN npm prune --omit=dev

ENV NODE_ENV=production

EXPOSE 7860

USER node

CMD ["npm", "run", "start"]
