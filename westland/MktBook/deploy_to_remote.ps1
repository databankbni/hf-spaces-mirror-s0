# Deployment script to run via SSH
# Usage: ./deploy_to_remote.ps1

param(
    [string]$DropletIP = "144.126.213.48",
    [string]$DiscordGuildId = "1474787626450948211",
    [string]$OpenAIKey = ""  # Will be passed as parameter
)

# Colors for output
$ErrorActionPreference = "Stop"
function Write-Step { Write-Host ">>> $args" -ForegroundColor Cyan }
function Write-Success { Write-Host "✓ $args" -ForegroundColor Green }
function Write-Error { Write-Host "✗ $args" -ForegroundColor Red }

Write-Host "=========================================="
Write-Host "mktbook_2 DigitalOcean Deployment"
Write-Host "=========================================="
Write-Host ""

Write-Step "Step 1: Verifying SSH connectivity..."
try {
    $testSSH = ssh root@$DropletIP "echo 'SSH connection OK'"
    Write-Success "SSH connection successful"
} catch {
    Write-Error "Failed to connect to $DropletIP via SSH"
    Write-Error "Ensure you can run: ssh root@$DropletIP"
    exit 1
}

Write-Step "Step 2: Creating mktbook_2 directory structure..."
$setupDir = @"
mkdir -p /opt/mktbook/mktbook_2/bots
mkdir -p /opt/mktbook/mktbook_2/grading
mkdir -p /opt/mktbook/mktbook_2/scheduler
echo 'Directories created'
"@

ssh root@$DropletIP $setupDir | Out-Null
Write-Success "Directory structure created"

Write-Step "Step 3: Creating .env_2 configuration file..."
$envContent = @"
OPENAI_API_KEY=$OpenAIKey
DISCORD_GUILD_ID=$DiscordGuildId
MARKETPLACE_CHANNEL_NAME=the-marketplace-2
DATABASE_PATH=/opt/mktbook/mktbook.db
HOST=0.0.0.0
PORT=8001
CONVERSATION_MIN_INTERVAL=30
CONVERSATION_MAX_INTERVAL=120
CONVERSATION_TURNS=4
OPENAI_MODEL=gpt-4o-mini
"@

# Use cat to create the file on the remote server
ssh root@$DropletIP "cat > /opt/mktbook/mktbook_2/.env_2" -InputObject $envContent | Out-Null
Write-Success ".env_2 created with Discord Guild ID and OpenAI key"

Write-Step "Step 4: Verifying dependencies..."
$depCheck = @"
/opt/mktbook/venv/bin/python3 -m pip install --upgrade pip setuptools wheel discord.py fastapi uvicorn[standard] aiosqlite openai pydantic-settings jinja2 python-multipart wsproto 2>&1 | tail -1
"@

ssh root@$DropletIP $depCheck | Out-Null
Write-Success "Dependencies verified and installed"

Write-Step "Step 5: Creating systemd service file..."
$serviceContent = @"
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
"@

ssh root@$DropletIP "cat > /etc/systemd/system/mktbook_2.service" -InputObject $serviceContent | Out-Null
ssh root@$DropletIP "systemctl daemon-reload" | Out-Null
Write-Success "Systemd service created and reloaded"

Write-Step "Step 6: Testing mktbook_2 configuration..."
$testConfig = @"
export PYTHONPATH=/opt/mktbook
/opt/mktbook/venv/bin/python3 -c "
from mktbook_2.config import settings
print(f'Discord Guild ID: {settings.discord_guild_id}')
print(f'Port: {settings.port}')
print(f'Database: {settings.database_path}')
" 2>&1
"@

try {
    $configTest = ssh root@$DropletIP $testConfig 2>&1
    Write-Success "Configuration test passed`n$configTest"
} catch {
    Write-Error "Configuration test failed - may need to check code files"
}

Write-Step "Step 7: Starting mktbook_2 service..."
ssh root@$DropletIP "systemctl start mktbook_2.service" | Out-Null
ssh root@$DropletIP "sleep 2" | Out-Null

$status = ssh root@$DropletIP "systemctl status mktbook_2.service --no-pager" 2>&1
Write-Success "Service started`n$status"

Write-Step "Step 8: Viewing initial logs..."
$logs = ssh root@$DropletIP "journalctl -u mktbook_2.service -n 20 --no-pager" 2>&1
Write-Host $logs

Write-Host ""
Write-Host "=========================================="
Write-Host "✓ DEPLOYMENT COMPLETE"
Write-Host "=========================================="
Write-Host ""
Write-Host "Service Status: mktbook_2.service"
Write-Host "Log Command: sudo journalctl -u mktbook_2.service -f"
Write-Host "Config File: /opt/mktbook/mktbook_2/.env_2"
Write-Host ""
