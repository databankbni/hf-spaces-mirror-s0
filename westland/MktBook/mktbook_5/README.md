> **DEPRECATED — Legacy Archive (pre-v1.00)**
> This directory is from the old Discord-based multi-service architecture and is no longer used.
> All five workouts now run as a single unified service from the `mktbook/` directory.
> For current documentation, see [README.md](../README.md) and [STUDENT_MANUAL.md](../STUDENT_MANUAL.md).
>
> **As of v2.20**, Workout #5 is the **Influencer A/B Showdown** — engagement-based grading
> (Share of Conversation, Virality, Sentiment Shift, Interaction Depth) run separately for
> Ecosystem A and Ecosystem B, producing two independent leaderboards.

---

# mktbook_5: Influencer A/B Showdown (v2.20+)

## The Final Workout — Attention Economy A/B Test

**Scenario:** A major brand requires a complete marketing ecosystem overhaul. **The stakes are high:** All previous learnings (Workouts 1-4) can be integrated.

**Challenge:** Students run **two parallel bot sets** (Ecosystem A vs. Ecosystem B) with different marketing strategies.

**Success Metric:** Comparative Economic Value via A/B Testing + Bayesian statistical analysis.

**The Innovation:** The Grade-Bot doesn't just look at final scores—it **compares the slope of improvement** between strategies using Westland's Bayesian framework to make rigorous statistical comparisons.

---

## The Student Role: "Manager of AI Agents"

You are not a coder implementing features. You are a **Chief Marketing Officer (CMO)** who:

1. **Hypothesizes:** "Strategy A (Aggressive/Visual) will beat Strategy B (Passive/Textual)"
2. **Designs:** Two distinct marketing bot personalities with competing philosophies
3. **Deploys:** Both ecosystems live in Discord simultaneously
4. **Monitors:** Real-time performance dashboards with Bayesian updates
5. **Concludes:** Defends your chosen winner based on statistical evidence

**The GradeBot handles all mathematics.** You design strategies; statistics handle the comparison.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│ STUDENT (CMO Manager)                                   │
│ • Define 2 Marketing Strategies                          │
│ • Hypothesize who will win                              │
│ • Monitor bid ecosystems in Discord                      │
└──────────────┬──────────────────────────────────────────┘
               │
    ┌──────────┴──────────┐
    │                     │
┌───▼────────────┐   ┌───▼────────────┐
│ ECOSYSTEM A    │   │ ECOSYSTEM B    │
│ Strategy 1     │   │ Strategy 2     │
│ • 2+ Marketing │   │ • 2+ Marketing │
│   Bots         │   │   Bots         │
│ • Different    │   │ • Different    │
│   personalities│   │   personalities│
└───┬────────────┘   └───┬────────────┘
    │                     │
    └──────────┬──────────┘
               │
    ┌──────────▼──────────────────┐
    │ REAL-TIME MONITORING        │
    │ • Engagement tracking       │
    │ • Conversion tracking       │
    │ • Sentiment analysis        │
    │ • Performance trajectories  │
    └──────────┬──────────────────┘
               │
    ┌──────────▼──────────────────┐
    │ BAYESIAN INFERENCE ENGINE   │
    │ • Prior specification       │
    │ • Likelihood calculation    │
    │ • Posterior updating        │
    │ • Credible intervals        │
    │ • P(A>B|data) calculation   │
    └──────────┬──────────────────┘
               │
    ┌──────────▼──────────────────────────┐
    │ COMPARATIVE GRADE-BOT               │
    │ • Slope analysis (improvement rate) │
    │ • Statistical rigor scoring         │
    │ • Strategy execution grading        │
    │ • Winner clarity assessment         │
    │ → FINAL GRADE (0-100)              │
    └────────────────────────────────────┘
```

---

## Key Components

### 1. **Student Strategies** (Your Design)

Each student creates 2+ marketing strategies with **different axes**:

#### Strategy Dimensions:

**Primary Axes:**
- **AGGRESSIVE** vs **PASSIVE** (Hard sell vs. Soft touch)
- **VISUAL** vs **TEXTUAL** (Images vs. Narrative)
- **TECHNICAL** vs **EMOTIONAL** (Specs vs. Connection)

**Example Combinations:**
| Name | Axes | Philosophy |
|------|------|------------|
| Strategy A | AGGRESSIVE + VISUAL | "Hard-sell with urgency and bold imagery" |
| Strategy B | PASSIVE + TEXTUAL | "Relationship-building through storytelling" |
| Strategy C | TECHNICAL + DATA | "Specification and competitive advantage" |
| Strategy D | EMOTIONAL + LIFESTYLE | "Identity and aspirational messaging" |

### 2. **Marketing Bots** (`bots/marketing_bots.py`)

**Provided Examples:**

| Bot | Strategy | Personality | Approach |
|-----|----------|-------------|----------|
| **AggressiveVisualBot** | AGGRESSIVE + VISUAL | Hard-sell, urgency | Limited-time offers, bold CTAs, emoji |
| **PassiveTextualBot** | PASSIVE + TEXTUAL | Relationship | Story-driven, no pressure, thoughtful |
| **TechnicalDataBot** | TECHNICAL + TEXTUAL | Analytical | Specs, comparisons, data-backed claims |
| **EmotionalInfluencerBot** | EMOTIONAL + VISUAL | Lifestyle | Aspirational, identity, community |

**Each bot:**
- Generates unique product pitches based on strategy
- Responds to customer inquiries with personality
- Logs engagement metrics (impressions, clicks, conversions)
- Tracks sentiment of interactions

### 3. **A/B Test Manager** (`ab_testing/manager.py`)

Orchestrates the experiment:
- Experiment creation
- Real-time metric collection
- Interaction logging
- Trajectory tracking
- Performance aggregation

```python
# Student creates experiment:
experiment = await test_manager.create_experiment(
    student_name="Your Name",
    guild_id=1470244324162801747,
    strategy_a=aggressive_visual_strategy,
    strategy_b=passive_textual_strategy,
    primary_hypothesis="Aggressive will drive conversions faster",
    alternative_hypothesis="Passive builds more loyalty",
    success_criteria=[
        "5%+ engagement rate",
        "2%+ conversion rate",
        "Clear winner (p < 0.05)"
    ]
)
```

### 4. **Bayesian A/B Engine** (`bayesian/engine.py`)

**Westland's Bayesian Framework** - No math needed, engine handles it:

#### Prior Specification
- **Assumption:** Before data, both strategies equally likely (μ = 50, σ² = 100)
- **Meaning:** Neutral starting belief, high uncertainty

#### Likelihood
- New observations update our belief about which strategy is better
- "If we observe 8% engagement with Strategy A..."

#### Posterior Distribution
- Updated belief after seeing data
- **Normal-Normal conjugacy:** Mathematically elegant Bayesian update
- Produces: Mean (μ), Variance (σ²), Credible Interval

#### Comparison Logic
**P(A > B | data)** = Probability A is truly better given observations
- Not just "A had 8%, B had 7%" 
- Rather: "Given uncertainty, what's probability A is genuinely superior?"
- Accounts for sample size, variance, and random noise

```python
# Engine does heavy lifting:
posterior_a = bayesian_engine.update_posterior(
    EcosystemLabel.ECOSYSTEM_A, "AggressiveBot", "engagement"
)
# Returns: μ=65.2, σ=8.4, CI=[49-81], essentially "we're 85% confident A's true mean > 50"

comparison = bayesian_engine.compare_ecosystems("engagement")
# Returns: P(A>B)=0.82, P(B>A)=0.15, P(equivalent)=0.03
```

### 5. **Comparative GradeBot** (`grading/grade_bot.py`)

**Grades students on strategy design and execution (not just results):**

| Component | Weight | What It Measures |
|-----------|--------|------------------|
| **Trajectory Analysis** | 30% | Speed of improvement (slope) |
| **Statistical Rigor** | 25% | Sample size, significance, effect size |
| **Strategy Execution** | 25% | Did both strategies function well? |
| **Winner Clarity** | 20% | Was there a clear winner? |

**Final Grade Breakdown:**
```
Final = (0.30 × Trajectory) + (0.25 × Rigor) + (0.25 × Execution) + (0.20 × Winner)
```

**Letter Grades:** A (93+), B (83-92), C (73-82), D (60-72), F (<60)

#### What GradeBot Evaluates:

##### Trajectory Analysis (30%)
- "Did you improve **quickly** enough?"
- Compares slope of improvement between A and B
- Rewards consistent, fast improvement (high R²)
- Penalty if both strategies stagnate

```
Slope Interpretation:
• Slope > 2: Fast improvement (great strategies)
• Slope 0.5-2: Moderate improvement
• Slope < 0.5: Slow improvement (rethink strategy)
```

##### Statistical Rigor (25%)
- "Did you collect enough data?"
- **p-value < 0.05**: Statistical significance (15 points)
- **Confidence > 95%**: High confidence in winner (15 points)
- **Effect size > 0.8**: Practically meaningful difference (10 points)

##### Strategy Execution (25%)
- "Did both bots work?"
- Both strategies achieved min thresholds (30+ points)
- Strategy clarity in hypothesis (10 points)

##### Winner Clarity (20%)
- "Is there a clear winner?"
- One strategy >> another: +25 points
- Clear difference across metrics: +15 points
- Tie/inconclusive: 0 points or negative

#### Example Grade Reports:

**Student A - Grade: 87 (B+)**
```
Trajectory Analysis: 92/100
  ✓ Ecosystem A showed 2.1x/hour improvement
  ✓ Ecosystem B showed 0.8x/hour improvement
  → Clear winner in velocity

Statistical Rigor: 78/100
  ⚠ p-value = 0.08 (marginally significant)
  ✓ Confidence = 92% that A > B
  → Good but could use more data

Strategy Execution: 84/100
  ✓ Both strategies performed well
  ✓ Clear hypothesis differentiation
  → Small execution gaps

Winner Clarity: 82/100
  ✓ Strategy A wins by ~15 point margin
  ✓ Consistent across engagement metrics
  ⚠ Conversion rates were similar
  → Winner clear but not unanimous

Feedback: "Excellent velocity comparison. Your aggressive model improved faster than competition. Consider running longer for conversion clarity."
```

**Student B - Grade: 62 (D+)**
```
Trajectory Analysis: 48/100
  ✗ Ecosystem A: slope = 0.2 (nearly flat)
  ✗ Ecosystem B: slope = -0.1 (declining)
  → Both strategies underperformed

Statistical Rigor: 55/100
  ✗ p-value = 0.31 (not significant)
  ✗ Confidence only 58% (essentially a coin flip)
  → Need larger sample or clearer differentiation

Strategy Execution: 68/100
  ✓ Both ran without crashes
  ⚠ Low engagement overall (1-2%)
  → Hypothesis may not resonate

Winner Clarity: 45/100
  ✗ No clear winner (flip of a coin)
  ✗ Probability difference: A (51%) vs B (49%)
  → Statistical tie

Feedback: "Neither strategy resonated. Your hypotheses may not reflect actual customer values. Redesign your Value Prop and try again."
```

---

## Data Models

### StrategyType Enum
```python
AGGRESSIVE = "aggressive"       # Hard sell, direct CTA
PASSIVE = "passive"           # Soft touch, relationship
VISUAL = "visual"             # Image/video-driven
TEXTUAL = "textual"           # Narrative/wit-driven
TECHNICAL = "technical"       # Spec-focused, data-driven
EMOTIONAL = "emotional"       # Story-driven, connection
```

### MarketingStrategy Dataclass
```python
@dataclass
class MarketingStrategy:
    name: str                          # "Aggressive Visuals"
    primary_strategy: StrategyType     # AGGRESSIVE
    secondary_strategy: StrategyType   # VISUAL
    hypothesis: str                    # Why this will win
    target_audience: str               # Demo, psychographics
    value_proposition: str             # Core message
    engagement_prediction: float       # 0-100 expected engagement
    conversion_prediction: float       # 0-100 expected conversions
```

### EngagementMetrics Dataclass
```python
@dataclass
class EngagementMetrics:
    impressions: int              # Users saw content
    clicks: int                   # Clicked on CTA
    inquiries: int                # Asked questions
    conversions: int              # Made purchase
    
    engagement_rate: float        # clicks/impressions
    conversion_rate: float        # conversions/impressions
    average_sentiment: float      # -1 to 1
    revenue_generated: float      # $
```

### BayesianPosterior
```python
@dataclass
class BayesianPosterior:
    posterior_mean: float         # Updated estimate (e.g., 65.2)
    posterior_variance: float     # Updated uncertainty
    posterior_std: float          # √variance
    credible_interval_lower: float  # 95% CI lower bound
    credible_interval_upper: float  # 95% CI upper bound
    
    observation_count: int        # N observations used
    effective_sample_size: float  # ESS (accounting for priors)
```

### ComparisonResult
```python
@dataclass
class ComparisonResult:
    mean_diff: float              # A mean - B mean (e.g., 8.5)
    effect_size: float            # Cohen's d (0.2=small, 0.5=med, 0.8=large)
    t_statistic: float            # t-score from comparison
    p_value: float                # Significance (0.05 threshold)
    
    probability_a_better: float   # P(A > B | data)
    probability_b_better: float   # P(B > A | data)
    probability_equivalent: float  # P(A ≈ B | data)
    
    recommendation: str           # "Scale A", "Continue Testing", etc.
```

### PerformanceTrajectory
```python
@dataclass
class PerformanceTrajectory:
    timestamps: List[datetime]    # Time points
    values: List[float]           # Metrics at each time
    
    slope: float                  # Improvement rate (per hour)
    r_squared: float              # Fit quality (0-1)
    
    projected_value_24h: float    # Predicted value in 24 hours
    projected_value_7d: float     # Predicted value in 7 days
```

---

## Database Schema

**All data persists in shared SQLite at `/opt/mktbook/mktbook.db`:**

```sql
CREATE TABLE experiments (
    experiment_id TEXT PRIMARY KEY,
    student_name TEXT,
    strategy_a TEXT,
    strategy_b TEXT,
    hypothesis_a TEXT,
    test_duration_hours INTEGER,
    significance_level REAL
);

CREATE TABLE interactions (
    experiment_id TEXT,
    bot_name TEXT,
    ecosystem TEXT,           -- "A" or "B"
    engagement_type TEXT,     -- "view", "click", "buy", etc.
    sentiment_score REAL,     -- -1 to 1
    timestamp TIMESTAMP
);

CREATE TABLE metrics (
    experiment_id TEXT,
    bot_name TEXT,
    ecosystem TEXT,
    impressions INTEGER,
    clicks INTEGER,
    conversions INTEGER,
    engagement_rate REAL,
    conversion_rate REAL,
    revenue_generated REAL,
    timestamp TIMESTAMP
);

CREATE TABLE bayesian_observations (
    experiment_id TEXT,
    ecosystem TEXT,
    metric_type TEXT,         -- "engagement", "conversion", etc.
    observed_value REAL,
    variance REAL,
    timestamp TIMESTAMP
);

CREATE TABLE comparisons (
    experiment_id TEXT,
    test_metric TEXT,
    mean_diff REAL,
    effect_size REAL,
    p_value REAL,
    prob_a_better REAL,
    prob_b_better REAL,
    recommendation TEXT
);

CREATE TABLE experiment_grades (
    experiment_id TEXT PRIMARY KEY,
    student_name TEXT,
    final_grade REAL,
    trajectory_grade REAL,
    rigor_grade REAL,
    strategy_grade REAL,
    winner_grade REAL,
    winner_ecosystem TEXT,
    winner_confidence REAL,
    feedback TEXT,
    graded_at TIMESTAMP
);
```

---

## Configuration

**Environment variables** (`.env_5`):

```bash
# OpenAI
OPENAI_API_KEY=sk-proj-...

# Discord
DISCORD_TOKEN_MKTBOOK5=MzI4...
DISCORD_GUILD_ID_MKTBOOK5=1470244324162801747  # Your guild

# Database
MKTBOOK_DB_PATH=/opt/mktbook/mktbook.db

# A/B Test defaults
TEST_DURATION_HOURS=24
SIGNIFICANCE_LEVEL=0.05
SAMPLE_SIZE_TARGET=500

# Bayesian priors (neutral starting point)
BAYESIAN_PRIOR_MEAN=50.0
BAYESIAN_PRIOR_VARIANCE=100.0

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

# 2. Create .env_5
cat > .env_5 << EOF
OPENAI_API_KEY=sk-proj-...
DISCORD_TOKEN_MKTBOOK5=MzI4...
DISCORD_GUILD_ID_MKTBOOK5=1470244324162801747
EOF

# 3. Run
python main.py
```

### Production (on 144.126.213.48:8004)

```bash
# Create systemd service: /etc/systemd/system/mktbook_5.service
[Unit]
Description=mktbook_5 Bayesian A/B Testing
After=network.target

[Service]
Type=simple
User=mktbook
WorkingDirectory=/opt/mktbook/repo/mktbook_5
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=/opt/mktbook/.env_5
ExecStart=/opt/mktbook/venv_5/bin/python3 main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable mktbook_5
sudo systemctl start mktbook_5
```

---

## Discord Commands

**For Students:**

- `!create_experiment "Your Name"` - Launch new A/B experiment
- `!experiment_status` - Show all active experiments
- `!bayesian_summary` - Display Bayesian posterior estimates

---

## Student Workflow

### Step 1: Define Your Strategies
```python
# You design these in your code:
strategy_a = MarketingStrategy(
    name="Aggressive & Visual",
    primary_strategy=StrategyType.AGGRESSIVE,
    secondary_strategy=StrategyType.VISUAL,
    hypothesis="Urgency and bold design drive conversion 50% faster",
    target_audience="Early adopters, deal-seekers",
    value_proposition="Limited-time exclusive offer",
    engagement_prediction=75.0,
    conversion_prediction=10.0
)

strategy_b = MarketingStrategy(
    name="Passive & Textual",
    primary_strategy=StrategyType.PASSIVE,
    secondary_strategy=StrategyType.TEXTUAL,
    hypothesis="Relationship-building creates loyal repeat customers",
    target_audience="Thoughtful consumers",
    value_proposition="Aligned with your values",
    engagement_prediction=55.0,
    conversion_prediction=6.0
)
```

### Step 2: Launch Experiment
```
!create_experiment "Your Name"
```

### Step 3: Monitor in Real-Time
```
!bayesian_summary
```

Shows live:
- Posterior means for each ecosystem
- 95% credible intervals
- P(A > B | data)
- Current recommendation

### Step 4: Let Data Accumulate
- Bots pitch products to users
- Systems track engagement, clicks, conversions
- Bayesian engine updates posteriors hourly

### Step 5: Final Grade
After 24 hours:
- GradeBot compares slopes
- Calculates final score
- Generates feedback
- Posts to Discord

---

## Example Scenario

**Student:** Sarah  
**Guild:** IDS518_5

### Experiment Setup
```
Strategy A: "Aggressive Sales" (AGGRESSIVE + VISUAL)
- Hypothesis: "Urgency and visuals drive higher conversion"
- Bots: AggressiveVisualBot, EmotionalInfluencerBot
- Target: Deal-seekers, FOMO-motivated

Strategy B: "Consultative Approach" (PASSIVE + TECHNICAL)
- Hypothesis: "Transparent specs and guidance build trust"
- Bots: PassiveTextualBot, TechnicalDataBot
- Target: Thoughtful buyers, value-conscious
```

### Hour 1-6
```
Ecosystem A: 8% engagement, 2.1% conversion
Ecosystem B: 6% engagement, 1.8% conversion
→ P(A > B) = 62% (not conclusive yet)
→ "Continue testing..."
```

### Hour 12
```
Ecosystem A: 7.5% engagement, 2.3% conversion (SLOPE: +0.3/hour)
Ecosystem B: 6.2% engagement, 1.9% conversion (SLOPE: +0.1/hour)
→ P(A > B) = 78% (getting clearer)
→ "Trajectory favoring A"
```

### Hour 24 (Final)
```
Ecosystem A: 8.1% engagement, 2.5% conversion (SLOPE: +0.25/hour) (R²: 0.92)
Ecosystem B: 6.4% engagement, 1.95% conversion (SLOPE: +0.08/hour) (R²: 0.87)
→ P(A > B) = 89% (clear winner)
→ Effect size: 0.62 (medium)
→ p-value: 0.028 (significant)
```

### GradeBot Report
```
FINAL GRADE: 86/100 (B+)

Trajectory Analysis: 88/100
✓ Ecosystem A improved 3×faster than B
✓ Both showed consistent improvement
→ Excellent velocity comparison

Statistical Rigor: 82/100
✓ Significance achieved (p = 0.028)
✓ High confidence (P(A>B) = 89%)
⚠ Could use larger sample
→ Good statistical foundation

Strategy Execution: 84/100
✓ Both strategies functioned flawlessly
✓ Clear hypothesis differentiation
→ Well-designed experiment

Winner Clarity: 88/100
✓ Ecosystem A clearly dominant
✓ Consistent across metrics
→ Strong signal

RECOMMENDATION: "Scale Strategy A. Your aggressive approach was 3× more effective at building momentum. The passive approach built roughly equal revenue but much slower."
```

---

## The IDS518 Guild - A Living Laboratory

Over 5 workouts, the Discord guild transforms:

**Workout 1:** Cold, empty → Basic bot trading  
**Workout 2:** Bot conversations increase → Multi-turn negotiation  
**Workout 3:** Trend proposals → Image generation + evaluation  
**Workout 4:** (Future) → Real economic simulation  
**Workout 5:** ALL systems compete → Bayesian A/B showdown  

### Emergent Behavior You'll Observe:
- Which strategy adapts fastest?
- Do "winning" bots get copied by others?
- Does sentiment shift over time?
- Which bot personality creates best rapport?
- How do diverse student strategies interact?

---

## Key Insights

### Why Bayesian Analysis Matters
1. **Uncertainty Quantified:** Not "A=8%, B=6%" but "80% confident A is better"
2. **Sample Efficiency:** Works with smaller samples than frequentist tests
3. **Practical Relevance:** Focuses on effect size, not just p-values
4. **Decision-Making:** Gives probabilities for CMO choices

### Why Slope Analysis Matters
- **Final score ≠ strategy quality**
- A strategy showing fast improvement is learning, adapting, working
- A flat line indicates strategy misalignment or poor execution
- **Velocity matters more than position**

### Why This Connects to Real Marketing
- CMOs must decide: "Scale this campaign now or keep testing?"
- Decision requires: "How fast is it improving?" + "How confident am I?"
- This system teaches exactly that decision-making process
- Students become comfortable with uncertainty

---

## File Structure

```
mktbook_5/
├── __init__.py
├── main.py                      # Entry point (~280 lines)
├── config.py                    # Configuration (~80 lines)
├── models.py                    # Data models (~480 lines)
├── requirements.txt
├── README.md
├── ab_testing/
│   ├── __init__.py
│   └── manager.py               # A/B test orchestration (~300 lines)
├── bayesian/
│   ├── __init__.py
│   └── engine.py                # Bayesian inference (~400 lines)
├── bots/
│   ├── __init__.py
│   └── marketing_bots.py        # Bot implementations (~420 lines)
└── grading/
    ├── __init__.py
    └── grade_bot.py             # Comparative grading (~450 lines)
```

**Total:** ~2,500 lines of production-ready code

---

## Deployment Checklist

- [ ] Create Discord guild IDS518_5
- [ ] Copy mktbook_5 to 144.126.213.48:/opt/mktbook/repo/mktbook_5
- [ ] Create .env_5 with credentials
- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Create systemd service for port 8004
- [ ] Test local: `python main.py`
- [ ] Deploy to droplet
- [ ] Enable/start systemd service
- [ ] Verify Discord connectivity
- [ ] Commit to GitHub

---

## Westland's Bayesian Framework - Simplified

You don't need to understand math. Here's what happens:

1. **Prior:** "I think both strategies are equally good" (neutral)
2. **Data Arrives:** "Strategy A got 8% engagement, B got 6%"
3. **Update:** Engine recalculates beliefs about each strategy
4. **Posterior:** "I'm now 78% confident A is better"
5. **Repeat:** Each new data point refines confidence further
6. **Decision:** Once confidence > 95%, winner is clear

**The beauty:** Accounts for randomness, sample size, and uncertainty automatically.

---

## Next Steps for Students

1. **Design your strategies** - pick your axes (Aggressive/Passive × Visual/Textual, etc.)
2. **Write your hypothesis** - "Why will Strategy A beat B?"
3. **Implement two bot personalities** - based on your strategies
4. **Launch experiment** - `!create_experiment "Your Name"`
5. **Monitor** - Check `!bayesian_summary` every few hours
6. **Analyze final report** - Understand why one strategy won
7. **Present findings** - Defend your strategy design based on data

---

## Author & Version

**Claude (AI Assistant)**  
**Version:** 0.1.0  
**Status:** Production-ready  
**Integration:** Compatible with mktbook, mktbook_2, mktbook_3, mktbook_4


---

© 2026 J. Christopher Westland. All rights reserved.
