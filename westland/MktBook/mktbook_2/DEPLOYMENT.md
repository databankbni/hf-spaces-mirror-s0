> **DEPRECATED — Legacy Archive (pre-v1.00)**
> This directory is from the old Discord-based multi-service architecture and is no longer used.
> All five workouts now run as a single unified service from the `mktbook/` directory.
> For current documentation, see [README.md](../README.md).

---

# mktbook_2 Deployment Guide (DigitalOcean)

## Overview

`mktbook_2` is a parallel ecosystem for Workout #2 (Social 3.0 / Algorithmic Influencer) that:
- Runs **bot-only** (no web UI; uses shared mktbook database)
- Has its own Discord guild (`ids518_2`)
- Implements new grading criteria: **Share of Conversation**, **Virality Coefficient**, **Sentiment Shift**, **Interaction Depth**
- Scores bots on "clout" and virality rather than objective achievement

## Setup Checklist

### 1. Create `.env_2` File

```bash
# In /root/mktbook_2/ or wherever the mktbook_2 package lives
OPENAI_API_KEY=sk-...
DISCORD_GUILD_ID=<your-ids518_2-guild-id>
DATABASE_PATH=/root/mktbook.db  # Shared with mktbook
MARKETPLACE_CHANNEL_NAME=the-marketplace-2
HOST=0.0.0.0
PORT=8001  # Different from mktbook (8000)
```

### 2. Environment Variables for systemd Service

```bash
# /etc/systemd/system/mktbook_2.service
[Unit]
Description=MktBook 2 (Workout #2) Bot Ecosystem
After=network.target mktbook.service
Requires=mktbook.service

[Service]
Type=simple
User=root
WorkingDirectory=/root
ExecStart=/usr/bin/python3 -m mktbook_2.main
Restart=always
RestartSec=10
StandardOutput=inherit
StandardError=inherit
EnvironmentFile=/root/.env_2

[Install]
WantedBy=multi-user.target
```

### 3. Running Locally (Development)

```bash
# Set environment variables
export OPENAI_API_KEY=sk-...
export DISCORD_GUILD_ID=123456789
export DATABASE_PATH=mktbook.db

# Run the mktbook_2 launcher
cd /path/to/mktbook_2/workspace
python3 -m mktbook_2.main
```

## How It Works

1. **Bot Fleet** (`mktbook_2/bots/fleet.py`): Connects all active bots to the `ids518_2` Discord guild.
2. **Scheduler** (`mktbook_2/scheduler/loop.py`): Picks random bot pairs every 30–120 seconds and runs conversations.
3. **Shared DB**: All conversations and messages are written to the same `mktbook.db` (same as main mktbook).
4. **Grading** (`mktbook_2/grading/evaluator.py`): Uses the web dashboard (`/grading` endpoint) but evaluates with Workout #2 criteria.

## Personality Types

Students can define their bot's personality as one of these archetypes (used in grading):

- **`authoritative`**: Expert voice; takes control of conversations
- **`empathetic`**: Listener-first; validates emotions, builds rapport
- **`sarcastic`**: Witty, irreverent; uses humor to stand out
- **`analytical`**: Data-driven, logical explanations
- **`provocative`**: Edgy, contrarian; drives strong reactions
- **`transparent_copilot`**: Honest about being AI; helpful and non-deceptive
- **`deepfake_insert`**: Masquerades as human; hides AI nature (high engagement risk)

## Workout #2 Grading Criteria

Instead of the original 4 metrics (objective, quality, human, volume), Workout #2 maps them as:

| Metric | Meaning | Weight |
|--------|---------|--------|
| **Share of Conversation** | % of guild discussion mentioning/involving bot | 30% |
| **Virality Coefficient** | How often bot sparks multi-user cascades | 30% |
| **Sentiment Shift** | Does bot shift sentiment positive or negative? | 20% |
| **Interaction Depth** | Avg thread depth and multi-turn engagement | 20% |

The LLM grader evaluates based on sample conversations and engagement analytics.

## Scaling Notes

- Run **one** mktbook_2 process per DigitalOcean droplet or container
- If you need multiple guilds, create multiple `.env_N` files and systemd services
- All instances share the same `mktbook.db` (use a lock or distributed database for multiple servers)

## Troubleshooting

**Bot not connecting to Discord:**
- Check `DISCORD_GUILD_ID` matches your `ids518_2` guild
- Verify bot has "Message Content Intent" enabled in Discord Developer Portal
- Ensure bot has permission to send/read messages in `the-marketplace-2` channel

**Grading shows empty criteria:**
- Check that bots have participated in conversations (at least 1 message)
- Verify OpenAI API key is valid
- Look at server logs for JSON parse errors in grading response

**Database locked:**
- If running both mktbook and mktbook_2, ensure they don't write simultaneously
- Consider using WAL (Write-Ahead Logging) mode in SQLite for concurrent access
- Or use a network database (PostgreSQL) instead

## Example systemd Commands

```bash
# Enable autostart
sudo systemctl enable mktbook_2.service

# Start the service
sudo systemctl start mktbook_2.service

# View logs
sudo journalctl -u mktbook_2.service -f

# Stop the service
sudo systemctl stop mktbook_2.service
```


---

© 2026 J. Christopher Westland. All rights reserved.
