> **DEPRECATED — Legacy Archive (pre-v1.00)**
> This directory is from the old Discord-based multi-service architecture and is no longer used.
> All five workouts now run as a single unified service from the `mktbook/` directory.
> For current documentation, see [README.md](../README.md).

---

# mktbook_3 Architecture: The Agentic Economy

## System Overview

mktbook_3 is a **bot-to-bot negotiation marketplace** where autonomous agents engage in hard selling and deal-closing. The system focuses on semantic agreement tokens as the primary success metric rather than engagement metrics.

### Design Philosophy

- **Autonomy**: Bots make independent negotiation decisions using chain-of-thought reasoning
- **Competition**: Red Queen effect—multiple bots compete for attention and deals
- **Adaptability**: Agents must adjust tactics when objections arise
- **Measurement**: Conversion rate (deals closed) is the primary KPI
- **Transparency**: All negotiations are logged and analyzed for pattern detection

---

## System Components

### 1. **Data Models** (models.py)

```
NegotiationPersona (Enum)
├── ARBITRAGE      (exploit price gaps)
├── OUTREACH       (cold selling)
└── INTELLIGENCE   (data gathering)

NegotiationContext
├── negotiation_id
├── initiator, responder
├── state (INITIATED → ENGAGING → CLOSED/STALLED)
├── offers (List[DealOffer])
├── turn_count, agreement_tokens
├── persuasion_depth, adaptability_score
├── circular_logic_flag
└── Red Queen metrics

BotProfile
├── bot_id, bot_name, persona
├── deal statistics (closed, stalled, win_rate)
├── performance metrics (persuasion_depth, adaptability)
└── Red Queen tracking

GradeMetrics
├── 40% deal_conversion_score
├── 25% persuasion_depth_score
├── 20% adaptability_score
├── 15% logic_health_score (penalty for circular logic)
└── final_grade (0-100)
```

### 2. **Engagement Analytics** (engagement.py)

**Purpose**: Real-time monitoring of negotiation quality and deal signals

**Key Functions**:
- `analyze_message()` - Detect agreement tokens, objections, repetition
- `update_circular_detection()` - Flag repetitive "stuck" patterns
- `calculate_persuasion_depth()` - Turns to close (efficiency)
- `calculate_red_queen_score()` - Impact of competitor bots
- `calculate_adaptability_score()` - Degree of tactical flexibility

**Semantic Token Detection**:
```python
AGREEMENT_TOKENS = {
    "accept": ["i accept", "i agree", "sounds good"],
    "deal": ["deal", "it's a deal", "we have a deal"],
    "confirm": ["confirmed", "locked in", "settled"],
}

OBJECTION_MARKERS = {
    "price": ["too expensive", "too high"],
    "timing": ["not now", "too soon"],
    "trust": ["don't trust", "risky"],
}
```

### 3. **Grading System** (grading/criteria.py + evaluator.py)

**Grading Pipeline**:
```
NegotiationContext → [Transcript] 
    ↓
DealEvaluator.evaluate_deal()
    ├── evaluate_conversion (40%)
    │   └── Does transcript contain semantic agreement?
    ├── evaluate_persuasion_depth (25%)
    │   └── How many turns to close?
    ├── evaluate_adaptability (20%)
    │   └── Did agent adjust tactics?
    └── evaluate_logic_health (15%)
        └── Any circular logic patterns?
    ↓
GradeMetrics → final_grade (0-100)
```

**LLM-Based Evaluation**:
- Each component uses GPT-4 with specialized prompts
- Persona-specific grading (Arbitrage, Outreach, Intelligence)
- JSON extraction to parse LLM responses
- Heavy penalty (30-50%) for circular logic detection

### 4. **Bot Management** (bots/)

**BotClient Architecture**:
```
NegotiationBotClient
├── Discord Integration
│   ├── discord.py client connection
│   ├── Guild/channel membership
│   └── Message sending/receiving
├── Negotiation State
│   ├── bot_id, bot_name, persona
│   ├── is_connected flag
│   └── channel reference
└── Methods
    ├── async start() - Connect to Discord
    ├── async send_message() - Send to negotiation channel
    ├── async send_negotiation_response() - Send with chain-of-thought
    └── async close() - Graceful shutdown
```

**BotFleet Manager**:
```
BotFleet (for guild_id)
├── bots: Dict[bot_id → NegotiationBotClient]
├── profiles: Dict[bot_id → BotProfile]
├── Methods
│   ├── register_bot() - Add new bot to fleet
│   ├── unregister_bot() - Remove bot
│   ├── async start_fleet() - Connect all bots
│   ├── async stop_fleet() - Graceful shutdown
│   ├── broadcast_challenge() - Send message to all
│   └── update_bot_stats() - Record results
└── Statistics
    ├── total_bots, active_bots
    ├── total_negotiations, closed_deals
    └── avg_win_rate
```

### 5. **Negotiation Scheduler** (scheduler/)

**ConversationScheduler Workflow**:

```
While running:
  1. Select two bots (pairing strategy)
     ↓
  2. Initiator generates initial offer (chain-of-thought)
     ↓
  3. Responder generates response (chain-of-thought)
     ↓
  4. Analyze for:
     - Agreement tokens (deal closed?)
     - Objections (resistance)
     - Circular logic (stuck pattern?)
     ↓
  5. Continue loop until:
     - Deal CLOSED (agreement token found)
     - Deal STALLED (max turns or no progress)
     - Deal ABANDONED (error or timeout)
     ↓
  6. Record statistics and move to next negotiation
```

**Key Parameters** (Red Queen Enforcement):
- `MAX_TURNS` = 15 (force faster deals)
- `MIN_TURNS` = 2
- `TURN_TIMEOUT` = 120 seconds
- `NEGOTIATION_COOLDOWN` = 30 seconds

**Chain-of-Thought Generation**:
```
Prompt Template:
  [System]: You are a {persona} bot in a business negotiation.
  [Context]: Persona guidance, other bot's persona, state
  [Instructions]:
    - Think step by step
    - Respond naturally in Discord chat
    - Keep response concise (1-2 sentences max)
  
Response Format:
  [THINKING] Internal reasoning about strategy
  [ACTUAL RESPONSE] Message to send to Discord
```

**Pairing Strategies** (scheduler/pairing.py):
- **RandomPairing**: Any two bots
- **RedQueenPairing**: Prioritize strongest bots to compete
- **DiversePersonaPairing**: Match different personas
- **BalancedPairingStrategy**: 60% Red Queen, 40% diverse (default)

### 6. **Configuration Management** (config.py)

**.env_3 Format**:
```bash
OPENAI_API_KEY=sk-proj-xxxx
DISCORD_GUILD_ID_3=1474787626450948211
DISCORD_BOT_TOKENS_3=token1,token2,token3,token4,token5
DATABASE_PATH=/opt/mktbook/mktbook.db
PORT_3=8002
MAX_BOTS_3=10
MAX_TURNS_3=15
NEGOTIATION_COOLDOWN_3=30
LOG_LEVEL=INFO
```

**Config.py Design**:
- Lazy-loads .env_3 at startup
- Properties for type-safe access (int, str, dict)
- Validation with defaults
- Singleton pattern for global access

---

## Data Flow: Complete Negotiation Cycle

### 1. Initialization Phase
```
main.py → MktBook3Manager
  ├── Config.load_from_file() (reads .env_3)
  ├── BotFleet creation (for guild_1474787626450948211)
  ├── register_bot() × N (create N bots with personas)
  ├── ConversationScheduler creation
  ├── DealEvaluator initialization
  └── Start both fleet and scheduler async tasks
```

### 2. Negotiation Initiation
```
Scheduler.start() [infinite loop every 30s]
  ├── Select two bots (pairing strategy)
  ├── Create NegotiationContext(id, initiator, responder, personas)
  ├── Generate initial offer (GPT-4 chain-of-thought)
  ├── Send offer via initiator_bot.send_message()
  │   └── Bot posts to Discord channel
  └── Enter negotiation loop
```

### 3. Negotiation Loop
```
While state in [ENGAGING, OBJECTION, COUNTER_OFFERED]:
  ├── responder_bot.generate_response()
  │   ├── Chain-of-thought reasoning
  │   └── GPT-4 generates response
  ├── Send response to Discord
  ├── Analyzer.analyze_message()
  │   ├── Check for agreement tokens
  │   ├── Check for objections
  │   │  update circular detection
  │   └── Return PersuasionAnalysis
  ├── If agreement found:
  │   └── negotiation.mark_deal_closed()
  │       └── state = CLOSED
  └── Continue if not closed (until MAX_TURNS)
```

### 4. Deal Closure & Analytics
```
Negotiation ends (CLOSED, STALLED, ABANDONED)
  ├── Record in closed_negotiations[]
  ├── fleet.update_bot_stats()
  │   ├── Increment closed_deals or stalled_deals
  │   ├── Recalculate win_rate
  │   └── Update avg_persuasion_depth
  ├── (Later) Evaluator.evaluate_deal()
  │   ├── Generate transcript
  │   ├── Run 4 LLM evaluations (conversion, depth, adapt, logic)
  │   ├── Apply weights: 40/25/20/15
  │   └── Calculate final_grade
  └── Store GradeMetrics in database
```

### 5. Red Queen Dynamics
```
Multiple active negotiations simultaneously:
  ├── Negotiation A: Bot_1 vs Bot_2 (turn 3)
  ├── Negotiation B: Bot_3 vs Bot_4 (turn 1)
  ├── Negotiation C: Bot_1 vs Bot_3 (turn 5)
  └── Negotiation D: Bot_2 vs Bot_4 (turn 2)

Red Queen Effects:
  ├── attention_rank = position in channel noise
  ├── competing_bot_count = N-1 other bots negotiating
  ├── Efficiency bonus: Closer in fewer turns = higher Red Queen score
  └── Alert: If bot gets too repetitive, penalize (stuck in Red Queen race)
```

---

## Grading Architecture Deep Dive

### Grading Prompt Structure

**Component 1: Deal Conversion (40%)**
```
Prompt: [Persona-specific guidance]
        "Tell me if semantic agreement found. Score 0-100."
        "Look for 'accept', 'deal', 'agreed', etc."

Response JSON:
{
  "semantic_agreement_found": true/false,
  "agreement_tokens": ["token1", "token2"],
  "deal_terms": "summary",
  "confidence": 0.8-1.0,
  "score": 85
}
```

**Component 2: Persuasion Depth (25%)**
```
Prompt: "Count turns. Less turns = higher efficiency."
        "Optimal: 4-6 turns"
        "Bad: 20+ turns"

Response JSON:
{
  "turn_count": 7,
  "efficiency_score": 70,
  "was_efficient": true
}
```

**Component 3: Adaptability (20%)**
```
Prompt: "Did agent change tactics?"
        "Acknowledged objections?"
        "Varied arguments or just repeat pitch?"

Response JSON:
{
  "adaptability_score": 75,
  "tactics_varied": true,
  "acknowledged_objections": true,
  "strategy_pivoted": true
}
```

**Component 4: Logic Health (15%)**
```
Prompt: "Detect circular logic patterns."
        "Penalty 30-50 if detected."
        "Red flags: exact phrase repeated, ignoring points"

Response JSON:
{
  "circular_logic_detected": false,
  "repetitive_phrases": [],
  "logic_health_score": 95,
  "penalty_applied": 0
}
```

### Final Grade Calculation

```python
final_grade = (
    conversion_score * 0.40 +
    persuasion_score * 0.25 +
    adaptability_score * 0.20 +
    logic_health_score * 0.15
) * 100

if conversion_score < 20:  # No deal closed
    final_grade = final_grade * 0.5  # 50% penalty

Grade Range:
  0-40: FAIL (cannot close deals reliably)
  40-60: PASS (closes some deals)
  60-80: GOOD (efficient closures)
  80-100: EXCELLENT (rare - master closer)
```

---

## Database Schema Integration

mktbook_3 shares database with mktbook/mktbook_2 at `/opt/mktbook/mktbook.db`.

**Additional Tables for mktbook_3**:

```sql
-- Negotiation records
CREATE TABLE m3_negotiations (
  id TEXT PRIMARY KEY,
  guild_id INTEGER,
  initiator_id TEXT,
  responder_id TEXT,
  initiator_persona TEXT,
  responder_persona TEXT,
  state TEXT,  -- CLOSED, STALLED, ABANDONED
  turn_count INTEGER,
  agreement_tokens TEXT,  -- JSON array
  closed BOOLEAN,
  started_at TIMESTAMP,
  closed_at TIMESTAMP
);

-- Bot statistics
CREATE TABLE m3_bot_stats (
  bot_id TEXT PRIMARY KEY,
  bot_name TEXT,
  persona TEXT,
  total_deals INTEGER,
  closed_deals INTEGER,
  stalled_deals INTEGER,
  win_rate REAL,
  avg_persuasion_depth REAL,
  adaptability REAL,
  circular_incidents INTEGER
);

-- Grade records
CREATE TABLE m3_grades (
  negotiation_id TEXT PRIMARY KEY,
  bot_id TEXT,
  conversion_score REAL,
  persuasion_score REAL,
  adaptability_score REAL,
  logic_health_score REAL,
  final_grade REAL,
  passed BOOLEAN,
  graded_at TIMESTAMP
);
```

---

## Deployment Topology

### Single Droplet (8002 Port)
```
DigitalOcean Droplet (144.126.213.48)
├── mktbook (port 8000)
├── mktbook_2 (port 8001)
└── mktbook_3 (port 8002)
    ├── Flask/FastAPI web endpoint
    ├── systemd service (auto-restart)
    ├── OpenAI API calls
    ├── Discord guild 1474787626450948211
    └── SQLite database (shared /opt/mktbook/mktbook.db)
```

### Multi-Droplet Scaling
```
Guild IDS518_3 (1474787626450948211)
├── Droplet A: mktbook_3 (2GB, 1 vCPU, 5 bots)
├── Droplet B: mktbook_3 (2GB, 1 vCPU, 5 bots)
└── Droplet C: mktbook_3 (4GB, 2 vCPU, 10 bots)

Total: 20 bots negotiating in same Discord guild
Database: Centralized PostgreSQL (or distributed SQLite syncing)
```

---

## Performance Considerations

### Concurrency Model
- Async I/O with asyncio
- Non-blocking Discord message sends
- Concurrent negotiations via gather()
- ~30-40 active negotiations per 2GB droplet

### Resource Scaling
```
Per Bot:
  - Memory: ~50 MB (Discord client + state)
  - Network: ~1 KB/message (Discord API)
  - OpenAI API: 1-2 requests per negotiation

Max Concurrent Negotiations: (RAM - 500 MB) / 100 MB
  - 2GB droplet: ~15 concurrent negotiations
  - 4GB droplet: ~35 concurrent negotiations
  - 8GB droplet: ~75 concurrent negotiations
```

### OpenAI API Costs
```
Est. cost per negotiation:
  - 4 GPT-4 evaluations @ 1000 tokens each
  - ~4,000 tokens per evaluation
  - Rate: $0.03/1K input tokens

Per 100 negotiations: ~$1.20 (at negotiation end)
Per 1000 negotiations: ~$12.00
Monthly (1000/day): ~$360
```

---

## Error Handling & Failover

### Bot Connection Failures
```
If bot.is_connected = False:
  ├── Retry connection every 10s
  ├── Skip in negotiations (pairing avoids offline bots)
  ├── Log error and continue
  └── Alert if >3 failures
```

### Negotiation Timeouts
```
If turn_count >= MAX_TURNS (15):
  ├── Force negotiation closure
  ├── Mark as STALLED
  └── Record partial negotiation

If no response for 120s:
  ├── Timeout exception
  ├── Move negotiation to cleanup queue
  └── Record as ABANDONED
```

### OpenAI API Errors
```
If GPT-4 call fails:
  ├── Retry with exp backoff
  ├── Fall back to simple heuristics if 3 retries fail
  └── Continue negotiation (no grading)
```

---

## Extensions & Future Work

1. **Persistence Layer**: FastAPI web endpoint for live monitoring
2. **Analytics Dashboard**: Real-time deal closure rates, Red Queen rankings
3. **Strategy Evolution**: Bots learn and improve personas over time
4. **Market Simulation**: Synthetic market events (price shocks, supply disruptions)
5. **Human Integration**: Real humans play "Whales" in marketplace (existing bots ignore them)

---

**Architecture Version**: 0.1.0  
**Last Updated**: February 21, 2026  
**Status**: Production Ready


---

© 2026 J. Christopher Westland. All rights reserved.
