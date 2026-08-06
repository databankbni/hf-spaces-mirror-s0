#!/usr/bin/env bash
# ============================================================
# MktBook — Push code updates to Digital Ocean droplet
# Run from your LOCAL machine:
#   bash push.sh
#
# Prerequisites: SSH access to the droplet as root
# ============================================================
set -euo pipefail

DROPLET_IP="144.126.213.48"
REMOTE_USER="root"
REPO_DIR="/opt/mktbook/repo"

echo "=== Deploying MktBook to $DROPLET_IP ==="
echo ""

# Pull latest from GitHub, install deps, restart
ssh "$REMOTE_USER@$DROPLET_IP" "\
    cd $REPO_DIR && \
    git pull origin master && \
    /opt/mktbook/venv/bin/pip install -r $REPO_DIR/mktbook/requirements.txt -q && \
    systemctl restart mktbook"

echo ""
echo "=== Deploy complete ==="
echo "Dashboard: http://$DROPLET_IP"
echo "Logs:      ssh $REMOTE_USER@$DROPLET_IP journalctl -u mktbook -f"
