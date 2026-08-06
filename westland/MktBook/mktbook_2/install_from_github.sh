#!/bin/bash
# mktbook_2 Interactive Installer for GitHub Deployment
# Usage: bash install_from_github.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Banner
clear
echo -e "${BLUE}"
cat << "EOF"
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║         mktbook_2: Workout #2 Bot Ecosystem              ║
║         Interactive DigitalOcean Installer               ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"
echo ""

# Configuration
MKTBOOK_DIR="/opt/mktbook"
MKTBOOK_2_DIR="$MKTBOOK_DIR/mktbook_2"
VENV_DIR="$MKTBOOK_DIR/venv"
PYTHON="$VENV_DIR/bin/python3"
SERVICE_FILE="/etc/systemd/system/mktbook_2.service"

echo -e "${YELLOW}[1/7] Checking prerequisites...${NC}"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}✗ This script must be run as root${NC}"
   echo "Please run: sudo bash install_from_github.sh"
   exit 1
fi
echo -e "${GREEN}✓ Running as root${NC}"

# Check if Python 3 installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python 3 is not installed${NC}"
    echo "Install with: apt-get update && apt-get install -y python3"
    exit 1
fi
PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo -e "${GREEN}✓ Python $PYTHON_VERSION installed${NC}"

# Check if mktbook directory exists
if [ ! -d "$MKTBOOK_DIR" ]; then
    echo -e "${RED}✗ $MKTBOOK_DIR does not exist${NC}"
    echo "Ensure main mktbook is installed first"
    exit 1
fi
echo -e "${GREEN}✓ $MKTBOOK_DIR exists${NC}"

# Check if venv exists
if [ ! -f "$PYTHON" ]; then
    echo -e "${RED}✗ Python virtual environment not found${NC}"
    echo "Run: cd $MKTBOOK_DIR && python3 -m venv venv"
    exit 1
fi
echo -e "${GREEN}✓ Virtual environment found${NC}"

echo ""
echo -e "${YELLOW}[2/7] Gathering configuration...${NC}"
echo ""

# Prompt for Discord Guild ID
echo -e "${BLUE}Discord Configuration:${NC}"
read -p "Enter Discord Guild ID for IDS518_2: " DISCORD_GUILD_ID

if [ -z "$DISCORD_GUILD_ID" ]; then
    echo -e "${RED}✗ Guild ID cannot be empty${NC}"
    exit 1
fi

if ! [[ "$DISCORD_GUILD_ID" =~ ^[0-9]+$ ]]; then
    echo -e "${RED}✗ Guild ID must be numeric${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Guild ID: $DISCORD_GUILD_ID${NC}"
echo ""

# Prompt for OpenAI API Key
echo -e "${BLUE}OpenAI Configuration:${NC}"
read -sp "Enter OpenAI API Key (sk-proj-...): " OPENAI_API_KEY
echo ""

if [ -z "$OPENAI_API_KEY" ]; then
    echo -e "${RED}✗ API Key cannot be empty${NC}"
    exit 1
fi

if [[ ! "$OPENAI_API_KEY" =~ ^sk-proj* ]]; then
    echo -e "${YELLOW}⚠ Warning: API Key should start with 'sk-proj-'${NC}"
    read -p "Continue anyway? (y/n): " CONTINUE
    if [[ ! "$CONTINUE" =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo -e "${GREEN}✓ API Key configured (***...)${NC}"
echo ""

# Prompt for Port
echo -e "${BLUE}Server Configuration:${NC}"
read -p "Enter port for mktbook_2 service (default: 8001): " PORT
PORT=${PORT:-8001}

if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1024 ] || [ "$PORT" -gt 65535 ]; then
    echo -e "${RED}✗ Port must be between 1024 and 65535${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Port: $PORT${NC}"
echo ""

# Optional: Custom channel name
read -p "Enter marketplace channel name (default: the-marketplace-2): " CHANNEL_NAME
CHANNEL_NAME=${CHANNEL_NAME:-the-marketplace-2}
echo -e "${GREEN}✓ Channel: $CHANNEL_NAME${NC}"
echo ""

echo -e "${YELLOW}[3/7] Installing/upgrading dependencies...${NC}"

# Upgrade pip
"$PYTHON" -m pip install --upgrade pip setuptools wheel > /dev/null 2>&1
echo -e "${GREEN}✓ pip upgraded${NC}"

# Install required packages
"$PYTHON" -m pip install \
    discord.py \
    fastapi \
    uvicorn[standard] \
    aiosqlite \
    openai \
    pydantic-settings \
    jinja2 \
    python-multipart \
    wsproto > /dev/null 2>&1
echo -e "${GREEN}✓ All dependencies installed${NC}"

echo ""
echo -e "${YELLOW}[4/7] Creating .env_2 configuration...${NC}"

# Create .env_2 file
cat > "$MKTBOOK_2_DIR/.env_2" << ENVEOF
# mktbook_2 Configuration
# Generated: $(date)

# Discord Configuration
DISCORD_GUILD_ID=$DISCORD_GUILD_ID
MARKETPLACE_CHANNEL_NAME=$CHANNEL_NAME

# OpenAI Configuration
OPENAI_API_KEY=$OPENAI_API_KEY
OPENAI_MODEL=gpt-4o-mini

# Database Configuration
DATABASE_PATH=/opt/mktbook/mktbook.db

# Server Configuration
HOST=0.0.0.0
PORT=$PORT

# Conversation Scheduler Configuration
CONVERSATION_MIN_INTERVAL=30
CONVERSATION_MAX_INTERVAL=120
CONVERSATION_TURNS=4
ENVEOF

# Set permissions to restrict access
chmod 600 "$MKTBOOK_2_DIR/.env_2"
echo -e "${GREEN}✓ .env_2 created${NC}"

echo ""
echo -e "${YELLOW}[5/7] Creating systemd service...${NC}"

# Create systemd service file
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
echo -e "${GREEN}✓ Systemd service created${NC}"

echo ""
echo -e "${YELLOW}[6/7] Testing configuration...${NC}"

# Test imports
export PYTHONPATH="/opt/mktbook:/opt/mktbook/repo"
if "$PYTHON" -c "
from mktbook_2.config import settings
print(f'Discord Guild: {settings.discord_guild_id}')
print(f'Port: {settings.port}')
print(f'Channel: {settings.marketplace_channel_name}')
" 2>/dev/null; then
    echo -e "${GREEN}✓ Configuration validated${NC}"
else
    echo -e "${RED}✗ Configuration test failed${NC}"
    echo "Please check .env_2 file manually"
fi

echo ""
echo -e "${YELLOW}[7/7] Starting mktbook_2 service...${NC}"

# Reload systemd
systemctl daemon-reload
echo -e "${GREEN}✓ Systemd daemon reloaded${NC}"

# Start service
systemctl start mktbook_2.service
echo -e "${GREEN}✓ Service started${NC}"

# Brief wait for startup
sleep 3

# Check status
if systemctl is-active --quiet mktbook_2.service; then
    echo -e "${GREEN}✓ Service is RUNNING${NC}"
else
    echo -e "${RED}✗ Service failed to start${NC}"
    echo "Check logs with: sudo journalctl -u mktbook_2.service -n 50"
    exit 1
fi

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}                                                            ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}          ${GREEN}✓ INSTALLATION COMPLETE!${NC}                          ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}                                                            ${BLUE}║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo "Configuration saved to: $MKTBOOK_2_DIR/.env_2"
echo "Service file: $SERVICE_FILE"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. View logs:        sudo journalctl -u mktbook_2.service -f"
echo "2. Check status:     sudo systemctl status mktbook_2.service"
echo "3. Register bots:    Visit http://$(hostname -I | awk '{print $1}'):8000"
echo "4. Enable auto-start: sudo systemctl enable mktbook_2.service"
echo ""
echo -e "${YELLOW}Documentation:${NC}"
echo "- Deployment: $MKTBOOK_2_DIR/GITHUB_DEPLOYMENT.md"
echo "- Architecture: $MKTBOOK_2_DIR/ARCHITECTURE.md"
echo "- Installation: $MKTBOOK_2_DIR/IMPLEMENTATION.md"
echo ""
