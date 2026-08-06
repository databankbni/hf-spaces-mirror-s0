FROM node:20-slim

# Install system dependencies required for Chromium/Puppeteer
RUN apt-get update && apt-get install -y \
    chromium \
    fonts-ipafont-gothic \
    fonts-wqy-zenhei \
    fonts-thai-tlwg \
    fonts-kacst \
    fonts-freefont-ttf \
    libxss1 \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Set up Hugging Face required environment variables
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

# Rename the existing 'node' user (UID 1000) to 'user'
RUN usermod -l user node && \
    groupmod -n user node && \
    usermod -d /home/user -m user

WORKDIR /home/user/app

# Copy ALL uploaded files (including package.json and index.js) at once
COPY --chown=user:user . .

# Install dependencies now that package.json is guaranteed to be there
RUN npm install

# Switch to the non-root user for security
USER user

# Expose Hugging Face default port
EXPOSE 7860

CMD ["node", "index.js"]