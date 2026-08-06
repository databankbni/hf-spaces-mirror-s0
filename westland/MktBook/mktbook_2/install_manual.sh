#!/bin/bash
# mktbook_2 Manual Installer for CI/CD Pipelines
# Usage: bash install_manual.sh \
#   --discord-guild-id 1474787626450948211 \
#   --openai-key sk-proj-xxx \
#   --port 8001

set -e

# Default values
PORT=8001
MKTBOOK_DIR="/opt/mktbook"
MKTBOOK_2_DIR="$MKTBOOK_DIR/mktbook_2"
VENV_DIR="$MKTBOOK_DIR/venv"
PYTHON="$VENV_DIR/bin/python3"
SERVICE_FILE="/etc/systemd/system/mktbook_2.service"
CHANNEL_NAME="the-marketplace-2"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --discord-guild-id)
            DISCORD_GUILD_ID="$2"
            shift 2
            ;;
        --openai-key)
            OPENAI_API_KEY="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --channel-name)
            CHANNEL_NAME="$2"
            shift 2
            ;;
        --mktbook-dir)
            MKTBOOK_DIR="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate required arguments
if [ -z "$DISCORD_GUILD_ID" ]; then
    echo -e "${RED}Error: --discord-guild-id is required${NC}"
    exit 1
fi

if [ -z "$OPENAI_API_KEY" ]; then
    echo -e "${RED}Error: --openai-key is required${NC}"
    exit 1
fi

# Update derived paths
MKTBOOK_2_DIR="$MKTBOOK_DIR/mktbook_2"
VENV_DIR="$MKTBOOK_DIR/venv"
PYTHON="$VENV_DIR/bin/python3"

echo -e "${YELLOW}mktbook_2 Manual Installation${NC}"
echo "================================="
echo "Mktbook Dir: $MKTBOOK_DIR"
echo "Guild ID: $DISCORD_GUILD_ID"
echo "Port: $PORT"
echo "Channel: $CHANNEL_NAME"
echo ""

# Check prerequisites
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}Must run as root${NC}"
    exit 1
fi

if [ ! -d "$MKTBOOK_DIR" ]; then
    echo -e "${RED}$MKTBOOK_DIR not found${NC}"
    exit 1
fi

if [ ! -f "$PYTHON" ]; then
    echo -e "${RED}Python venv not found at $PYTHON${NC}"
    exit 1
fi

echo -e "${GREEN}[1/5] Installing dependencies...${NC}"
"$PYTHON" -m pip install --upgrade pip > /dev/null 2>&1
"$PYTHON" -m pip install \
    discord.py fastapi uvicorn[standard] aiosqlite openai \
    pydantic-settings jinja2 python-multipart wsproto > /dev/null 2>&1
echo -e "${GREEN}✓ Dependencies installed${NC}"

echo -e "${GREEN}[2/5] Creating .env_2...${NC}"
cat > "$MKTBOOK_2_DIR/.env_2" << ENVEOF
OPENAI_API_KEY=$OPENAI_API_KEY
DISCORD_GUILD_ID=$DISCORD_GUILD_ID
MARKETPLACE_CHANNEL_NAME=$CHANNEL_NAME
DATABASE_PATH=/opt/mktbook/mktbook.db
HOST=0.0.0.0
PORT=$PORT
CONVERSATION_MIN_INTERVAL=30
CONVERSATION_MAX_INTERVAL=120
CONVERSATION_TURNS=4
OPENAI_MODEL=gpt-4o-mini
ENVEOF
chmod 600 "$MKTBOOK_2_DIR/.env_2"
echo -e "${GREEN}✓ .env_2 created${NC}"

echo -e "${GREEN}[3/5] Creating systemd service...${NC}"
cat > "$SERVICE_FILE" << SVCEOF
[Unit]
Description=MktBook 2 (Workout #2) Bot Ecosystem
After=network.target mktbook.service
Requires=mktbook.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/mktbook
Environment="PYTHONPATH=/opt/mktbook:/opt/mktbook/repo"
ExecStart=$PYTHON -m mktbook_2.main
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
EnvironmentFile=$MKTBOOK_2_DIR/.env_2

[Install]
WantedBy=multi-user.target
SVCEOF
chmod 644 "$SERVICE_FILE"
echo -e "${GREEN}✓ Service file created${NC}"

echo -e "${GREEN}[4/5] Starting service...${NC}"
systemctl daemon-reload
systemctl start mktbook_2.service
sleep 2
echo -e "${GREEN}✓ Service started${NC}"

echo -e "${GREEN}[5/5] Verifying installation...${NC}"
if systemctl is-active --quiet mktbook_2.service; then
    echo -e "${GREEN}✓ Service is RUNNING${NC}"
    echo ""
    echo -e "${GREEN}Installation complete!${NC}"
    exit 0
else
    echo -e "${RED}✗ Service failed to start${NC}"
    journalctl -u mktbook_2.service -n 20
    exit 1
fi
