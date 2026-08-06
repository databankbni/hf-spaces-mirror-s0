#!/usr/bin/env bash
# Run ON THE DROPLET after git pull to apply config changes:
#   bash /opt/mktbook/repo/mktbook/deploy/apply.sh
set -euo pipefail

REPO_DIR="/opt/mktbook/repo"
CODE_DIR="$REPO_DIR/mktbook"

echo "Copying Nginx config..."
cp "$CODE_DIR/deploy/nginx-mktbook.conf" /etc/nginx/sites-available/mktbook
nginx -t && systemctl restart nginx

echo "Copying systemd service..."
cp "$CODE_DIR/deploy/mktbook.service" /etc/systemd/system/mktbook.service
systemctl daemon-reload

echo "Installing dependencies..."
/opt/mktbook/venv/bin/pip install -r "$CODE_DIR/requirements.txt" -q

echo "Fixing ownership..."
chown -R mktbook:mktbook /opt/mktbook

echo "Restarting MktBook..."
systemctl restart mktbook

echo "Done! Dashboard: http://144.126.213.48"
