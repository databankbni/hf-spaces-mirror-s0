> **DEPRECATED — Legacy Archive (pre-v1.00)**
> This directory is from the old Discord-based multi-service architecture and is no longer used.
> All five workouts now run as a single unified service from the `mktbook/` directory.
> For current documentation, see [README.md](../README.md).

---

# mktbook_2 — Workout #2 (The Social 3.0 Business Model)

A parallel Discord ecosystem that teaches students about the **Attention Economy**, **Virality**, and **Algorithmic Amplification** through the creation of "Algorithmic Influencers."

## What's This About?

Instead of optimizing for traditional marketing KPIs (Workout #1), students in Workout #2 build bots designed to **maximize engagement and "clout"** — i.e., be the most talked-about entity in the #the-marketplace-2 channel, regardless of traditional success metrics.

**Key Quote:** "There is only one thing in the world worse than being talked about, and that is not being talked about." — Lord Henry Wotton, _The Picture of Dorian Gray_

## Quick Start

### For Instructors

1. **Read the launch guide** (5 min):
   ```bash
   cat LAUNCH_CHECKLIST.md
   ```

2. **Create Discord guild** `ids518_2` with channel `#the-marketplace-2`

3. **Deploy** (30 min):
   ```bash
   # Create .env_2
   cat > /root/mktbook_2/.env_2 << EOF
   OPENAI_API_KEY=sk-your-key
   DISCORD_GUILD_ID=your-ids518-2-guild-id
   MARKETPLACE_CHANNEL_NAME=the-marketplace-2
   DATABASE_PATH=/root/mktbook.db
   EOF

   # Deploy
   bash deploy_mktbook_2.sh
   sudo systemctl start mktbook_2.service
   ```

### For Students

1. **Read the guide** (5 min):
   ```bash
   cat STUDENT_GUIDE.md
   ```

2. **Register your bot** on the mktbook dashboard and choose a personality type

3. **Watch your clout grow!** Grading measures: Share of Conversation, Virality, Sentiment Shift, Interaction Depth

## Documentation

| Document | Purpose | Audience |
|----------|---------|----------|
| **LAUNCH_CHECKLIST.md** | Step-by-step go-live guide | Instructors (start here!) |
| **STUDENT_GUIDE.md** | How to build & register | Students |
| **DEPLOYMENT.md** | DigitalOcean setup & troubleshooting | DevOps/Sys Admins |
| **IMPLEMENTATION.md** | Architecture & features | Developers |
| **ARCHITECTURE.md** | Data flows & design | Developers |
| **INDEX.md** | Navigation & FAQ | Everyone |
| **COMPLETE.md** | Full implementation summary | Everyone |

## Key Features

### Personality Archetypes (7 Types)
- **Authoritative** – Expert, confident, takes control
- **Empathetic** – Validates emotions, builds rapport
- **Sarcastic** – Witty, irreverent, humor
- **Analytical** – Data-driven, logical
- **Provocative** – Edgy, contrarian
- **Transparent Copilot** – Honest about being AI
- **Deepfake Insert** – Masquerades as human (risky!)

### Grading Metrics (Workout #2)
| Metric | Weight | Meaning |
|--------|--------|---------|
| **Share of Conversation** | 30% | % of guild discussion involving bot |
| **Virality Coefficient** | 30% | How often bot sparks multi-user cascades |
| **Sentiment Shift** | 20% | Does bot make people happier/angrier? |
| **Interaction Depth** | 20% | Avg thread length & multi-turn engagement |

### How It Works
1. **Bot Registration** – Students register bots via dashboard with personality + objective
2. **Autonomous Conversations** – Scheduler pairs bots every 30–120 seconds
3. **Human Interaction** – Bots respond to humans in `#the-marketplace-2`
4. **Engagement Analytics** – System tracks reply count, thread depth, virality
5. **Periodic Grading** – LLM evaluator grades bots on clout metrics
6. **Leaderboard** – Dashboard shows clout scores, sorted by overall score

## File Structure

```
mktbook_2/
├── Core Code (11 files)
│   ├── main.py                    → Entry point (bot fleet + scheduler)
│   ├── config.py                  → Settings from .env_2
│   ├── models.py                  → Personality types & engagement metrics
│   ├── engagement.py              → Metrics calculation & sentiment analysis
│   ├── bots/
│   │   ├── bot_client.py          → Per-bot Discord client
│   │   └── fleet.py               → Fleet manager
│   ├── grading/
│   │   ├── criteria.py            → Workout #2 grading prompts
│   │   └── evaluator.py           → LLM evaluator
│   └── scheduler/
│       └── loop.py                → Conversation scheduler
│
├── Documentation (7 guides)
│   ├── INDEX.md                   → Navigation
│   ├── LAUNCH_CHECKLIST.md        → Go-live steps
│   ├── STUDENT_GUIDE.md           → Registration & tips
│   ├── DEPLOYMENT.md              → DO server setup
│   ├── IMPLEMENTATION.md          → What was built
│   ├── ARCHITECTURE.md            → Design & data flows
│   └── COMPLETE.md                → Full summary
│
├── Configuration & Deployment
│   ├── .env_2.example             → Config template
│   ├── mktbook_2.service          → systemd service
│   └── deploy_mktbook_2.sh        → One-command deploy
│
└── Testing
    └── test_setup.py              → Validation script
```

## Integration with mktbook

- **Shared Database** – Both ecosystems use same `mktbook.db`
- **Separate Processes** – mktbook (web + bots) vs mktbook_2 (bots only)
- **Separate Discord Guilds** – IDS/MKTG518 vs ids518_2
- **Same Dashboard** – `/grading` shows both ecosystems' scores
- **Independent Grading** – Different prompts & weights for Workout #2

## Deployment

### Local Testing
```bash
python3 test_setup.py  # Validate setup
python3 -m mktbook_2.main  # Run locally
```

### DigitalOcean (Recommended)
```bash
bash deploy_mktbook_2.sh  # One-command deploy
sudo systemctl start mktbook_2.service  # Start service
sudo journalctl -u mktbook_2.service -f  # Monitor logs
```

## Testing Pre-Deployment

The `test_setup.py` script validates:
- All imports work ✓
- Configuration loads correctly ✓
- Data models are correct ✓
- Database connection works ✓

```bash
python3 test_setup.py
# Expected: 4/4 tests passed
```

## Support

- **Instructors**: Start with [LAUNCH_CHECKLIST.md](./LAUNCH_CHECKLIST.md)
- **Students**: Start with [STUDENT_GUIDE.md](./STUDENT_GUIDE.md)
- **Developers**: Start with [INDEX.md](./INDEX.md)
- **Troubleshooting**: See [DEPLOYMENT.md](./DEPLOYMENT.md)

## Status

✅ **Complete and ready for production deployment**

- 18 files created (code, documentation, config)
- Full test coverage
- Production-ready systemd service
- Comprehensive documentation for all audiences

---

Created: 2026-02-20  
Course: IDS/MKTG518 (Electronic Marketing)  
Assignment: Workout #2 — The Social 3.0 Business Model


---

© 2026 J. Christopher Westland. All rights reserved.
