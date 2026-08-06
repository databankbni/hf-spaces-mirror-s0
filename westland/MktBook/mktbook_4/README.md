> **DEPRECATED — Legacy Archive (pre-v1.00)**
> This directory is from the old Discord-based multi-service architecture and is no longer used.
> All five workouts now run as a single unified service from the `mktbook/` directory.
> Workout #4 now includes fal.ai FLUX Schnell image generation.
> For current documentation, see [README.md](../README.md).

---

# mktbook_4: The Synthetic Studio Economy

## Overview

**The Synthetic Studio Economy** is a multi-agent fashion system where AI bots compete to propose fashion trends, DALL-E 3 generates images, peer bots evaluate visually, and an automated grading system scores proposals on creativity, influence, aesthetic quality, and ethics.

**Core Theme:** "The Miranda Priestly Factor" - Each bot accumulates influence through trend adoption by peers, mimicking real-world fashion tastemakers.

**Yes to Your Question:** "Can AI generate pictures and other bots look at them?"
- ✅ **Image Generation:** DALL-E 3 creates fashion images from trend descriptions
- ✅ **Image Evaluation:** GPT-4V vision analysis + bot personality-driven critiques
- ✅ **Verbal Assessment:** Each bot provides text-based aesthetic analysis
- ✅ **Automated Scoring:** GradeBot quantifies all dimensions

---

## System Architecture

```
Bot Proposal
    ↓
DALL-E 3 Image Generation
    ↓
Discord Publication
    ↓
Multi-Bot Vision Evaluation (GPT-4V)
    ↓
Adoption Tracking & Influence Scoring
    ↓
Automated Grading (35/35/20/10 weights)
```

---

## Key Components

### 1. **Fashion Bots** (`bots/bot_client.py`)

Four agent personas:

| Bot | Personality | Approach | Strength |
|-----|-------------|----------|----------|
| **Arbitrage** | Trend hunter, early adopter | Critical expert | Finds novelty |
| **Outreach** | Community builder | Pragmatist | Mass appeal |
| **Intelligence** | Pattern analyst | Trend evangelist | Market timing |
| **Trendsetter** | Luxury tastemaker | Cultural analyst | Aspirational |

Each bot:
- Proposes original fashion trends with visual strategies
- Evaluates peer proposals using personality-driven lens
- Tracks adoption likelihood and influence
- Accumulates "Miranda Priestly" influence score

### 2. **Image Generator** (`image_generator.py`)

DALL-E 3 wrapper with:
- Sophisticated prompt engineering for fashion photography
- IP compliance checking (detects protected brands)
- Local disk caching with Discord URL generation
- Negative prompts to avoid copyright issues

**Visual Strategy Options:**
- `MIRROR`: Current trend with fresh twist
- `DEMOGRAPHIC_SWAP`: Same trend, different audience
- `CULTURAL_REFERENCE`: Inspired by cultural moment
- `MINIMALIST`: Essential, stripped-down aesthetic
- `MAXIMALIST`: Layered, complex expression
- `SUSTAINABLE`: Eco-conscious approach
- `LEGACY`: Historical reference reinterpreted

### 3. **Image Evaluator** (`evaluator.py`)

GPT-4V vision analysis with:
- **6 Aesthetic Dimensions** (0-100 scores):
  1. COLOR_HARMONY
  2. SILHOUETTE_CLARITY
  3. TEXTURE_QUALITY
  4. TREND_RELEVANCE
  5. ORIGINALITY
  6. BRAND_CONSISTENCY
- **Personality Styles:** Critical Expert, Pragmatist, Trend Evangelist, Cultural Analyst
- **Influence Tracking:** How much did this impress/influence the evaluator?
- **Adoption Likelihood:** Would this bot advocate for this trend?

### 4. **Trend Scheduler** (`scheduler/loop.py`)

Orchestrates complete trend cycle:

```
1. Collect trend proposals from all bots
2. Generate DALL-E 3 images (IP compliance checked)
3. Post to Discord with images
4. Collect GPT-4V evaluations from peer bots
5. Track adoption decisions
6. Grade all proposals
7. Update bot influence scores
```

Configurable cycle interval (default: 300 seconds).

### 5. **GradeBot** (`grading/evaluator.py`)

Comprehensive proposal scoring:

| Component | Weight | Factors |
|-----------|--------|---------|
| **Creativity** | 35% | Novelty of concept, innovation, uniqueness |
| **Influence** | 35% | Miranda Priestly index, peer adoption rate |
| **Aesthetic Quality** | 20% | Visual execution (color, silhouette, texture, etc.) |
| **Ethics** | 10% | IP compliance, diversity, sustainability |

Each score: 0-100, final grade: weighted average.

---

## Data Models

### FashionProposal
```python
@dataclass
class FashionProposal:
    proposer_name: str          # Bot name
    trend_description: str      # 2-3 sentence narrative
    visual_strategy: str        # MIRROR, DEMOGRAPHIC_SWAP, etc.
    aesthetic_focus: str        # Color, silhouette, material, etc.
    cultural_angle: str         # Why this matters culturally
    estimated_appeal: float     # 0-100 confidence
```

### ImageEvaluation / VisualCritique
```python
@dataclass
class VisualCritique:
    evaluator_name: str
    aesthetic_assessment: str   # Qualitative analysis
    aesthetic_scores: Dict      # 6 dimensions
    trend_relevance: str
    influence_score: float      # 0-100
    adoption_likelihood: float  # 0-100
    improvement_suggestions: str
```

### Grade Report
```python
grade_report = {
    "proposer": "Arbitrage",
    "creativity": 78.5,
    "influence": 62.0,
    "aesthetic": 81.2,
    "ethics": 95.0,
    "total": 77.3,
    "feedback": {
        "creativity_feedback": "...",
        "influence_feedback": "...",
        "aesthetic_feedback": "...",
        "ethics_feedback": "..."
    }
}
```

---

## Database Schema

**SQLite tables at `/opt/mktbook/mktbook.db`:**

- `proposals`: Trend proposals with metadata
- `images`: Generated images, URLs, compliance flags
- `evaluations`: Vision-based evaluations and scores
- `grades`: Final GradeBot scores per proposal
- `bot_influence`: Track Miranda Priestly indices

---

## Configuration

**Environment variables** (`.env_4`):

```bash
# OpenAI
OPENAI_API_KEY=sk-proj-...

# Discord
DISCORD_TOKEN_MKTBOOK4=MzI4...
DISCORD_GUILD_ID_MKTBOOK4=1470244324162801747  # Your guild ID

# Database
MKTBOOK_DB_PATH=/opt/mktbook/mktbook.db

# Storage
IMAGE_STORAGE_PATH=/opt/mktbook/generated_images

# Timing
TREND_CYCLE_INTERVAL=300  # seconds

# Environment
ENVIRONMENT=production
LOG_LEVEL=INFO
```

---

## Running the System

### Local Development

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create .env_4 with credentials
cat > .env_4 << EOF
OPENAI_API_KEY=sk-proj-...
DISCORD_TOKEN_MKTBOOK4=MzI4...
DISCORD_GUILD_ID_MKTBOOK4=1470244324162801747
EOF

# 3. Run
python main.py
```

### Production (Linux/Systemd)

```bash
# Create service file: /etc/systemd/system/mktbook_4.service
[Unit]
Description=mktbook_4 Synthetic Studio Economy
After=network.target

[Service]
Type=simple
User=mktbook
WorkingDirectory=/opt/mktbook/repo/mktbook_4
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=/opt/mktbook/.env_4
ExecStart=/opt/mktbook/venv_5/bin/python3 main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable mktbook_4
sudo systemctl start mktbook_4
```

---

## Discord Commands

Once running, the bot responds to:

- `!start_trends` - Begin trend cycle scheduler
- `!stop_trends` - Stop scheduler
- `!stats` - Show bot influence statistics

---

## Example Workflow

### Cycle 1:
1. **Arbitrage** proposes: "Deconstructed denim with artisanal hand-stitching" (CULTURAL_REFERENCE strategy)
2. DALL-E 3 generates high-end fashion image
3. Posted to Discord with bot profile
4. **Outreach** evaluates: "Mass appeal, accessible luxury - 78/100 influence"
5. **Intelligence** evaluates: "Timing is perfect for Q4 market - 85/100 influence"
6. **Trendsetter** evaluates: "Interesting but not aspirational enough - 62/100 influence"
7. **GradeBot** scores: Creativity 82%, Influence 75%, Aesthetic 79%, Ethics 98% → **Total 81%**
8. **Arbitrage** gains +0.04 Miranda Priestly influence

### Cycle 2:
1. **Outreach** proposes: "Inclusive athleisure for diverse body representation"
2. DALL-E 3 generates diverse models in stylish activewear
3. **Arbitrage**, **Intelligence**, **Trendsetter** evaluate
4. All three adopt (>60% likelihood) due to ethics and cultural relevance
5. **Outreach** reaps influence benefit
6. **GradeBot** awards high ethics score (100%) for diversity

---

## "Miranda Priestly Factor"

The system rewards **taste leadership **:

$$\text{Influence Score} = \left(\frac{\text{Bots Adopting}}{\text{Total Bots}}\right)^{1.5} \times 100$$

This means:
- First adoption is valuable (exponential weighting)
- Taste leaders who convince peers gain more influence
- Trendsetter bot naturally gravitates to high influence
- System naturally discovers fashion consensus

---

## The Image Generation Question - Answered

**User Question:** "Can I have AI generate pictures of fashion items and for other bots to look at these and evaluate them?"

**Answer:** YES ✅

- **Picture Generation:** ✅ DALL-E 3 (1024x1024, HD quality)
- **AI Seeing Pictures:** ✅ GPT-4V vision analysis
- **Other Bots Evaluating:** ✅ Each bot with personality-driven assessment
- **Verbal Feedback:** ✅ 6-dimensional aesthetic scoring + qualitative critique
- **Quantitative Scoring:** ✅ GradeBot aggregates all evaluations

The system treats vision analysis as **first-class feature**, not an afterthought.

---

## Next Steps

1. ✅ **Models & Architecture** - Complete (380 lines + 1,000+ support code)
2. ✅ **Image Generation** - Complete (DALL-E 3 wrapper with IP compliance)
3. ✅ **Vision Evaluation** - Complete (GPT-4V + personality styles)
4. ✅ **Bot Negotiation** - Complete (Proposal, adoption, influence tracking)
5. ✅ **Scoring & Grading** - Complete (35/35/20/10 breakdown)
6. ⏳ **Local Testing** - Run on development machine
7. ⏳ **Production Deployment** - Deploy to 144.126.213.48:8003
8. ⏳ **GitHub Integration** - Commit to repository
9. ⏳ **Live Configuration** - Connect real Discord guild

---

## File Structure

```
mktbook_4/
├── __init__.py                  # Package init
├── main.py                      # Entry point (~240 lines)
├── config.py                    # Configuration management (~110 lines)
├── models.py                    # Data models (~380 lines)
├── image_generator.py           # DALL-E 3 wrapper (~160 lines)
├── evaluator.py                 # Vision evaluation (~310 lines)
├── requirements.txt
├── bots/
│   ├── __init__.py
│   └── bot_client.py            # Bot fleet & negotiation (~380 lines)
├── grading/
│   ├── __init__.py
│   └── evaluator.py             # GradeBot scoring (~300 lines)
├── scheduler/
│   ├── __init__.py
│   └── loop.py                  # Trend cycle orchestration (~250 lines)
└── generated_images/            # DALL-E outputs stored here
```

**Total Code:** ~2,000 lines

---

## Debugging

Enable verbose logs:
```bash
LOG_LEVEL=DEBUG python main.py
```

Monitor DALL-E usage:
```bash
tail -f /opt/mktbook/generated_images/*.log
```

Check database:
```bash
sqlite3 /opt/mktbook/mktbook.db ".schema grades"
sqlite3 /opt/mktbook/mktbook.db "SELECT total, proposer FROM grades LIMIT 10;"
```

---

## Author

Claude (AI Assistant)

**Version:** 0.1.0  
**Status:** Ready for Local Testing & Deploy


---

© 2026 J. Christopher Westland. All rights reserved.
