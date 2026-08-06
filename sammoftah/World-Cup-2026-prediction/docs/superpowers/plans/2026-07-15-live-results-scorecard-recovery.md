# Live Results and Honest Scorecard Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore automatic World Cup result ingestion without a paid secret, backfill all 72 completed group-stage results, and publish the complete verified pre-kickoff prediction scorecard.

**Architecture:** Keep the existing audited snapshot boundary and add ESPN's public FIFA World Cup scoreboard as a keyless fallback provider. Normalize either provider into the same additions/corrections document, require the scheduled job to report which provider ran, then score only immutable `live-forecast-v2` artifacts whose timestamps, provenance, probabilities, and manifests pass the existing audit.

**Tech Stack:** Python 3.12, Pydantic 2, urllib, pytest, Gradio 6, GitHub Actions, Hugging Face Spaces.

## Global Constraints

- Never modify historical forecast artifacts or their manifests.
- Never score a prediction generated at or after kickoff.
- Keep retrospective current-model replay visibly separate from prospective scores.
- Treat provider corrections as reviewable changes; never silently rewrite an existing result.
- Preserve the official 72-match group-stage fixture orientation and exact kickoff validation.
- Use FIFA's official published results as a human cross-check for the machine-readable ESPN feed.
- A scheduled ingestion run must not appear healthy merely because a required secret is absent.

---

### Task 1: Add a keyless ESPN result provider

**Files:**
- Create: `tests/fixtures/espn_wc2026.json`
- Create: `data/world_cup_2026/provider_mappings/espn.json`
- Modify: `src/underdog_lab/world_cup/providers.py`
- Modify: `scripts/fetch_wc2026_results.py`
- Test: `tests/unit/test_fetch_wc2026_results.py`

**Interfaces:**
- Consumes: `TournamentRepository`, `safe_information_cutoff(...)`, existing internal fixture IDs.
- Produces: `normalize_espn_response(payload, repository, aliases, fetched_at=...) -> dict` and CLI option `--provider {auto,football-data,espn}`.

- [ ] **Step 1: Add a representative frozen ESPN response fixture**

Include one finished group match, one scheduled match, the `fifa.world` league identity, `season.year=2026`, exact UTC kickoff, explicit `homeAway`, and scores.

- [ ] **Step 2: Write failing normalization tests**

```python
def test_espn_response_maps_home_away_and_scores():
    result = normalize_espn_response(payload, repository, aliases, fetched_at=now)
    row = result["results"][0]
    assert row["fixture_id"] == "WC26-003"
    assert (row["home_goals"], row["away_goals"]) == (1, 1)
    assert result["provider"] == "espn"

def test_espn_response_rejects_wrong_competition():
    payload["leagues"][0]["slug"] = "eng.1"
    with pytest.raises(ValueError, match="not FIFA World Cup"):
        normalize_espn_response(payload, repository, aliases, fetched_at=now)
```

- [ ] **Step 3: Verify RED**

Run: `PYTHONPATH=src python3 -m pytest tests/unit/test_fetch_wc2026_results.py -q`

Expected: import failure because `normalize_espn_response` does not exist.

- [ ] **Step 4: Implement the normalizer**

For each `season.slug == "group-stage"` event, resolve competitors by `homeAway`, map names through the provider alias table, validate the internal fixture pair and kickoff within 180 minutes, accept only `status.type.completed is True`, and emit the existing audited update schema with raw-response SHA-256 and provider IDs.

- [ ] **Step 5: Implement provider selection**

```python
provider = args.provider
if provider == "auto":
    provider = "football-data" if token else "espn"
payload = fetch_football_data_payload(token) if provider == "football-data" else fetch_espn_payload()
```

The ESPN request must use:

```text
https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=20260611-20260719&limit=200
```

- [ ] **Step 6: Verify GREEN**

Run: `PYTHONPATH=src python3 -m pytest tests/unit/test_fetch_wc2026_results.py -q`

Expected: all provider tests pass.

### Task 2: Make scheduled ingestion truthful and self-healing

**Files:**
- Modify: `.github/workflows/result-check.yml`
- Modify: `README.md`
- Modify: `docs/world-cup-verification-checklist.md`
- Test: `tests/unit/test_result_workflow.py`

**Interfaces:**
- Consumes: `scripts/fetch_wc2026_results.py --provider auto`.
- Produces: a workflow that always performs a keyless fetch, records the chosen provider, validates candidate data, and opens a human-reviewed PR when results change.

- [ ] **Step 1: Write a failing workflow-contract test**

```python
def test_result_workflow_has_keyless_fallback():
    workflow = Path(".github/workflows/result-check.yml").read_text()
    assert "--provider auto" in workflow
    assert "FOOTBALL_DATA_API_KEY is not configured" not in workflow
    assert "provider=" in workflow
```

- [ ] **Step 2: Verify RED**

Run: `python3 -m pytest tests/unit/test_result_workflow.py -q`

Expected: failure because the workflow currently exits on a missing secret.

- [ ] **Step 3: Replace the false-success branch**

Run the fetcher unconditionally with the optional token. Set `changed` only if the audited update file exists, write the selected provider to the job summary, and retain health/test/PR gates.

- [ ] **Step 4: Update operations documentation**

Document ESPN as the automatic keyless fallback and `FOOTBALL_DATA_API_KEY` as an optional primary provider rather than a mandatory dependency.

- [ ] **Step 5: Verify GREEN**

Run: `python3 -m pytest tests/unit/test_result_workflow.py -q`

Expected: pass.

### Task 3: Backfill and verify all completed group results

**Files:**
- Create: `data/world_cup_2026/result_updates/espn-<UTC timestamp>.json`
- Create: `data/world_cup_2026/backups/snapshot-<UTC timestamp>.json`
- Modify: `data/world_cup_2026/snapshot.json`

**Interfaces:**
- Consumes: the new ESPN normalizer and the current 12-result snapshot.
- Produces: an auditable update containing 60 additions and a snapshot containing 72 group results.

- [ ] **Step 1: Fetch a live dry-run update**

Run: `PYTHONPATH=src python3 scripts/fetch_wc2026_results.py --provider espn --output /tmp/espn-wc2026-update.json`

Expected: `additions=60 corrections=0`.

- [ ] **Step 2: Cross-check the provider payload**

Verify all 72 internal fixtures appear exactly once, all kickoffs match within tolerance, scores are non-negative integers, and the first 12 checked-in results are unchanged. Compare a sample from every matchday with FIFA's official results page.

- [ ] **Step 3: Apply through the audited boundary**

Run: `PYTHONPATH=src python3 scripts/update_snapshot.py --results-file /tmp/espn-wc2026-update.json --allow-corrections`

Expected: a timestamped backup, 60 imported results, zero corrections, and round-trip verification.

- [ ] **Step 4: Preserve the raw normalized update**

Copy the verified update into `data/world_cup_2026/result_updates/` using the fetch timestamp so provenance survives deployment.

- [ ] **Step 5: Verify the recovered health state**

Run: `PYTHONPATH=src python3 scripts/health_check.py`

Expected: `recorded_results: 72`, no overdue group fixtures, and `status: healthy`.

### Task 4: Publish a complete, honest prediction scorecard

**Files:**
- Modify: `src/underdog_lab/world_cup/predictions.py`
- Modify: `src/underdog_lab/ui/app.py`
- Modify: `scripts/track_record_summary.py`
- Test: `tests/unit/test_prediction_scorecard.py`
- Test: `tests/unit/test_prediction_eligibility.py`

**Interfaces:**
- Consumes: 72 final group results and 65 eligible immutable prospective artifacts.
- Produces: score summaries with `accuracy`, `mean_log_loss`, `mean_brier`, `mean_rps`, `log_loss_skill_vs_uniform`, `coverage`, and explicit eligible/excluded counts.

- [ ] **Step 1: Write failing scorecard tests**

```python
def test_summary_reports_accuracy_and_skill():
    summary = _summarize([home_win_correct, draw_wrong])
    assert summary["accuracy"] == 0.5
    assert summary["log_loss_skill_vs_uniform"] == pytest.approx(
        1 - summary["mean_log_loss"] / summary["uniform_log_loss"]
    )

def test_complete_snapshot_scores_only_verified_artifacts():
    records = scored_track_records(repository.fixtures, repository.team_by_name)
    assert records["prospective"]["n"] == 65
    assert records["artifact_audit"]["eligible"] == 65
```

- [ ] **Step 2: Verify RED**

Run: `PYTHONPATH=src python3 -m pytest tests/unit/test_prediction_scorecard.py tests/unit/test_prediction_eligibility.py -q`

Expected: missing scorecard fields.

- [ ] **Step 3: Add scorecard metrics**

Define the predicted class as the largest of `p_home`, `p_draw`, and `p_away`; calculate accuracy and log-loss skill against uniform. Add a top-level coverage summary showing 65 scored predictions out of 72 completed group matches and explicitly list why seven are excluded.

- [ ] **Step 4: Upgrade the Track Record UI**

Show the all-horizons prospective aggregate first. Label positive skill as better than uniform and negative skill as worse. Retain horizon sections and retrospective replay, but visually separate them and state that accuracy is secondary to proper scoring rules.

- [ ] **Step 5: Verify GREEN**

Run: `PYTHONPATH=src python3 -m pytest tests/unit/test_prediction_scorecard.py tests/unit/test_prediction_eligibility.py -q`

Expected: pass.

- [ ] **Step 6: Generate the final score report**

Run: `PYTHONPATH=src python3 scripts/track_record_summary.py`

Expected: 72 recorded fixtures, 65 prospective scored fixtures, complete aggregate and per-horizon metrics, and seven transparently unscored fixtures.

### Task 5: Verify, publish, and confirm the live Space

**Files:**
- Modify only if required by verification: deployment or documentation files already named above.

**Interfaces:**
- Consumes: verified local recovery commit.
- Produces: a pushed GitHub revision, successful deployment workflow, and a live Space serving the same revision and 72-result scorecard.

- [ ] **Step 1: Run the full local gate**

Run:

```bash
PYTHONPATH=src python3 scripts/audit_dataset.py
PYTHONPATH=src python3 scripts/verify_world_cup_bracket.py
PYTHONPATH=src python3 scripts/submission_preflight.py --allow-human-pending
PYTHONPATH=src python3 scripts/health_check.py
PYTHONPATH=src:. python3 -m pytest -q
git diff --check
```

Expected: every command exits 0; health reports 72 recorded results.

- [ ] **Step 2: Commit only recovery files**

Inspect `git status`, stage only the files in this plan, and commit with a message describing keyless ingestion and the complete scorecard.

- [ ] **Step 3: Push the verified revision**

Push to the authorized repository branch. If repository protection requires a PR, create it and do not claim deployment until it is merged.

- [ ] **Step 4: Verify GitHub automation**

Confirm the test workflow passes, the deploy workflow pushes the intended source revision, and the result workflow no longer warns that a missing football-data token disables ingestion.

- [ ] **Step 5: Verify the live runtime**

Check the Hugging Face API and Space `/config`: runtime stage is `RUNNING`, deployed revision matches the pushed content, the stale-results banner is absent, the Track Record aggregate shows 65/72 verified coverage, and no played group match appears as upcoming.
