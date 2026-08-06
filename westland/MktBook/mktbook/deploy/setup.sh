#!/usr/bin/env bash
# ============================================================
# MktBook — Digital Ocean Droplet Setup Script
# Run this ONCE on a fresh Ubuntu 24.04 droplet as root:
#   bash /opt/mktbook/repo/mktbook/deploy/setup.sh
#
# Expects the git repo cloned to /opt/mktbook/repo/
# Droplet IP: 144.126.213.48
# ============================================================
set -euo pipefail

DROPLET_IP="144.126.213.48"
APP_DIR="/opt/mktbook"
REPO_DIR="$APP_DIR/repo"
CODE_DIR="$REPO_DIR/mktbook"
APP_USER="mktbook"

echo "=== MktBook Droplet Setup ==="
echo "Droplet IP: $DROPLET_IP"
echo ""

# --------------------------------------------------
# 1. System packages
# --------------------------------------------------
echo "[1/7] Updating system and installing packages..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq python3 python3-venv python3-pip nginx ufw git

# --------------------------------------------------
# 2. Firewall
# --------------------------------------------------
echo "[2/7] Configuring firewall (SSH + HTTP only)..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP (Nginx)
ufw --force enable

# --------------------------------------------------
# 3. Create application user
# --------------------------------------------------
echo "[3/7] Creating mktbook system user..."
if ! id "$APP_USER" &>/dev/null; then
    useradd --system --create-home --home-dir "$APP_DIR" --shell /bin/bash "$APP_USER"
else
    echo "  User $APP_USER already exists, skipping."
fi

# --------------------------------------------------
# 4. Create directory structure
# --------------------------------------------------
echo "[4/7] Setting up application directory..."
mkdir -p "$APP_DIR"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# --------------------------------------------------
# 5. Python virtual environment
# --------------------------------------------------
echo "[5/7] Creating Python virtual environment..."
if [ ! -d "$APP_DIR/venv" ]; then
    python3 -m venv "$APP_DIR/venv"
    chown -R "$APP_USER:$APP_USER" "$APP_DIR/venv"
fi

# Install dependencies if requirements.txt exists
if [ -f "$CODE_DIR/requirements.txt" ]; then
    "$APP_DIR/venv/bin/pip" install --upgrade pip -q
    "$APP_DIR/venv/bin/pip" install -r "$CODE_DIR/requirements.txt" -q
    echo "  Dependencies installed."
else
    echo "  WARNING: requirements.txt not found at $CODE_DIR/requirements.txt"
    echo "  Make sure the repo is cloned to $REPO_DIR"
    exit 1
fi

# --------------------------------------------------
# 6. Nginx configuration
# --------------------------------------------------
echo "[6/7] Configuring Nginx reverse proxy..."
cp "$CODE_DIR/deploy/nginx-mktbook.conf" /etc/nginx/sites-available/mktbook
ln -sf /etc/nginx/sites-available/mktbook /etc/nginx/sites-enabled/mktbook
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx
systemctl enable nginx

# --------------------------------------------------
# 7. Systemd service
# --------------------------------------------------
echo "[7/7] Installing systemd service..."
cp "$CODE_DIR/deploy/mktbook.service" /etc/systemd/system/mktbook.service
systemctl daemon-reload
systemctl enable mktbook.service

# --------------------------------------------------
# .env check
# --------------------------------------------------
if [ ! -f "$CODE_DIR/.env" ]; then
    echo ""
    echo "============================================"
    echo "  IMPORTANT: .env file not found!"
    echo "  Copy .env.example and fill in your keys:"
    echo ""
    echo "    cp $CODE_DIR/.env.example $CODE_DIR/.env"
    echo "    nano $CODE_DIR/.env"
    echo ""
    echo "  Then fix ownership and start the service:"
    echo "    chown -R $APP_USER:$APP_USER $APP_DIR"
    echo "    systemctl start mktbook"
    echo "============================================"
else
    chown -R "$APP_USER:$APP_USER" "$APP_DIR"
    echo ""
    echo "Starting MktBook service..."
    systemctl restart mktbook
    echo ""
    echo "============================================"
    echo "  MktBook is running!"
    echo "  Dashboard: http://$DROPLET_IP"
    echo ""
    echo "  Useful commands:"
    echo "    systemctl status mktbook     # Check status"
    echo "    journalctl -u mktbook -f     # View live logs"
    echo "    systemctl restart mktbook    # Restart"
    echo "    systemctl stop mktbook       # Stop"
    echo "============================================"
fi
