# Visitor-Facing Forecasting UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the Space immediately understandable to curious visitors by separating the interactive historical challenge from verified World Cup evidence, clarifying the user journey, and applying one consistent visual language.

**Architecture:** Keep forecasting engines, frozen prediction artifacts and scoring calculations unchanged. Add presentation helpers in the existing UI modules, rename the two visitor journeys at the Gradio tab level, and scope the new visual treatment to these surfaces. Use rendered-HTML tests for copy, ordering and styling hooks, then deploy the exact Git commit through the existing GitHub-to-Hugging-Face workflow.

**Tech Stack:** Python 3.14, Gradio Blocks, custom HTML strings, CSS in src/underdog_lab/ui/theme.py, pytest, Ruff, GitHub Actions, Hugging Face Spaces.

## Global Constraints

- Do not modify model parameters, frozen forecast artifacts, result snapshots, score definitions or historical match data.
- Preserve the distinction between the 20-match historical Challenge dataset and the 72-fixture World Cup Track Record.
- Keep the local scenario extractor and its fallback behavior unchanged.
- Keep log loss, Brier and RPS visible; do not replace them with accuracy-only messaging.
- Keep primary actions red, secondary actions outlined, and reserve pill shapes for compact status/metric badges.
- Every UI behavior change requires a failing test before production code.
- Deploy only to sammoftah/World-Cup-2026-prediction through .github/workflows/deploy-space.yml.

---

### Task 1: Establish the visitor information architecture and copy

**Files:**
- Modify: src/underdog_lab/ui/app.py around the Gradio tab declarations
- Test: tests/unit/test_world_cup_2026.py

**Interfaces:**
- Consumes existing repository, world_cup_repository, track_record_html and Gradio callbacks.
- Produces visitor_tab_copy(), plus the tab names and introductory copy used by later tasks.

- [ ] Write a failing test for visitor_tab_copy().

Use this exact assertion shape:

    def test_visitor_journeys_use_distinct_names_and_explanations():
        copy = visitor_tab_copy()
        assert copy["challenge_title"] == "Beat the Model"
        assert copy["evidence_title"] == "Evidence"
        assert "frozen before kickoff" in copy["evidence_intro"]

Run:

    PYTHONPATH=.:src pytest -q tests/unit/test_world_cup_2026.py -k visitor

Expected: FAIL because visitor_tab_copy is absent.

- [ ] Implement visitor_tab_copy() in src/underdog_lab/ui/app.py.

It must return:

    {
        "challenge_title": "Beat the Model",
        "challenge_intro": (
            "Test whether new information should change a football forecast. "
            "Choose a past match, add evidence, commit your probabilities, then reveal the result."
        ),
        "evidence_title": "Evidence",
        "evidence_intro": (
            "Every World Cup forecast below was frozen before kickoff and scored "
            "against the result. Proper scoring rules are the main evidence; "
            "accuracy is a secondary, easier-to-read summary."
        ),
    }

Rename the Gradio tabs from Challenge to Beat the Model and Track Record to Evidence. Add the matching intro copy before each surface.

- [ ] Run the focused test and confirm PASS.

    PYTHONPATH=.:src pytest -q tests/unit/test_world_cup_2026.py -k visitor

- [ ] Commit:

    git add src/underdog_lab/ui/app.py tests/unit/test_world_cup_2026.py
    git commit -m "feat: clarify visitor forecasting journeys"

### Task 2: Restructure the historical Challenge as a four-step learning flow

**Files:**
- Modify: src/underdog_lab/ui/app.py around the current Challenge tab
- Modify: src/underdog_lab/ui/components.py
- Modify: src/underdog_lab/ui/theme.py
- Test: tests/unit/test_world_cup_2026.py

**Interfaces:**
- Consumes select_match(), run_scenario(), reveal(), forecast_html() and existing scoring callbacks.
- Produces challenge_intro_html() and stable challenge-panel CSS hooks.
- Does not change callback signatures or score calculations.

- [ ] Write failing tests for the four-step copy.

    def test_challenge_intro_explains_the_four_step_flow():
        html = challenge_intro_html()
        assert "Beat the Model" in html
        assert "Choose a past match" in html
        assert "Add evidence" in html
        assert "Commit probabilities" in html
        assert "Reveal the result" in html

- [ ] Implement challenge_intro_html() in src/underdog_lab/ui/components.py.

Use one ordered four-step block with these exact concepts:

    1. Choose a past match — the result stays hidden.
    2. Add evidence — describe an injury, suspension or supported factor.
    3. Commit probabilities — home, draw and away total 100%.
    4. Reveal the result — compare baseline, scenario and user forecast.

Rename controls:
- Hidden historical match -> Choose a past match
- What changes before kickoff? -> Add evidence before kickoff
- Translate scenario -> Apply evidence
- Lock forecast and reveal result -> Commit forecast and reveal result
- Add info text: The final score is hidden until you commit your forecast.

Wrap the historical controls and result cards in challenge-panel. Keep the baseline, scenario, sliders and reveal output visible, but make the four-step intro the first thing a visitor reads.

- [ ] Run:

    PYTHONPATH=.:src pytest -q tests/unit/test_world_cup_2026.py -k challenge

Expected: PASS.

- [ ] Commit:

    git add src/underdog_lab/ui/app.py src/underdog_lab/ui/components.py src/underdog_lab/ui/theme.py tests/unit/test_world_cup_2026.py
    git commit -m "feat: turn historical challenge into guided flow"

### Task 3: Present Track Record as evidence, not another historical game

**Files:**
- Modify: src/underdog_lab/ui/app.py in track_record_html()
- Modify: src/underdog_lab/ui/theme.py
- Test: tests/unit/test_prediction_scorecard.py

**Interfaces:**
- Consumes scored_track_records() without changing its calculations.
- Produces evidence_summary_html(records) and clearer retrospective labeling.

- [ ] Write a failing evidence-summary test.

    def test_evidence_summary_explains_freezing_and_proper_scores():
        html = evidence_summary_html({
            "coverage": {"completed": 72, "scored": 65, "rate": 65 / 72, "excluded": 7}
        })
        assert "frozen before kickoff" in html
        assert "65 / 72" in html
        assert "Log loss, Brier and RPS" in html
        assert "Excluded forecasts stay visible" in html

- [ ] Implement evidence_summary_html(records) in app.py.

The opening card must say:
- What did the model say before kickoff?
- 65 / 72 completed matches have eligible forecasts.
- Log loss, Brier and RPS are the primary evidence.
- Excluded forecasts stay visible and are never silently backfilled.

Preserve all existing horizon sections, row-level probabilities, excluded fixture IDs and the prospective/retrospective distinction. Add the label Retrospective diagnostic — not prospective evidence to the current-model replay section.

- [ ] Add a heading-order test:

    html = track_record_html(TournamentRepository())
    assert html.index("What did the model say before kickoff?") < html.index("All verified pre-kickoff predictions")
    assert "Retrospective diagnostic" in html

- [ ] Run and commit:

    PYTHONPATH=.:src pytest -q tests/unit/test_prediction_scorecard.py -k evidence
    git add src/underdog_lab/ui/app.py src/underdog_lab/ui/theme.py tests/unit/test_prediction_scorecard.py
    git commit -m "feat: frame track record as forecasting evidence"

### Task 4: Normalize buttons, tags and radius tokens

**Files:**
- Modify: src/underdog_lab/ui/theme.py
- Modify: src/underdog_lab/ui/components.py
- Test: tests/unit/test_world_cup_2026.py

**Interfaces:**
- Consumes primary-button, secondary-button, metric-pill, factor-chip and lab-card.
- Produces journey-intro, journey-steps, challenge-panel, evidence-coverage and status-chip styles.

- [ ] Write the CSS contract test:

    def test_ui_uses_pills_only_for_compact_status_and_keeps_controls_consistent():
        css = Path("src/underdog_lab/ui/theme.py").read_text(encoding="utf-8")
        assert ".challenge-panel" in css
        assert ".journey-intro" in css
        assert ".status-chip" in css
        assert ".metric-pill" in css
        assert ".factor-chip" in css

- [ ] Add radius tokens:

    --radius-xs: 6px;
    --radius-control: 8px;
    --radius-card: 12px;
    --radius-pill: 999px;

Use radius-pill only for metric-pill, cutoff-badge, versus and status-chip. Use radius-control for buttons, inputs, dropdowns and factor-chip. Use radius-card for content cards.

Add a four-column journey-steps grid, a red-accented journey-intro card and a rectangular evidence block. At max-width 760px, collapse journey-steps to two columns.

Change the global button radius from radius-md to radius-control. Keep the existing red primary button and outlined secondary button colors. Remove the pill-like treatment from factor-chip; keep its blue-soft background and left status border.

- [ ] Run:

    PYTHONPATH=.:src pytest -q tests/unit/test_world_cup_2026.py -k "visitor or challenge"
    ruff check src/underdog_lab/ui/app.py src/underdog_lab/ui/components.py src/underdog_lab/ui/theme.py tests/unit/test_world_cup_2026.py
    git diff --check

Expected: all tests pass, changed-file Ruff is clean and the diff has no whitespace errors.

- [ ] Commit:

    git add src/underdog_lab/ui/theme.py src/underdog_lab/ui/components.py tests/unit/test_world_cup_2026.py
    git commit -m "style: unify visitor-facing controls and cards"

### Task 5: Run the complete verification gate and inspect rendered output

**Files:**
- Modify: none unless a verification failure identifies a regression.
- Test: full test suite and rendered HTML smoke checks.

- [ ] Run:

    PYTHONPATH=.:src pytest -q
    ruff check src/underdog_lab/ui/app.py src/underdog_lab/ui/components.py src/underdog_lab/ui/theme.py tests/unit/test_world_cup_2026.py tests/unit/test_prediction_scorecard.py
    git diff --check

Expected: full suite passes, changed-file Ruff is clean and diff check passes.

- [ ] Run this smoke check:

    PYTHONPATH=.:src python3 - <<'PY'
    from underdog_lab.ui.components import challenge_intro_html
    from underdog_lab.ui.app import track_record_html, world_cup_repository
    challenge = challenge_intro_html()
    evidence = track_record_html(world_cup_repository)
    assert "Beat the Model" in challenge
    assert "Choose a past match" in challenge
    assert "What did the model say before kickoff?" in evidence
    assert "Retrospective diagnostic" in evidence
    print("visitor UI smoke checks passed")
    PY

- [ ] Commit the verified release:

    git add src tests
    git commit -m "feat: clarify forecasting experience for visitors"

### Task 6: Deploy and verify the personal Hugging Face Space

**Files:**
- Verify: .github/workflows/deploy-space.yml
- Verify: scripts/verify_space_revision.py
- Modify: none.

**Interfaces:**
- Consumes the merged main commit and existing HF_TOKEN GitHub secret.
- Produces a running Space whose repository SHA and runtime SHA match main.

- [ ] Push:

    git push origin main

The workflow pushes the exact Git revision to sammoftah/World-Cup-2026-prediction. Do not create a separate Space-only commit.

- [ ] Watch deployment:

    DEPLOY_RUN=$(gh run list --repo OsamaMoftah/World-Cup-2026-prediction --workflow deploy-space.yml --limit 1 --json databaseId --jq '.[0].databaseId')
    gh run watch "$DEPLOY_RUN" --repo OsamaMoftah/World-Cup-2026-prediction --exit-status

Expected: deploy and Verify deployed runtime revision succeed.

- [ ] Verify runtime:

    python3 scripts/verify_space_revision.py \
      --space sammoftah/World-Cup-2026-prediction \
      --expected "$(git rev-parse HEAD)" \
      --url https://sammoftah-world-cup-2026-prediction.hf.space \
      --timeout 600

Expected: the JSON status is deployed and the returned sha equals the value printed by git rev-parse HEAD.

- [ ] Verify live Gradio config contains the tab names Beat the Model and Evidence, and invoke the live endpoint to confirm the new intro copy is present. Record the Space URL and workflow run in the handoff.

## Self-review checklist

- Challenge and Track Record are separate in naming and explanation.
- The 20 historical Challenge matches are not presented as 2026 evidence.
- The 72-fixture World Cup scorecard remains frozen and mathematically unchanged.
- New copy explains proper scores without overclaiming accuracy.
- Buttons, chips, cards and tables use a consistent radius hierarchy.
- Mobile layout collapses the four-step explanation to two columns.
- Local tests, changed-file lint, whitespace checks and live runtime verification are required before completion.
