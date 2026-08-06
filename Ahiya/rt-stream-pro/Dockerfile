FROM node:18-slim

# Install FFmpeg and SSL certificates for secure HTTPS video URLs
RUN apt-get update && apt-get install -y ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 7860

CMD ["node", "server.js"]
