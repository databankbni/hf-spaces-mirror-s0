# Live Knockout and Final Forecast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the World Cup Space from a group-stage dashboard into a live 104-match tournament tracker that ingests knockout results, shows the next match and conditional final forecasts, scores completed knockout forecasts, and redeploys the personal Space.

**Architecture:** Preserve the existing immutable group-stage repository and prospective scorecard. Add a separate checked-in knockout snapshot containing provider-resolved matches and placeholders, expose `knockout_fixtures` and `tournament_fixtures`, and make the simulation condition on verified knockout results. Use ESPN's public FIFA scoreboard for all stages, with stage/order mapping and strict provider provenance. The UI will lead with the next resolved fixture and conditional final scenarios until the second semifinal completes.

**Tech Stack:** Python 3.12, Pydantic 2, urllib, pytest, Gradio 6, JSON snapshots, GitHub Actions, Hugging Face Spaces.

## Global Constraints

- Never modify historical group-stage forecast artifacts or manifests.
- Knockout result snapshots must retain provider event IDs, raw-response SHA-256, fetch timestamp, stage, match number, kickoff and scores.
- Scheduled placeholders may appear in the bracket but must never be scored or forecasted until both teams resolve.
- A completed knockout result must be used by tournament simulation rather than re-simulated.
- Final probabilities must clearly distinguish regulation 1X2 from advancing/champion probability.
- Every new behavior gets a failing test before production implementation.
- Full verification uses `PYTHONPATH=src:. pytest -q`, health checks, live revision checks and live config markers.

---

### Task 1: Add knockout domain and repository fixtures

**Files:**
- Modify: `src/underdog_lab/world_cup/models.py`
- Modify: `src/underdog_lab/world_cup/data.py`
- Create: `data/world_cup_2026/knockout.json`
- Test: `tests/unit/test_world_cup_knockout.py`

- [ ] Write failing tests asserting the repository exposes 72 group fixtures, loads knockout fixtures, returns 104 tournament slots, and reports Spain–France as played with the final unresolved.
- [ ] Run `PYTHONPATH=src:. pytest -q tests/unit/test_world_cup_knockout.py`; confirm the expected missing-property failure.
- [ ] Add `KnockoutFixture` with match number, stage, date/kickoff, teams, scores and optional winner.
- [ ] Add `TournamentRepository.knockout_fixtures` loading the checked-in JSON and `tournament_fixtures` combining group plus knockout.
- [ ] Add validation that knockout IDs are WC26-073 through WC26-104 and stage numbers are unique.
- [ ] Run the focused tests and commit.

### Task 2: Normalize ESPN knockout events and create the live snapshot

**Files:**
- Modify: `src/underdog_lab/world_cup/providers.py`
- Modify: `scripts/fetch_wc2026_results.py`
- Modify: `data/world_cup_2026/provider_mappings/espn.json`
- Create: `tests/fixtures/espn_knockout_wc2026.json`
- Test: `tests/unit/test_fetch_wc2026_results.py`
- Create: `scripts/build_knockout_snapshot.py`

- [ ] Add a failing test for a completed semifinal, scheduled final placeholder, stage mapping, winner and provider IDs.
- [ ] Run the focused provider tests and confirm failure.
- [ ] Implement stage/order mapping from ESPN slugs: round-of-32, round-of-16, quarterfinals, semifinals, 3rd-place-match and final, assigning match numbers 73–104 by kickoff within stage.
- [ ] Keep the existing group normalizer unchanged for scorecard compatibility; add `normalize_espn_knockout_response` returning a separate snapshot schema.
- [ ] Add ESPN provider-team IDs discovered in the existing audited update and aliases for placeholder labels.
- [ ] Implement `scripts/build_knockout_snapshot.py` to fetch the public scoreboard, normalize all knockout events, write a timestamped raw update and atomically update `knockout.json`.
- [ ] Run it against the live scoreboard, verify 32 entries, one completed Spain–France semifinal, scheduled England–Argentina semifinal and scheduled Spain final placeholder, then commit the snapshot.

### Task 3: Condition simulation and produce upcoming/final forecasts

**Files:**
- Modify: `src/underdog_lab/world_cup/simulation.py`
- Modify: `src/underdog_lab/world_cup/forecasting.py`
- Modify: `src/underdog_lab/world_cup/ui.py`
- Modify: `src/underdog_lab/ui/app.py`
- Test: `tests/unit/test_world_cup_knockout.py`
- Test: `tests/unit/test_simulation.py`

- [ ] Add failing tests showing a played knockout match is not re-simulated and unresolved final scenarios produce conditional forecasts.
- [ ] Run focused tests and confirm failure.
- [ ] Update `simulate_tournament` to force winners from played knockout snapshots while simulating only unresolved matches.
- [ ] Add helper for regulation forecast and clearly named knockout advance probability.
- [ ] Replace the group-only upcoming empty state with next resolved knockout fixtures and conditional final scenarios when the opponent is still a placeholder.
- [ ] Keep completed group scorecard wording intact while adding tournament-stage labels.
- [ ] Run focused tests and commit.

### Task 4: Add benchmark scorecard and operational ingestion

**Files:**
- Modify: `src/underdog_lab/world_cup/comparison.py`
- Modify: `src/underdog_lab/ui/app.py`
- Modify: `.github/workflows/result-check.yml`
- Modify: `scripts/track_record_summary.py`
- Test: `tests/unit/test_prediction_scorecard.py`
- Test: `tests/unit/test_result_workflow.py`

- [ ] Add failing tests for benchmark copy and the provider-aware result workflow.
- [ ] Add a visible comparison card: 64.6%/65, +16.8% skill vs equal odds, 4/4 semifinalist set hit, and explicitly mark market overlap as n=3 and descriptive only.
- [ ] Change result ingestion workflow to build/update knockout snapshot from ESPN and label provider dynamically; never auto-apply corrections.
- [ ] Add a tracked “final forecast” artifact path and score only resolved, immutable knockout forecasts.
- [ ] Run focused tests and commit.

### Task 5: Verify and redeploy personal Space

**Files:**
- Modify only files already listed above.

- [ ] Run `PYTHONPATH=src:. pytest -q`, `python3 -m py_compile src/underdog_lab/ui/app.py`, `PYTHONPATH=src python3 scripts/health_check.py`, `git diff --check`.
- [ ] Commit the implementation and snapshots.
- [ ] Push GitHub main and personal Space.
- [ ] Wait for Hugging Face runtime revision to match.
- [ ] Verify live config contains next knockout fixture, conditional final forecast, tournament stage labels and scorecard metrics; verify 104 fixture slots and no stale “all group-stage fixtures have been played” as the primary state.

