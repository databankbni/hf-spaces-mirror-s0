FROM node:22-slim

WORKDIR /app

# Copy package files and install dependencies
COPY package*.json ./
RUN npm install --production

# Copy application files
COPY . .

# Expose the HF Spaces port
EXPOSE 7860

# Set Node environment variables
ENV NODE_ENV=production
ENV PORT=7860

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD node -e "require('http').get('http://localhost:7860/health', (res) => { if (res.statusCode === 200) process.exit(0); else process.exit(1); })"

# Run the app
CMD ["node", "app.js"]
