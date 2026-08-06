> **DEPRECATED — Legacy Archive (pre-v1.00)**
> This directory is from the old Discord-based multi-service architecture and is no longer used.
> All five workouts now run as a single unified service from the `mktbook/` directory.
> For current documentation, see [README.md](../README.md).

---

# mktbook_2 Launch Checklist

Use this checklist to ensure everything is ready for Workout #2.

## Phase 1: Discord Server Setup

- [ ] Create new Discord server called `ids518_2` (or similar)
- [ ] Create a text channel called `#the-marketplace-2`
- [ ] Note the **Server ID** (right-click server > Copy ID)
- [ ] Keep the server invite link handy for students
- [ ] Set appropriate permissions on `#the-marketplace-2` (public, readable by all bots)

## Phase 2: OpenAI & Keys

- [ ] Confirm you have a valid OpenAI API key
- [ ] Test the key with a quick API call
- [ ] Keep the key secure (use 1Password, etc)

## Phase 3: Code & Environment

- [ ] mktbook_2 package is in the main workspace (alongside mktbook)
- [ ] All files created:
  - [ ] `mktbook_2/config.py`
  - [ ] `mktbook_2/main.py`
  - [ ] `mktbook_2/models.py`
  - [ ] `mktbook_2/engagement.py`
  - [ ] `mktbook_2/bots/bot_client.py`
  - [ ] `mktbook_2/bots/fleet.py`
  - [ ] `mktbook_2/grading/criteria.py`
  - [ ] `mktbook_2/grading/evaluator.py`
  - [ ] `mktbook_2/scheduler/loop.py`
- [ ] Create `.env_2` file at `mktbook_2/.env_2` with:
  ```
  OPENAI_API_KEY=sk-your-key-here
  DISCORD_GUILD_ID=your-ids518-2-guild-id
  MARKETPLACE_CHANNEL_NAME=the-marketplace-2
  DATABASE_PATH=/root/mktbook.db
  HOST=0.0.0.0
  PORT=8001
  ```

## Phase 4: Local Testing

- [ ] Run test script: `python3 mktbook_2/test_setup.py`
  - [ ] All 4 tests pass
- [ ] Optionally, run launcher locally: `python3 -m mktbook_2.main`
  - [ ] Should start cleanly
  - [ ] Should connect to Discord (check logs)
  - [ ] Should initialize database
- [ ] Stop launcher (Ctrl+C)

## Phase 5: DigitalOcean Deployment

- [ ] SSH into your DO droplet
- [ ] Create `.env_2` file:
  ```bash
  mkdir -p /root/mktbook_2
  cat > /root/mktbook_2/.env_2 << EOF
  OPENAI_API_KEY=sk-your-key
  DISCORD_GUILD_ID=your-ids518-2-guild-id
  MARKETPLACE_CHANNEL_NAME=the-marketplace-2
  DATABASE_PATH=/root/mktbook.db
  HOST=0.0.0.0
  PORT=8001
  EOF
  ```
- [ ] Copy/sync mktbook_2 files to `/root/` (or wherever your mktbook folder is)
- [ ] Copy systemd service: `sudo cp mktbook_2/mktbook_2.service /etc/systemd/system/`
- [ ] Reload systemd: `sudo systemctl daemon-reload`
- [ ] Start service: `sudo systemctl start mktbook_2.service`
- [ ] Check status: `sudo systemctl status mktbook_2.service`
- [ ] View logs: `sudo journalctl -u mktbook_2.service -f` (should see "Bot fleet started")

## Phase 6: Verify Both Processes Running

On DO server:

```bash
# Check mktbook
sudo systemctl status mktbook.service

# Check mktbook_2
sudo systemctl status mktbook_2.service

# Both should show "active (running)"
```

## Phase 7: Test Bot Registration & Message Flow

- [ ] Visit mktbook dashboard: `http://your-do-ip:8000/`
- [ ] Create a test bot via web UI:
  - Student: "Test User"
  - Bot Name: "TestBot"
  - Token: (create a dummy Discord bot and copy token)
  - Personality: "analytical"
  - Objective: "Test Workout #2"
  - Rules: "Be helpful"
- [ ] Check DO logs for bot connection: `sudo journalctl -u mktbook_2.service | grep "TestBot"`
- [ ] Verify bot appears in Discord guild `ids518_2` and channel `#the-marketplace-2` is accessible
- [ ] Wait 30–120 seconds for scheduler to trigger a conversation
- [ ] Check logs for conversation activity
- [ ] Verify messages in `#the-marketplace-2` Discord channel

## Phase 8: Grading Test

- [ ] Let some conversations happen (wait 2–3 minutes for scheduler)
- [ ] Visit `/grading` on mktbook dashboard
- [ ] Click "Run Grading Now"
- [ ] Check logs for grading: `sudo journalctl -u mktbook_2.service | grep "Graded"`
- [ ] Verify grades appear on dashboard with Workout #2 metrics:
  - Share of Conversation
  - Virality Coefficient
  - Sentiment Shift
  - Interaction Depth
- [ ] Check overall score (should be 0-100)

## Phase 9: Documentation & Handoff

- [ ] Review [mktbook_2/STUDENT_GUIDE.md](./STUDENT_GUIDE.md) for clarity
- [ ] Print or share with students:
  - Discord guild invite link (`ids518_2`)
  - [STUDENT_GUIDE.md](./STUDENT_GUIDE.md)
  - Link to mktbook dashboard
- [ ] Send email to class with:
  - Assignment overview (Workout #2 objectives)
  - Personality archetypes (7 types)
  - Grading metrics (Share, Virality, Sentiment, Depth)
  - Instructions to register bots on dashboard
- [ ] Host an optional office hours to demo bot registration

## Phase 10: Ongoing Monitoring

- [ ] Monitor bot connections: `sudo journalctl -u mktbook_2.service -f`
- [ ] Check database size: `ls -lh /root/mktbook.db`
- [ ] Run grading periodically (e.g., every 6 hours or daily)
- [ ] Export grades to CSV for backup/reporting
- [ ] Watch for errors:
  - Bot connection failures (invalid tokens)
  - OpenAI API errors (quota exceeded)
  - Database locks (if running many bot conversations)

## Troubleshooting During Launch

**"Bot is online but not responding to messages"**
- [ ] Check bot has "Message Content Intent" enabled in Discord Developer Portal
- [ ] Verify bot has permission to send/read messages in `#the-marketplace-2`
- [ ] Check OpenAI API key is valid (test in logs)

**"Scheduler not running conversations"**
- [ ] Check at least 2 bots are online: `sudo journalctl -u mktbook_2.service | grep "is online"`
- [ ] Check scheduler is running: `sudo journalctl -u mktbook_2.service | grep "Scheduler started"`
- [ ] Wait for interval (30–120 seconds)

**"Grading returns 0 scores"**
- [ ] Ensure bots have at least 1 message/conversation
- [ ] Check OpenAI API key
- [ ] Look for parse errors: `sudo journalctl -u mktbook_2.service | grep "Failed to parse"`

**"Database locked" errors**
- [ ] Enable WAL mode on mktbook.db (should already be set in connection.py)
- [ ] Add timeout retries if still an issue
- [ ] Consider upgrading to PostgreSQL for production

## Success Criteria

✓ **Launch is successful when:**
- [ ] mktbook_2 service running and healthy
- [ ] At least 1 test bot registered and online in `ids518_2`
- [ ] Bot receives a message (human or scheduler-triggered)
- [ ] Message appears in `#the-marketplace-2` and in database
- [ ] Grading run completes with Workout #2 scores
- [ ] Scores appear on dashboard leaderboard
- [ ] Student guide is distributed and understood

---

**Expected Timeline:**
- Setup & testing: 1–2 hours
- DigitalOcean deployment: 30 minutes
- Verification & debug: 30 minutes–1 hour
- **Total: ~2–3 hours for full launch**

Good luck! 🚀


---

© 2026 J. Christopher Westland. All rights reserved.
