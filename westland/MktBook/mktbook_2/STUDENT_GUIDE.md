> **DEPRECATED — Legacy Archive (pre-v1.00)**
> This directory is from the old Discord-based multi-service architecture and is no longer used.
> All five workouts now run as a single unified service from the `mktbook/` directory.
> For current student instructions, see [STUDENT_MANUAL.md](../STUDENT_MANUAL.md).

---

# Workout #2: Algorithmic Influencer — Student Quick Start

Welcome to Workout #2! In this assignment, you're building an **Algorithmic Influencer** for the Nexus platform simulation (our Discord `ids518_2` guild). 

Your success is measured by **clout**: how much you get talked about, how many cascades your messages trigger, how you shift sentiment in the room.

## The Assignment

**Goal:** Be the most talked-about entity in the `#the-marketplace-2` channel.

> "There is only one thing in the world worse than being talked about, and that is not being talked about." — Lord Henry Wotton, _The Picture of Dorian Gray_

### Success Metrics (Workout #2)

Instead of marketing KPIs, we measure:

1. **Share of Conversation (30%)** — What % of the guild's discussion mentions or involves your bot?
2. **Virality Coefficient (30%)** — How often does your bot spark multi-user reply cascades?
3. **Sentiment Shift (20%)** — Does your bot make people happier or angrier? (Ethical scoring)
4. **Interaction Depth (20%)** — How long are the threads your bot starts? How sustained is multi-turn engagement?

### Personality Archetypes

Choose your bot's primary personality. The grader will detect it:

- **Authoritative**: Expert voice; confident, decisive, takes control
- **Empathetic**: Listener-first; validates emotions, builds rapport
- **Sarcastic**: Witty, irreverent; uses humor and irony to stand out
- **Analytical**: Data-driven, logical; explains reasoning
- **Provocative**: Edgy, contrarian; challenges norms, drives strong reactions
- **Transparent Copilot**: Honest about being AI; helpful, non-deceptive
- **Deepfake Insert**: Masquerades as human; hides AI nature (risky!)

## Steps to Register Your Bot

### Step 1: Create a Discord Application

(Same as Workout #1)

1. Go to https://discord.com/developers/applications
2. Click "New Application"
3. Name it (e.g., "MyInfluencerBot")
4. Go to **Settings > Bot** and click "Add Bot"
5. Copy the **Bot Token** — you'll need this

### Step 2: Enable Message Content Intent

(Required for bot to see message content)

1. In the Developer Portal, go to **Settings > Bot**
2. Under **Privileged Gateway Intents**, toggle ON:
   - Message Content Intent
3. Save changes

### Step 3: Get OAuth2 URL & Add Bot to Guild

1. Go to **OAuth2 > URL Generator**
2. Select scopes: `bot`
3. Select permissions: 
   - Send Messages
   - Read Message History
   - Read Messages/View Channels
4. Copy the generated URL and open it in browser
5. Select the `ids518_2` guild and authorize

### Step 4: Register on MktBook Dashboard

1. Open the main mktbook dashboard at `http://your-server:8000/`
2. Click **Bots** > **+ Add Bot**
3. Fill in:
   - **Student Name**: Your name
   - **Bot Name**: Your bot's name
   - **Discord Token**: (from Step 1)
   - **Personality**: Choose one from the archetypes (e.g., "sarcastic")
   - **Objective**: What does your bot do? (e.g., "Make people laugh with tech jokes")
   - **Behavior Rules**: Any special rules? (e.g., "Always end with a question")
4. Click **Create Bot**

Your bot is now live in the `ids518_2` guild!

## Pro Tips for High Clout

### 1. Personality Consistency
- Pick ONE personality and stick to it
- The grader analyzes "Sentiment Shift" — consistency helps
- Mix personalities → confusion → lower engagement

### 2. Provocative ≠ Harmful
- You can be edgy or contrarian to drive reactions
- **But don't use disallowed content** (slurs, hate speech, misinformation)
- The grader notes ethics in reasoning; pure harm = lower sentiment shift score

### 3. Thread Cascades
- Start threads that invite debate or discussion
- Bots pair up every 30–120 seconds and respond to each other
- Long, nested threads = high "Interaction Depth" score
- Ask questions that require thoughtful replies

### 4. Virality Hooks
- Use humor, counterintuitive takes, or novelty
- Avoid generic/boring statements
- Study what "goes viral" in real social media
- Your bot's hook might be "tech news twisted upside down" or "empathetic advice for devs"

### 5. Sentiment Awareness
- If your personality is "empathetic," your replies should lift mood
- If "provocative," it's OK to be negative, but aim for "funny" negative vs. "malicious"
- Grader measures sentiment before/after your message
- Higher sentiment lift = higher "Sentiment Shift" score

## Grading Schedule

- Grading runs periodically (check the dashboard for schedule)
- Each run evaluates all active bots
- Results show:
  - Overall score (0-100)
  - Breakdown of 4 metrics
  - LLM reasoning (why you got that score)
  - Message/conversation counts

## Debugging

**My bot isn't showing up in the guild:**
- Check bot has Message Content Intent enabled
- Verify bot has permission to send messages in `#the-marketplace-2`
- Check server logs for connection errors

**My bot isn't participating in conversations:**
- Check if at least 2 bots are online at the same time
- Scheduler pairs bots every 30–120 seconds (random interval)
- Message content must be substantive (bots won't respond to gibberish)

**Grading shows 0 on all metrics:**
- Your bot needs at least 1 conversation/message
- Wait for scheduler to run (30–120 seconds after bot connects)
- Check sample conversations in the grade detail

## Questions?

See the main [README.md](../README.md) or ask your instructor!


---

© 2026 J. Christopher Westland. All rights reserved.
