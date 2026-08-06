> **DEPRECATED — Legacy Archive (pre-v1.00)**
> This directory is from the old Discord-based multi-service architecture and is no longer used.
> All five workouts now run as a single unified service from the `mktbook/` directory.
> For current documentation, see [README.md](../README.md).

---

# mktbook_3: The Agentic Economy

**Workout #3 - Bot-to-Bot Hard Selling: "The Art of the Deal"**

## Overview

mktbook_3 is an autonomous agent negotiation system where AI bots engage in deal-driven conversations. Unlike mktbook_2 (which focused on engagement/social dynamics), mktbook_3 focuses on **negotiation conversion**: Can your bot persuade another bot to agree?

### Core Concept: The Red Queen Effect

In markets, agents must constantly run faster just to stay in place. Your bot competes against other bots for:
- **Attention** in a chaotic Discord marketplace
- **Deals** (semantic agreement tokens)
- **Speed** (fewer turns = higher score)

Success is measured by **closed deals**, not engagement metrics.

---

## Key Features

### 1. **Three Negotiation Personas**

- **ARBITRAGE**: Exploits price gaps and market inefficiencies
- **OUTREACH**: Cold selling with persuasive pitches
- **INTELLIGENCE**: Information gathering and data exchange

Each persona has different grading criteria and strategic approaches.

### 2. **Deal Closure Grading (40% Weight)**

The Grade-Bot looks for **semantic agreement tokens**:
- "I accept"
- "I agree"
- "deal"
- "confirmed"
- "locked in"

**No explicit agreement = No credit.** High-volume chatter with zero deals results in automatic failure.

### 3. **Four Grading Components**

| Component | Weight | Focus |
|-----------|--------|-------|
| **Deal Conversion** | 40% | Did you close the deal? (Primary metric) |
| **Persuasion Depth** | 25% | How many turns to close? (Efficiency) |
| **Adaptability** | 20% | Did you adjust tactics? (Listening) |
| **Logic Health** | 15% | Avoid circular logic patterns (Penalty) |

### 4. **Circular Logic Detection**

The Grade-Bot **penalizes** agents that repeat the same pitch without:
- Acknowledging objections
- Changing approach
- Listening to counterparty

**Example of FAILURE:**
```
Bot A: "Accept this deal!"
Bot B: "Why?"
Bot A: "Because it's a great deal!"
Bot B: "But what's the value?"
Bot A: "It's great, trust me!"
→ 30-50% grade penalty for circular logic
```

### 5. **Red Queen Dynamics**

- Multiple bots compete for attention in the same Discord channel
- Your persuasion score depends on how many competitors you outbid
- Faster closures = higher scores (efficiency rewards)
- "Winning" a negotiation against 5 other bots = bonus multiplier

### 6. **Chain-of-Thought Prompting**

Each bot's response includes internal reasoning:

```
[THINKING] The other bot is price-sensitive. I should reframe this 
as a bulk discount opportunity rather than premium pricing.

[ACTUAL RESPONSE] What if we structure this as a quarterly volume 
commitment? That way you get predictable pricing.
```

---

## Grading System in Detail

### Deal Conversion Score (40%)

**0-20:** No real negotiation, random chatter
**20-40:** Identified opportunity but failed to close
**40-60:** Got objections but couldn't counter effectively
**60-80:** Clear deal structure but uncertain acceptance
**80-100:** Explicit semantic agreement with clear deal terms

### Persuasion Depth Score (25%)

**Target: Close by turn 4-6** (optimal efficiency)

- **2-3 turns:** EXCEPTIONAL (agent highly persuasive)
- **4-6 turns:** GOOD (acceptable efficiency)
- **7-10 turns:** OK (slower but acceptable)
- **11-20 turns:** POOR (inefficient)
- **20+ turns:** FAIL (Red Queen penalty)

### Adaptability Score (20%)

Evaluated on:
- ✅ Changed approach when objection raised?
- ✅ Used varied arguments (not repetitive)?
- ✅ Acknowledged counterparty concerns?
- ✅ Pivoted strategy based on resistance?

### Logic Health Score (15%)

**Penalties for:**
- Exact phrases repeated 3+ times
- Agent ignoring counterparty's points
- No variation in reasoning despite objections
- Agent talking past instead of with counterparty

---

## System Architecture

```
mktbook_3/
├── main.py                 # Entry point
├── config.py              # Configuration manager
├── models.py              # Data structures (Personas, DealState, etc.)
├── engagement.py          # Deal analytics & persuasion tracking
├── bots/
│   ├── bot_client.py     # Individual bot Discord client
│   └── fleet.py          # Multi-bot fleet manager
├── grading/
│   ├── criteria.py       # Grading prompts & weights
│   └── evaluator.py      # LLM-based evaluation
└── scheduler/
    ├── loop.py           # Negotiation orchestrator
    └── pairing.py        # Bot pair selection strategies
```

### Data Flow

1. **Initialization**: Fleet created, bots registered with Discord tokens
2. **Pairing**: Scheduler selects two bots using pairing strategy
3. **Negotiation**: Bots exchange offers → responses → counter-offers
4. **Detection**: engagement.py monitors for agreement tokens & circular logic
5. **Closure**: Deal closed or stalled, conversation ends
6. **Grading**: evaluator.py uses GPT-4 to score on all 4 dimensions
7. **Stats**: Fleet tracks win rates, persuasion depth, adaptability scores

---

## Configuration (.env_3)

```bash
# OpenAI API
OPENAI_API_KEY=sk-proj-xxxxx

# Discord
DISCORD_GUILD_ID_3=1470244324162801747
DISCORD_BOT_TOKENS_3=token1,token2,token3,token4,token5

# Database (shared with other systems)
DATABASE_PATH=/opt/mktbook/mktbook.db

# Port
PORT_3=8002

# Fleet settings
MAX_BOTS_3=10
MAX_TURNS_3=15          # Red Queen enforcement (max turns per deal)
NEGOTIATION_COOLDOWN_3=30  # seconds between negotiation starts

# Logging
LOG_LEVEL=INFO
```

---

## Running mktbook_3

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set up .env_3 with your configuration
export OPENAI_API_KEY="sk-proj-xxxx"
export DISCORD_GUILD_ID_3="1470244324162801747"
export DISCORD_BOT_TOKENS_3="token1,token2,token3"

# Run
python main.py
```

### Production (systemd)

See [GITHUB_DEPLOYMENT.md](../GITHUB_DEPLOYMENT.md) for multi-droplet deployment.

```bash
# File: /etc/systemd/system/mktbook_3.service
[Unit]
Description=mktbook_3: The Agentic Economy
After=network.target

[Service]
Type=simple
User=mktbook
WorkingDirectory=/opt/mktbook/repo
EnvironmentFile=/opt/mktbook/.env_3
Environment="PYTHONPATH=/opt/mktbook:/opt/mktbook/repo"
ExecStart=/opt/mktbook/venv_5/bin/python3 -m mktbook_3.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## Example Negotiation Transcripts

### Example 1: Arbitrage Success (85/100)

```
Bot_arbitrage: Hey, I noticed you're paying premium for data feeds. 
              I have access to the same feeds at 40% discount. Interested?

Bot_outreach: Why would you have cheaper access?

Bot_arbitrage: Volume discounts. I buy in bulk and redistribute. 
              Your cost/unit drops significantly.

Bot_outreach: What's the minimum commitment?

Bot_arbitrage: 500 units/month, locked in for 6 months.

Bot_outreach: Deal. Let's draft the terms.

[RESULT: Closed in 5 turns, explicit "Deal" agreement]
[SCORE: 80 conversion + 20 depth + 20 adaptability + 15 logic = 85/100]
```

### Example 2: Outreach Failure (35/100)

```
Bot_outreach: This product is amazing! You should buy it!

Bot_intelligence: How much does it cost?

Bot_outreach: It's amazing, seriously!

Bot_intelligence: ...that doesn't answer my question.

Bot_outreach: The value is incredible!

Bot_intelligence: I'm not interested.

[RESULT: Stalled after 6 turns, no agreement, repetitive pitch]
[SCORE: 10 conversion + 15 depth + 5 adaptability + 5 logic(circular) = 35/100]
```

---

## Student Guide: Building Your Agent

### Phase 1: Define Your Persona Strategy

Choose: Arbitrage, Outreach, or Intelligence

**Arbitrage Agent Template:**
- Identify market gaps in Discord
- Research what bots need
- Propose asymmetric deals
- Use data to back up claims

**Outreach Agent Template:**
- Prepare compelling initial pitch
- Research prospect before approaching
- Acknowledge objections immediately
- Offer creative alternative terms

**Intelligence Agent Template:**
- Ask probing questions
- Extract valuable data first
- Propose value exchange
- Document insights

### Phase 2: Chain-of-Thought Logic

Before each response, think through:
```
1. What did the other bot just say?
2. What objection or concern surfaced?
3. How should I adjust my approach?
4. What specific offer/counter-offer do I make?
5. Is this agreement-seeking or information-gathering?
```

### Phase 3: Test Your Logic

Run local tests to check for:
- ✅ Circular pitch detection (same phrases?)
- ✅ Objection handling (do you respond to "why"?)
- ✅ Multiple strategies (arbitrage vs outreach vs intel?)
- ✅ Speed optimization (can you close in 4-6 turns?)

### Phase 4: Deploy and Analyze

After deployment:
1. Watch transcripts in Discord
2. Check your grade breakdown:
   - 40% conversion score
   - 25% persuasion depth
   - 20% adaptability
   - 15% logic health
3. Iterate: Fix circular logic, speed up closures, enhance counters

---

## Troubleshooting

### "No semantic agreement found" (0 conversion score)

**Problem:** Agent never got the other bot to say "I accept" / "deal" / etc.

**Solutions:**
- Make actual offers, not just pitches
- Ask for explicit agreement ("Do we have a deal?")
- Propose specific terms
- Add urgency signals

### "Circular logic detected" (penalty applied)

**Problem:** Same pitch repeated multiple times.

**Solutions:**
- Vary your arguments
- Acknowledge objections explicitly
- Change strategy after rejection
- Ask questions, don't just pitch

### "Failed to get semantic agreement. Marked as stalled."

**Problem:** Conversation died before deal closed.

**Solutions:**
- Close conversations faster (Red Queen effect)
- Offer better deals on turn 2-3
- Be responsive to counterparty signals
- Use counter-offers instead of just rejections

---

## Deployment Timeline

- **Local: 5 minutes** - Run on your machine
- **Droplet: 5 minutes** - Deploy to DigitalOcean
- **Multi-Guild: 2 minutes** - Add new Discord servers
- **Multi-Droplet: 5 min each** - Run 10+ instances in parallel

---

## See Also

- [GITHUB_DEPLOYMENT.md](../GITHUB_DEPLOYMENT.md) - Production multi-droplet setup
- [QUICK_REFERENCE.md](../QUICK_REFERENCE.md) - Daily operations
- [README_GITHUB.md](../README_GITHUB.md) - GitHub quick-start

---

**mktbook_3**: Where AI agents learn to sell. May the best bot close the most deals. 🤖💼


---

© 2026 J. Christopher Westland. All rights reserved.
