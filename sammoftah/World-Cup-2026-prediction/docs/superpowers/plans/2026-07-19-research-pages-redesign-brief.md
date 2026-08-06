# Research pages redesign brief (corrected)

Redesign three surfaces of the World Cup 2026 Forecaster to an editorial,
FiveThirtyEight/FT-style data product: **Beat the Model** (scenario challenge),
**Evidence** (track record), **Compare with other forecasters**.

This brief replaces an earlier draft whose reference mockups contained
fabricated data and assumed a React SPA. Read the two override sections below
before anything else; they outrank every other instruction and any reference
image.

## Override 1 — the stack is Gradio, not React

- Python 3.10+ / **Gradio** app (`app.py` → `src/underdog_lab/ui/app.py`).
- "Pages" are **Gradio tabs**; there is no routing, no deep links to preserve
  beyond tab structure, no SSR framework.
- All page content is **server-rendered HTML strings** built by Python
  functions in `src/underdog_lab/ui/components.py`, `ui/app.py`, and
  `world_cup/ui.py`. All styling lives in one CSS string:
  `src/underdog_lab/ui/theme.py` (`CSS`).
- There is **no charting library, no TypeScript, no build step, no test
  runner for JS**. Charts are hand-rolled HTML/CSS bars. Keep it that way —
  do not add npm, React, or a chart dependency.
- "Reusable components" means **Python helper functions returning HTML
  snippets**, following the existing conventions (`forecast_html`,
  `_player_card_html`, `section` helpers). Do not build a component library.
- Interactivity is limited to what Gradio provides (inputs, buttons, tab
  switches) plus static CSS states. No client-side sorting, tooltips beyond
  `title=`, stickiness, or steppers with JS state. Design within that budget.
- Tests are pytest (`python3 -m pytest tests/`). All 157 must stay green.
  Run `PYTHONPATH=src python3 scripts/health_check.py` after changes.

## Override 2 — banned content (fabrication guard)

The original reference mockups are **style direction only. Every number,
label, model name, and section in them is placeholder fiction unless it
matches the Real Data Inventory below.** Specifically banned — none of these
exist in this product and must not appear:

- "50,000+ matches", "17 tournaments", "10.2M+ predictions", "2000–2024",
  "updated every 24h"
- Any "accuracy = 1 − Brier" framing, "82% accuracy", "Top 38% vs public
  models"
- Any model-vs-model Brier leaderboard: FiveThirtyEight (SPI), Opta Analyst
  Brier scores, Elo Ratings model, Betting Market (Avg.), Pundit Poll,
  Random Guess rows, "#1 of 7 models", head-to-head accuracy percentages,
  Brier-over-time by year charts
- Calibration plots, calibration slope, ECE, reliability curves (no such
  artifact exists; we have temperature scaling with selection/confirmation
  reports only)
- Sensitivity analysis (team strength ±x%, weather, travel distance, rest
  days, injuries)
- Per-user challenge progress persistence, "2/20 completed", global rank,
  leaderboards (the challenge is local-first; nothing is stored server-side)
- 3D football hero renders or any new image assets
- By-stage Brier tables, "accuracy distribution" histograms, multi-year
  track-record lines

If a mockup section has no entry in the Real Data Inventory, **omit the
section**. Never resolve a conflict in favor of the mockup.

## Real Data Inventory (the only permitted numbers, with sources)

Values below are indicative as of 2026-07-18; always compute at render time
from the live functions — never hardcode.

### Evidence (track record tab)

Source: `world_cup/predictions.py::scored_track_records` over
`repository.tournament_fixtures`; backtest: `models/backtest_report.json`;
fit: `models/elo_fit_report.json`; calibration:
`models/recalibration_evaluation.json`, `models/upgrade_evaluation.json`.

- Live prospective record: **65 matches scored**, top-pick accuracy
  **64.6%**, mean log loss **0.914** (uniform 1.099, skill **+16.9%**),
  mean Brier **0.533**, mean RPS **0.161**; coverage 65 of 102 completed
  fixtures (excluded = no verified pre-kickoff artifact — say so).
- Horizon buckets (hide empty ones, keep spelled-out titles): 2–6 h n=2;
  6–24 h n=3; >1 day n=60 (66.7% accuracy, LL 0.879).
- Walk-forward backtest: **8,265 test matches, 2018–2026 folds**; mean log
  loss fitted **0.794** vs previous model 0.833 vs uniform 1.099 (also Brier
  0.465/0.486/0.667, RPS 0.148/0.157/0.239).
- Model fit: 11,094 matches (2015-01-03 → 2026-06-12), time-decayed MLE,
  180-day half-life, information cutoff 2026-06-12.
- Calibration: temperature T = 0.886, selected over T=1 on selection folds
  and confirmed on held-out 2026 fold. Describe in words; no reliability
  plot.
- Biggest live misses (real, from scored rows — recompute at render):
  Spain 0-0 Cape Verde (had home 96.7%…LL 3.42), England 0-0 Ghana,
  Ecuador 0-0 Curaçao, South Africa 1-0 South Korea, Qatar 1-1 Switzerland.
- Artifact integrity: SHA-256 manifests, post-kickoff rejection, audit
  counts from `audit_forecasts` (eligible/rejected).

### Beat the Model (scenario challenge tab)

Source: `data/raw/challenge_matches.json` (20 historical matches),
existing challenge flow in `ui/app.py` + `scenarios/`.

- Per match available: date, competition, stage, teams, venue,
  neutral flag, pre-match Elos, context paragraph, reveal notes. Examples:
  Argentina–Saudi Arabia WC2022, Brazil–Germany WC2014 SF,
  Germany–South Korea WC2018, Portugal–Greece Euro 2004 final.
- Flow: pick match → read context (result hidden) → enter p(home/draw/away)
  summing to 1 → reveal actual result + model forecast + log-loss/Brier
  comparison. A 4-step visual stepper is fine **as static per-state
  rendering**, driven by the existing Gradio flow, not JS.
- No persistence, no rank. Progress may be shown per-session only if the
  existing app state already tracks it; otherwise omit.

### Compare with other forecasters tab

Source: `data/world_cup_2026/external_forecasts.json`,
`world_cup/comparison.py`.

- Exactly **two external sources**, both captured **2026-06-09**
  (pre-tournament):
  - Opta Supercomputer (Stats Perform) — headline title probabilities for
    11 teams (Spain 16.1%, France 13.0%, England 11.2%, Argentina 10.4%, …).
  - RotoWire team projections — per-team group-win and round-of-32
    qualification probabilities for all 48 teams.
- Our model's numbers come from the live simulation/bracket; snapshots are
  **asynchronous** (theirs pre-tournament, ours live). State this
  prominently; never present the columns as contemporaneous.
- `frozen_long_range_top4()` benchmark card content must be preserved.
- Derived summaries (largest agreement/disagreement, ranges) are allowed
  only if computed at render time from these actual values.

## Design direction (kept from the original brief)

Editorial, light, calm: warm off-white background, near-black ink, muted
slate secondary, blue analytical accent, red action accent, restrained green
for positives, hairline cool-gray borders. Strong headline hierarchy,
numbered sections (1. 2. 3.), short subtitles, compact chart labels, small
source notes under every data block. Centered max-width container, generous
section spacing, subtle section borders instead of floating card salad.
Horizontal bars over donuts; label values directly; no gradients, glass,
shadows, 3D. Every metric row must carry its unit and its "lower/higher is
better" direction. Existing font stack.

## Process rules

1. Work on a branch (`redesign/research-pages`), **never** push to
   `personal-space` (the live Space) — deploys happen only after human
   review of screenshots.
2. Audit first: enumerate every data element currently rendered on the three
   tabs; the redesign must account for 100% of them (keep or consciously
   drop with a stated reason).
3. After implementing, render each tab and screenshot at desktop and
   ~420 px widths; verify no clipped tables, no invented numbers.
4. `python3 -m pytest tests/` green, health check green, no forecasting or
   scoring logic changes.
5. Summarize: files changed, sections mapped old→new, anything dropped and
   why.

## Acceptance criteria

1. Three tabs match the editorial direction and share one visual system.
2. Every displayed value traces to the Real Data Inventory / live functions.
3. Nothing from the banned list appears.
4. Challenge flow, scoring, comparison, and health checks work unchanged.
5. Tests and health check pass; screenshots reviewed before any deploy.
