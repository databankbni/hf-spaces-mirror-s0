> **DEPRECATED — Legacy Archive (pre-v1.00)**
> This directory is from the old Discord-based multi-service architecture and is no longer used.
> All five workouts now run as a single unified service from the `mktbook/` directory.
> For current documentation, see [README.md](../README.md).

---

# mktbook_2 Quick Reference Guide

## Installation

### Fast Track (Interactive)
```bash
ssh root@<DROPLET_IP>
cd /opt && git clone https://github.com/westland/mktbook.git
bash mktbook/mktbook_2/install_from_github.sh
```

### Manual (CI/CD)
```bash
bash install_manual.sh \
  --discord-guild-id 1474787626450948211 \
  --openai-key sk-proj-xxx \
  --port 8001
```

---

## Operations

### Service Management
```bash
# Start
sudo systemctl start mktbook_2.service

# Stop
sudo systemctl stop mktbook_2.service

# Restart
sudo systemctl restart mktbook_2.service

# Status
sudo systemctl status mktbook_2.service

# Enable auto-boot
sudo systemctl enable mktbook_2.service

# Disable auto-boot
sudo systemctl disable mktbook_2.service
```

### Monitoring

### View Live Logs
```bash
sudo journalctl -u mktbook_2.service -f
```

### Last 100 Lines
```bash
sudo journalctl -u mktbook_2.service -n 100
```

### Errors Only
```bash
sudo journalctl -u mktbook_2.service -p err | head -50
```

### Resource Usage
```bash
ps aux | grep mktbook_2.main
```

---

## Configuration Management

### View Current Configuration
```bash
cat /opt/mktbook/mktbook_2/.env_2
```

### Edit Configuration
```bash
sudo nano /opt/mktbook/mktbook_2/.env_2
```

### After Editing
```bash
sudo systemctl restart mktbook_2.service
```

### Test Configuration
```bash
export PYTHONPATH=/opt/mktbook:/opt/mktbook/repo
/opt/mktbook/venv/bin/python3 mktbook_2/test_setup.py
```

---

## Advanced Operations

### Add Second Guild (Same Droplet)
```bash
# Copy environment file
cp /opt/mktbook/mktbook_2/.env_2 /opt/mktbook/mktbook_2/.env_2_guild2

# Edit with new guild ID and port
nano /opt/mktbook/mktbook_2/.env_2_guild2

# Copy service file
sudo cp /etc/systemd/system/mktbook_2.service \
        /etc/systemd/system/mktbook_2_guild2.service

# Edit service
sudo nano /etc/systemd/system/mktbook_2_guild2.service
# Change: EnvironmentFile=/opt/mktbook/mktbook_2/.env_2_guild2

# Start both
sudo systemctl daemon-reload
sudo systemctl start mktbook_2_guild2.service
```

### Check Service Dependencies
```bash
# Is main mktbook running?
sudo systemctl status mktbook.service

# Are both services active?
sudo systemctl status mktbook_2.service mktbook_2_guild2.service
```

### Database Maintenance
```bash
# Backup database
cp /opt/mktbook/mktbook.db /opt/mktbook/mktbook.db.backup.$(date +%Y%m%d)

# WAL checkpoint
sqlite3 /opt/mktbook/mktbook.db "PRAGMA wal_checkpoint(RESTART);"

# Check database size
du -h /opt/mktbook/mktbook.db*
```

---

## Troubleshooting

### Service Won't Start
```bash
# Check error
sudo journalctl -u mktbook_2.service | tail -30

# Common issues:
# 1. Port in use: Change PORT in .env_2
# 2. Module not found: Re-run install_from_github.sh
# 3. Permission denied: Ensure running as root
```

### Import Errors
```bash
# Verify PYTHONPATH
echo $PYTHONPATH

# Test imports
export PYTHONPATH=/opt/mktbook:/opt/mktbook/repo
/opt/mktbook/venv/bin/python3 -c "from mktbook_2 import main; print('OK')"
```

### Discord Connection Issues
```bash
# Check guild ID
grep DISCORD_GUILD_ID /opt/mktbook/mktbook_2/.env_2

# Verify channel exists
# Discord > Guild > Channels > #the-marketplace-2

# Restart to reconnect
sudo systemctl restart mktbook_2.service
```

### Port Conflicts
```bash
# Find what's using a port
sudo lsof -i :8001

# Kill if needed
sudo kill -9 <PID>

# Or change port in .env_2
PORT=8002
```

---

## File Locations

- **Main Code**: `/opt/mktbook/mktbook_2/`
- **Config**: `/opt/mktbook/mktbook_2/.env_2`
- **Service**: `/etc/systemd/system/mktbook_2.service`
- **Logs**: `journalctl` system
- **Database**: `/opt/mktbook/mktbook.db`
- **Python venv**: `/opt/mktbook/venv/`

---

## Useful Commands

### System Info
```bash
# Python version
python3 --version

# IP address
hostname -I

# Disk usage
df -h

# RAM usage
free -h

# Process lookup
ps aux | grep mktbook
```

### Network
```bash
# Test port
curl http://localhost:8001

# Test Discord connectivity
curl https://discord.com/api/v10/ping

# Test OpenAI connectivity
curl https://api.openai.com/v1/ping
```

### Git Operations
```bash
# Update code
cd /opt/mktbook && git pull origin main

# Check status
git status

# View recent changes
git log --oneline -10

# Switch branch
git checkout develop
```

---

## Emergency Procedures

### Hard Reset
```bash
# Stop service
sudo systemctl stop mktbook_2.service

# Restore backup config
cp /opt/mktbook/mktbook_2/.env_2 /opt/mktbook/mktbook_2/.env_2.broken
cp /opt/mktbook/mktbook_2/.env_2.example /opt/mktbook/mktbook_2/.env_2

# Re-run installer
bash /opt/mktbook/mktbook_2/install_from_github.sh
```

### Clear Recent Logs
```bash
# Rotate logs
sudo journalctl --rotate

# Vacuum old logs (>7 days)
sudo journalctl --vacuum-time=7d
```

### Force Restart Everything
```bash
sudo systemctl restart mktbook.service mktbook_2.service
sleep 5
sudo systemctl status mktbook.service mktbook_2.service
```

---

## Performance Tuning

### Increase Conversation Frequency
```bash
# Edit .env_2
CONVERSATION_MIN_INTERVAL=15
CONVERSATION_MAX_INTERVAL=60

# Restart
sudo systemctl restart mktbook_2.service
```

### Increase Conversation Depth
```bash
CONVERSATION_TURNS=8  # More back-and-forth

# Restart
sudo systemctl restart mktbook_2.service
```

### Monitor Performance
```bash
# CPU/Memory
top -p $(pgrep -f mktbook_2.main)

# Disk I/O
iostat -x 1 5

# Network connections
netstat -an | grep 8001
```

---

## Documentation Links

- **Full Deployment**: [GITHUB_DEPLOYMENT.md](GITHUB_DEPLOYMENT.md)
- **Architecture**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **Implementation**: [IMPLEMENTATION.md](IMPLEMENTATION.md)
- **Student Guide**: [STUDENT_GUIDE.md](STUDENT_GUIDE.md)
- **Launch Checklist**: [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md)

---

**Last Updated**: February 21, 2026  
**Version**: 1.0


---

© 2026 J. Christopher Westland. All rights reserved.
