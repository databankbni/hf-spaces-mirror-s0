# 1. Base Image: Node.js 20 (LTS)
FROM node:20-slim

# 2. Install System Dependencies
# Git is needed to clone the repo. Python, Make, and G++ are required by 'node-gyp' 
# to compile the SQLite3 database driver that WebStreamrMBG uses for caching.
RUN apt-get update && apt-get install -y git python3 make g++ && rm -rf /var/lib/apt/lists/*

# 3. Clone the WebStreamrMBG Repository
WORKDIR /app
RUN git clone https://github.com/newman2x/WebStreamrMBG.git .

# 4. Install Dependencies & Build
RUN npm install
RUN npm run build --if-present

# 5. Hugging Face Permissions Fix
# Hugging Face runs containers as user 1000. We create a data folder for the cache 
# and grant universal read/write access to prevent permission crashes.
RUN mkdir -p /app/data && chmod -R 777 /app

# 6. Environment Variables
ENV PORT=7860
ENV CACHE_DIR=/app/data

# IMPORTANT: You must replace this with a real TMDB token in your Space Secrets
ENV TMDB_ACCESS_TOKEN="9cc4c06822e95c201ce0ff3a0fbb20f6"

EXPOSE 7860

# 7. Revert to Hugging Face's required Standard User
USER 1000

# 8. Start the application
CMD ["npm", "start"]
