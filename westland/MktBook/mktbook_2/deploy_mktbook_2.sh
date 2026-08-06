#!/bin/bash
# Deploy mktbook_2 to DigitalOcean
# Run: bash deploy_mktbook_2.sh

set -e

echo "=== mktbook_2 Deployment Script ==="

# 1. Ensure python environment
echo "[1/5] Checking Python environment..."
python3 --version
pip3 install --upgrade pip setuptools wheel

# 2. Install dependencies (same as mktbook)
echo "[2/5] Installing dependencies..."
pip3 install \
    discord.py \
    fastapi \
    uvicorn[standard] \
    aiosqlite \
    openai \
    pydantic-settings \
    jinja2 \
    python-multipart

# 3. Create .env_2 if it doesn't exist
echo "[3/5] Setting up configuration..."
if [ ! -f "/root/mktbook_2/.env_2" ]; then
    echo "Creating /root/mktbook_2/.env_2 template..."
    mkdir -p /root/mktbook_2
    cp mktbook_2/.env_2.example /root/mktbook_2/.env_2
    echo "Please edit /root/mktbook_2/.env_2 with your Discord guild ID and OpenAI key"
    exit 1
else
    echo "Using existing /root/mktbook_2/.env_2"
fi

# 4. Install systemd service
echo "[4/5] Installing systemd service..."
sudo cp mktbook_2/mktbook_2.service /etc/systemd/system/
sudo systemctl daemon-reload
echo "Service installed. To start: sudo systemctl start mktbook_2"

# 5. Summary
echo "[5/5] Deployment complete!"
echo ""
echo "Next steps:"
echo "1. Edit /root/mktbook_2/.env_2 with your Discord guild ID and API keys"
echo "2. Ensure mktbook service is running: sudo systemctl status mktbook"
echo "3. Start mktbook_2: sudo systemctl start mktbook_2.service"
echo "4. Check logs: sudo journalctl -u mktbook_2.service -f"
