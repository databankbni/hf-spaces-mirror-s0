#!/bin/bash
# Deployment script for mktbook_5 to DigitalOcean droplet
# Usage: ./deploy_mktbook5.sh

set -e

DROPLET_IP="144.126.213.48"
DROPLET_USER="root"
TARGET_DIR="/opt/mktbook"
REPO_DIR="$TARGET_DIR/repo/mktbook_5"
LOG_FILE="./deployment.log"

echo "================================================"
echo "mktbook_5 Deployment to $DROPLET_IP:8004"
echo "================================================"
echo "Starting deployment at $(date)" | tee -a $LOG_FILE

# Step 1: Copy mktbook_5 to droplet
echo ""
echo "[1/5] Copying mktbook_5 to droplet..."
scp -r mktbook_5/ $DROPLET_USER@$DROPLET_IP:$TARGET_DIR/repo/ 2>&1 | tee -a $LOG_FILE
echo "✓ Files copied to $REPO_DIR"

# Step 2: Copy .env_5 to droplet
echo ""
echo "[2/5] Copying environment configuration..."
scp .env_5 $DROPLET_USER@$DROPLET_IP:$TARGET_DIR/.env_5 2>&1 | tee -a $LOG_FILE
echo "✓ Environment file configured"

# Step 3: Install dependencies on droplet
echo ""
echo "[3/5] Installing Python dependencies..."
ssh $DROPLET_USER@$DROPLET_IP "cd $REPO_DIR && pip install -r requirements.txt" 2>&1 | tee -a $LOG_FILE
echo "✓ Dependencies installed"

# Step 4: Create systemd service
echo ""
echo "[4/5] Creating systemd service for mktbook_5..."
cat > /tmp/mktbook_5.service << 'EOF'
[Unit]
Description=mktbook_5 Bayesian A/B Testing Framework
After=network.target mktbook_4.service

[Service]
Type=simple
User=mktbook
WorkingDirectory=/opt/mktbook/repo/mktbook_5
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=/opt/mktbook/.env_5
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=mktbook_5

[Install]
WantedBy=multi-user.target
EOF

scp /tmp/mktbook_5.service $DROPLET_USER@$DROPLET_IP:/etc/systemd/system/ 2>&1 | tee -a $LOG_FILE
echo "✓ Service file created"

# Step 5: Enable and start service
echo ""
echo "[5/5] Enabling and starting mktbook_5 service..."
ssh $DROPLET_USER@$DROPLET_IP "systemctl daemon-reload && systemctl enable mktbook_5 && systemctl start mktbook_5" 2>&1 | tee -a $LOG_FILE
echo "✓ Service started"

# Verify deployment
echo ""
echo "================================================"
echo "Deployment Complete - Verifying Status"
echo "================================================"

ssh $DROPLET_USER@$DROPLET_IP "systemctl status mktbook_5 --no-pager | head -15" 2>&1 | tee -a $LOG_FILE

echo ""
echo "✓ mktbook_5 deployed to $DROPLET_IP:8004"
echo "✓ Discord Guild: 1470244324162801747"
echo ""
echo "Next steps:"
echo "1. Provide Discord bot token in .env_5 on droplet:"
echo "   ssh root@$DROPLET_IP \"nano /opt/mktbook/.env_5\""
echo "2. Provide OpenAI API key in .env_5"
echo "3. Restart service: ssh root@$DROPLET_IP \"systemctl restart mktbook_5\""
echo "4. Check logs: ssh root@$DROPLET_IP \"journalctl -u mktbook_5 -f\""
echo ""
echo "Deployment logged to: $LOG_FILE"
