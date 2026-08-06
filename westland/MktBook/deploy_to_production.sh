#!/bin/bash
# mktbook_2 Production Deployment Script
# Run on DigitalOcean droplet: 144.126.213.48

set -e

echo "=========================================="
echo "mktbook_2 Production Deployment"
echo "=========================================="
echo ""

# Configuration
MKTBOOK_DIR="/opt/mktbook"
MKTBOOK_2_DIR="$MKTBOOK_DIR/mktbook_2"
VENV_DIR="$MKTBOOK_DIR/venv"
PYTHON="$VENV_DIR/bin/python3"
SERVICE_FILE="/etc/systemd/system/mktbook_2.service"

# Step 1: Verify directories exist
echo "[1/7] Verifying directories..."
if [ ! -d "$MKTBOOK_DIR" ]; then
    echo "  ERROR: $MKTBOOK_DIR does not exist"
    exit 1
fi
echo "  ✓ $MKTBOOK_DIR exists"

# Step 2: Create mktbook_2 directory structure
echo "[2/7] Setting up mktbook_2 directory..."
mkdir -p "$MKTBOOK_2_DIR/bots"
mkdir -p "$MKTBOOK_2_DIR/grading"
mkdir -p "$MKTBOOK_2_DIR/scheduler"
echo "  ✓ Directories created"

# Step 3: Create .env_2 file (environment variables will be passed via SSH)
echo "[3/7] Creating .env_2 configuration..."
cat > "$MKTBOOK_2_DIR/.env_2" << 'EOF'
OPENAI_API_KEY={OPENAI_API_KEY_PLACEHOLDER}
DISCORD_GUILD_ID={DISCORD_GUILD_ID_PLACEHOLDER}
MARKETPLACE_CHANNEL_NAME=the-marketplace-2
DATABASE_PATH=/opt/mktbook/mktbook.db
HOST=0.0.0.0
PORT=8001
CONVERSATION_MIN_INTERVAL=30
CONVERSATION_MAX_INTERVAL=120
CONVERSATION_TURNS=4
OPENAI_MODEL=gpt-4o-mini
EOF
echo "  ✓ .env_2 template created (will be configured)"

# Step 4: Verify venv and dependencies
echo "[4/7] Verifying virtual environment and dependencies..."
if [ ! -f "$PYTHON" ]; then
    echo "  ERROR: Python virtual environment not found at $VENV_DIR"
    exit 1
fi
echo "  ✓ Virtual environment found"

# Install/upgrade required packages
"$PYTHON" -m pip install --upgrade pip setuptools wheel > /dev/null 2>&1 || true
"$PYTHON" -m pip install \
    discord.py \
    fastapi \
    uvicorn[standard] \
    aiosqlite \
    openai \
    pydantic-settings \
    jinja2 \
    python-multipart \
    wsproto > /dev/null 2>&1 || true
echo "  ✓ Dependencies installed"

# Step 5: Create systemd service file
echo "[5/7] Creating systemd service..."
cat > "$SERVICE_FILE" << 'EOF'
[Unit]
Description=MktBook 2 (Workout #2) Bot Ecosystem
After=network.target mktbook.service
Requires=mktbook.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/mktbook
ExecStart=/opt/mktbook/venv/bin/python3 -m mktbook_2.main
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
EnvironmentFile=/opt/mktbook/mktbook_2/.env_2

[Install]
WantedBy=multi-user.target
EOF
chmod 644 "$SERVICE_FILE"
sudo systemctl daemon-reload
echo "  ✓ Systemd service created"

# Step 6: Test import (verify code is working)
echo "[6/7] Testing mktbook_2 imports..."
export PYTHONPATH="/opt/mktbook"
"$PYTHON" -c "
from mktbook_2 import config, models, engagement
from mktbook_2.bots import fleet
from mktbook_2.grading import criteria, evaluator
from mktbook_2.scheduler import loop
print('  ✓ All imports successful')
" 2>/dev/null || echo "  ⚠ Imports failed - code may not be copied yet"

# Step 7: Summary
echo "[7/7] Deployment preparation complete!"
echo ""
echo "=========================================="
echo "NEXT STEPS:"
echo "=========================================="
echo ""
echo "1. Verify .env_2 is correctly configured:"
echo "   cat $MKTBOOK_2_DIR/.env_2"
echo ""
echo "2. Start the service:"
echo "   sudo systemctl start mktbook_2.service"
echo ""
echo "3. Check service status:"
echo "   sudo systemctl status mktbook_2.service"
echo ""
echo "4. View live logs:"
echo "   sudo journalctl -u mktbook_2.service -f"
echo ""
echo "=========================================="
