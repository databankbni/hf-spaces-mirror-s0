FROM node:20-slim

# Install Chromium and required fonts for Puppeteer
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

# Set Puppeteer environment variables to use system-installed Chromium
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    NODE_ENV=production

# Create app directory
WORKDIR /usr/src/app

# Copy package files
COPY package*.json ./

# Install production dependencies
RUN npm ci --only=production

# Copy app source code
COPY --chown=1000:1000 . .

# Ensure user 1000 recursively owns the entire work directory
RUN chown -R 1000:1000 /usr/src/app

# Expose server port
EXPOSE 3000

# Switch to non-root user for Hugging Face compatibility
USER 1000

# Start server
CMD [ "npm", "start" ]
