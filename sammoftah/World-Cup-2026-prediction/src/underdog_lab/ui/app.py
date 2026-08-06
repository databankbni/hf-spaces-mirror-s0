from __future__ import annotations

import html
import json
from functools import lru_cache
from pathlib import Path

import gradio as gr
from gradio.themes import Soft

from underdog_lab.data.repository import MatchRepository
from underdog_lab.domain import Forecast
from underdog_lab.release.health import application_health
from underdog_lab.scenarios.adjustments import RULES, apply_extraction
from underdog_lab.scenarios.factory import build_extractor
from underdog_lab.scenarios.schemas import ScenarioExtraction
from underdog_lab.service import analyze_scenario, baseline_forecast
from underdog_lab.telemetry.traces import append_trace
from underdog_lab.ui.components import (
    challenge_intro_html,
    derived_away_html,
    evidence_summary_html,
    factors_html,
    forecast_html,
    hero_html,
    match_html,
    research_cta_html,
    research_section_html,
    research_stat_row_html,
    reveal_html,
    visitor_tab_copy,
)
from underdog_lab.world_cup.comparison import (
    match_comparison_html,
    tournament_benchmark_html,
    tournament_comparison_html,
)
from underdog_lab.world_cup.data import TournamentRepository
from underdog_lab.world_cup.flags import team_label
from underdog_lab.world_cup.forecasting import match_forecast
from underdog_lab.world_cup.predictions import scored_track_records
from underdog_lab.world_cup.provenance import forecast_provenance
from underdog_lab.world_cup.simulation import simulate_tournament
from underdog_lab.world_cup.ui import (
    all_fixtures_html,
    awards_html,
    fixture_as_match,
    fixture_label,
    group_html,
    overdue_results_note,
    tournament_probabilities_html,
    upcoming_html,
)


repository = MatchRepository()
world_cup_repository = TournamentRepository()
extractor = build_extractor()
labels = repository.labels()
world_cup_fixtures = {
    fixture_label(fixture): fixture
    for fixture in world_cup_repository.fixtures
    if not fixture.played
}
world_cup_labels = list(world_cup_fixtures)

if hasattr(extractor, "warmup"):
    extractor.warmup()


@lru_cache(maxsize=64)
def _analyze_cached(match_id: str, text: str) -> tuple[dict, dict, dict, str, str | None]:
    match = repository.get(match_id)
    extraction, result, forecast = analyze_scenario(match, text, extractor)
    return (
        extraction.model_dump(mode="json"),
        result.model_dump(mode="json"),
        forecast.model_dump(mode="json"),
        getattr(extractor, "last_backend", extractor.name),
        getattr(extractor, "last_error", None),
    )


def select_match(label: str):
    match = repository.by_label(label)
    baseline = baseline_forecast(match)
    return (
        match.match_id,
        baseline.model_dump(mode="json"),
        baseline.model_dump(mode="json"),
        match_html(match),
        forecast_html(baseline, match, "Baseline forecast"),
        factors_html(ScenarioExtraction(), apply_extraction(match, ScenarioExtraction())),
        forecast_html(baseline, match, "Scenario forecast"),
        "",
        derived_away_html(45, 25),
    )


def run_scenario(label: str, text: str):
    match = repository.by_label(label)
    baseline = baseline_forecast(match)
    try:
        (
            extraction_data,
            result_data,
            forecast_data,
            actual_backend,
            backend_error,
        ) = _analyze_cached(
            match.match_id, text.strip()
        )
        extraction = ScenarioExtraction.model_validate(extraction_data)
        from underdog_lab.scenarios.schemas import AdjustmentResult

        result = AdjustmentResult.model_validate(result_data)
        adjusted = Forecast.model_validate(forecast_data)
    except Exception as error:
        actual_backend = "scenario pipeline error"
        backend_error = f"{type(error).__name__}: {error}"
        fallback = ScenarioExtraction(
            unsupported_claims=[f"Extractor unavailable: {type(error).__name__}"]
        )
        result = apply_extraction(match, fallback)
        extraction = fallback
        adjusted = baseline

    append_trace(
        {
            "event": "scenario_analyzed",
            "match_id": match.match_id,
            "extractor": extractor.name,
            "actual_backend": actual_backend,
            "backend_error": backend_error,
            "scenario": text,
            "extraction": extraction.model_dump(mode="json"),
            "forecast": adjusted.model_dump(mode="json"),
        }
    )
    return (
        adjusted.model_dump(mode="json"),
        factors_html(
            extraction,
            result,
            backend=actual_backend,
            backend_error=backend_error,
        ),
        forecast_html(adjusted, match, "Scenario forecast", comparison=baseline),
        "",
    )


def select_world_cup_group(group: str) -> str:
    return group_html(world_cup_repository, group)


def update_world_cup_upcoming(mode: str) -> str:
    return upcoming_html(world_cup_repository, mode=mode)


def select_world_cup_fixture(label: str):
    fixture = world_cup_fixtures[label]
    match = fixture_as_match(fixture, world_cup_repository)
    baseline = match_forecast(fixture, world_cup_repository.team_by_name)
    return (
        forecast_html(baseline, match, "2026 baseline forecast"),
        factors_html(
            ScenarioExtraction(),
            apply_extraction(match, ScenarioExtraction()),
        ),
        forecast_html(baseline, match, "Scenario forecast"),
        match_comparison_html(fixture, baseline),
    )


def run_world_cup_scenario(label: str, text: str):
    fixture = world_cup_fixtures[label]
    match = fixture_as_match(fixture, world_cup_repository)
    baseline = match_forecast(fixture, world_cup_repository.team_by_name)
    try:
        extraction, result, adjusted = analyze_scenario(
            match,
            text.strip(),
            extractor,
        )
        actual_backend = getattr(extractor, "last_backend", extractor.name)
        backend_error = getattr(extractor, "last_error", None)
    except Exception as error:
        actual_backend = "scenario pipeline error"
        backend_error = f"{type(error).__name__}: {error}"
        extraction = ScenarioExtraction(
            unsupported_claims=[f"Extractor unavailable: {type(error).__name__}"]
        )
        result = apply_extraction(match, extraction)
        adjusted = baseline
    append_trace(
        {
            "event": "world_cup_scenario_analyzed",
            "fixture_id": fixture.fixture_id,
            "actual_backend": actual_backend,
            "backend_error": backend_error,
            "scenario": text,
            "forecast": adjusted.model_dump(mode="json"),
        }
    )
    return (
        factors_html(
            extraction,
            result,
            backend=actual_backend,
            backend_error=backend_error,
        ),
        forecast_html(
            adjusted,
            match,
            "Scenario forecast (experimental)",
            comparison=baseline,
        ),
    )


def update_user_forecast(home: float, draw: float) -> str:
    return derived_away_html(home, draw)


def reveal(
    label: str,
    baseline_state: dict,
    adjusted_state: dict,
    home: float,
    draw: float,
) -> str:
    match = repository.by_label(label)
    baseline = Forecast.model_validate(baseline_state)
    adjusted = Forecast.model_validate(adjusted_state)
    output = reveal_html(match, baseline, adjusted, home, draw)
    append_trace(
        {
            "event": "forecast_revealed",
            "match_id": match.match_id,
            "user_home": home,
            "user_draw": draw,
            "user_away": 100.0 - home - draw,
        }
    )
    return output


def _legacy_track_record_section(title: str, description: str, summary: dict) -> str:
    """Full row-level detail table for one scored group (used inside a
    collapsible <details> block so the raw data stays available without
    competing with the editorial summary above it)."""
    rows = "".join(
        "<tr>"
        f"<td>{row['fixture_id']}</td><td>{team_label(row['home'])}</td>"
        f"<td>{row['score']}</td><td>{team_label(row['away'])}</td>"
        f"<td class='r-num'>{row['p_home']:.1%}</td><td class='r-num'>{row['p_draw']:.1%}</td>"
        f"<td class='r-num'>{row['p_away']:.1%}</td><td class='r-num'>{row['log_loss']:.3f}</td>"
        f"<td class='r-num'>{row['brier']:.3f}</td><td class='r-num'>{row['rps']:.3f}</td></tr>"
        for row in summary["rows"]
    )
    if not rows:
        rows = "<tr><td colspan='10'>No matches in this group yet.</td></tr>"
    metrics = (
        (
            f"{summary['accuracy']:.1%}",
            f"{summary['mean_log_loss']:.3f}",
            f"{summary['mean_brier']:.3f}",
            f"{summary['mean_rps']:.3f}",
            f"{summary['log_loss_skill_vs_uniform']:+.1%}",
        )
        if summary["n"]
        else ("-", "-", "-", "-", "-")
    )
    sample_note = (
        "Fewer than 30 matches so far: a useful early signal, but too "
        "small to call a stable accuracy rate yet."
        if summary["n"] < 30
        else "Large enough for a descriptive comparison, while still "
        "subject to tournament-specific sample uncertainty."
    )
    skill_note = (
        "Positive skill means lower (better) log loss than equal 1/3 odds; "
        "negative skill means worse."
    )
    return f"""
    <details class="r-details">
      <summary><strong>{html.escape(title)}</strong> &mdash; {html.escape(description)}</summary>
      <div class="r-statrow" style="margin-top:12px">
        <div><div class="r-k">Matches</div><div class="r-v">{summary['n']}</div></div>
        <div><div class="r-k">Top-pick accuracy</div><div class="r-v">{metrics[0]}</div></div>
        <div><div class="r-k">Mean log loss</div><div class="r-v">{metrics[1]}</div></div>
        <div><div class="r-k">Mean Brier / RPS</div><div class="r-v">{metrics[2]} / {metrics[3]}</div></div>
        <div><div class="r-k">Skill vs equal odds</div><div class="r-v">{metrics[4]}</div></div>
        <div><div class="r-k">Equal-odds baseline</div><div class="r-v">{summary['uniform_log_loss']:.3f}</div></div>
      </div>
      <p class="r-note">{skill_note} {sample_note}</p>
      <div class="table-scroll"><table class="r-table">
        <thead><tr><th>ID</th><th>Home</th><th>Score</th><th>Away</th>
        <th class="r-num">1</th><th class="r-num">X</th><th class="r-num">2</th>
        <th class="r-num">Log loss</th><th class="r-num">Brier</th><th class="r-num">RPS</th></tr></thead>
        <tbody>{rows}</tbody>
      </table></div>
    </details>
    """


def track_record_html(repository) -> str:
    records = scored_track_records(
        repository.tournament_fixtures, repository.team_by_name
    )
    summary = records["prospective"]
    coverage = records["coverage"]

    intro = evidence_summary_html(records)

    # Section 1 — the live, prospective track record: every pre-registered
    # forecast, scored once its match completed.
    rows_html = "".join(
        f"<tr><td>{row['fixture_id']}</td>"
        f"<td>{team_label(row['home'])} {row['score']} {team_label(row['away'])}</td>"
        f"<td class='r-num'>{row['p_home']:.1%}</td><td class='r-num'>{row['p_draw']:.1%}</td>"
        f"<td class='r-num'>{row['p_away']:.1%}</td><td class='r-num'>{row['log_loss']:.3f}</td>"
        f"<td class='r-num'>{row['brier']:.3f}</td><td class='r-num'>{row['rps']:.3f}</td></tr>"
        for row in summary["rows"]
    ) or "<tr><td colspan='8'>No matches scored yet.</td></tr>"
    exclusion_note = (
        f"{coverage['excluded']} completed fixtures are excluded because no "
        f"verified pre-kickoff artifact exists for them "
        f"({coverage['exclusion_reason'].replace('_', ' ')}) &mdash; they are "
        f"listed, not hidden. Coverage: "
        f"{coverage['rate']:.1%}." if coverage['rate'] is not None else ""
    )
    section1_body = (
        research_stat_row_html(
            [
                ("Matches scored", str(summary["n"]), f"of {coverage['completed']} completed"),
                (
                    "Top-pick accuracy",
                    f"{summary['accuracy']:.1%}" if summary["n"] else "&mdash;",
                    "vs 33.3% random",
                ),
                (
                    "Mean log loss",
                    f"{summary['mean_log_loss']:.3f}" if summary["n"] else "&mdash;",
                    f"uniform baseline {summary['uniform_log_loss']:.3f} &middot; lower is better",
                ),
                (
                    "Mean Brier / RPS",
                    (
                        f"{summary['mean_brier']:.3f} / {summary['mean_rps']:.3f}"
                        if summary["n"]
                        else "&mdash;"
                    ),
                    "lower is better",
                ),
            ]
        )
        + f'<p class="r-note">{exclusion_note}</p>'
        + f"""<div class="table-scroll"><table class="r-table">
          <thead><tr><th>ID</th><th>Match</th><th class="r-num">1</th><th class="r-num">X</th>
          <th class="r-num">2</th><th class="r-num">Log loss</th><th class="r-num">Brier</th>
          <th class="r-num">RPS</th></tr></thead>
          <tbody>{rows_html}</tbody>
        </table></div>"""
    )
    section1 = research_section_html(
        1,
        "The live track record",
        "Forecasts locked before kickoff during World Cup 2026, scored on the final result.",
        section1_body,
    )

    # Section 2 — same record, split by how far ahead of kickoff each
    # forecast was locked. Row-level detail lives in Section 1 already, so
    # this stays a compact comparison instead of repeating every match.
    horizon_titles = {
        "final": "Within 2 hours of kickoff",
        "6h": "2–6 hours before kickoff",
        "24h": "6–24 hours before kickoff",
        "long_range": "More than a day before kickoff",
    }
    horizon_order = ("long_range", "24h", "6h", "final")
    horizon_rows = []
    for horizon in horizon_order:
        horizon_summary = records["prospective_by_horizon"].get(horizon)
        if not horizon_summary or not horizon_summary["n"]:
            continue
        widest = max(
            (
                s["mean_log_loss"]
                for s in records["prospective_by_horizon"].values()
                if s["n"]
            ),
            default=1.0,
        )
        bar_pct = min(100, round(100 * horizon_summary["mean_log_loss"] / widest)) if widest else 0
        bar_class = "r-gray" if horizon_summary["n"] < 10 else ""
        horizon_rows.append(
            f"<tr><td>{html.escape(horizon_titles.get(horizon, horizon))}</td>"
            f"<td class='r-num'>{horizon_summary['n']}</td>"
            f"<td class='r-num'>{horizon_summary['accuracy']:.1%}</td>"
            f"<td class='r-num'>{horizon_summary['mean_log_loss']:.3f}</td>"
            f"<td><div class='r-bar {bar_class}'><i style='width:{bar_pct}%'></i></div></td></tr>"
        )
    section2_body = f"""
    <table class="r-table">
      <thead><tr><th>Locked</th><th class="r-num">Matches</th><th class="r-num">Accuracy</th>
      <th class="r-num">Mean log loss</th><th>vs. uniform {summary['uniform_log_loss']:.3f}</th></tr></thead>
      <tbody>{''.join(horizon_rows) or '<tr><td colspan="5">No horizon data yet.</td></tr>'}</tbody>
    </table>
    <p class="r-note">Any bucket with fewer than 30 matches is a useful early
    signal, not a stable rate &mdash; several horizons here are tiny samples,
    shown for completeness rather than as evidence either way.</p>
    """
    section2 = research_section_html(
        2,
        "How far ahead were the calls made?",
        "The same 65 forecasts, split by how long before kickoff each one was locked in.",
        section2_body,
    )

    # Section 3 — the walk-forward backtest run before the model shipped.
    backtest_path = Path("models/backtest_report.json")
    section3 = ""
    if backtest_path.exists():
        backtest = json.loads(backtest_path.read_text(encoding="utf-8"))
        fitted = backtest["overall_mean_scores"]["fitted"]
        current = backtest["overall_mean_scores"]["current"]
        uniform = backtest["overall_mean_scores"]["uniform"]
        test_years = backtest.get("test_years") or []
        year_range = f"{min(test_years)}–{max(test_years)}" if test_years else ""
        widest3 = max(fitted["log_loss"], current["log_loss"], uniform["log_loss"]) or 1.0
        section3_body = f"""
        <p class="r-sub" style="margin-top:-8px">The model was fitted on real
        historical matches and tested on {backtest['total_test_matches']:,}
        held-out matches across {year_range} folds it had never seen.</p>
        <table class="r-table">
          <thead><tr><th>Model</th><th class="r-num">Log loss</th>
          <th class="r-num">Brier</th><th class="r-num">RPS</th>
          <th>Log loss (lower is better)</th></tr></thead>
          <tbody>
            <tr><td><strong>Shipped model</strong></td>
            <td class="r-num">{fitted['log_loss']:.3f}</td>
            <td class="r-num">{fitted['brier']:.3f}</td>
            <td class="r-num">{fitted['rps']:.3f}</td>
            <td><div class="r-bar"><i style="width:{100 * fitted['log_loss'] / widest3:.0f}%"></i></div></td></tr>
            <tr><td>Previous hand-set model</td>
            <td class="r-num">{current['log_loss']:.3f}</td>
            <td class="r-num">{current['brier']:.3f}</td>
            <td class="r-num">{current['rps']:.3f}</td>
            <td><div class="r-bar r-gray"><i style="width:{100 * current['log_loss'] / widest3:.0f}%"></i></div></td></tr>
            <tr><td>Uniform &#8531; / &#8531; / &#8531;</td>
            <td class="r-num">{uniform['log_loss']:.3f}</td>
            <td class="r-num">{uniform['brier']:.3f}</td>
            <td class="r-num">{uniform['rps']:.3f}</td>
            <td><div class="r-bar r-gray"><i style="width:100%"></i></div></td></tr>
          </tbody>
        </table>
        <div class="r-src">Source: models/backtest_report.json &middot; every
        fold predicts matches after its training window.</div>
        """
        section3 = research_section_html(
            3,
            "Before it went live: the walk-forward backtest",
            "Tested against real results before a single 2026 forecast was made.",
            section3_body,
        )

    # Section 4 — biggest misses (real rows from Section 1) and the
    # calibration adjustment, side by side.
    worst = sorted(summary["rows"], key=lambda row: -row["log_loss"])[:5]
    miss_row_html = []
    for row in worst:
        outcome_probability = row[f"p_{row['outcome']}"]
        miss_row_html.append(
            f"<tr><td>{team_label(row['home'])} &ndash; {team_label(row['away'])}</td>"
            f"<td>{row['score']}</td>"
            f"<td class='r-num'>{outcome_probability:.1%}</td>"
            f"<td class='r-num'>{row['log_loss']:.2f}</td></tr>"
        )
    misses_rows = "".join(miss_row_html) or "<tr><td colspan='4'>No scored matches yet.</td></tr>"
    calibration_path = Path("models/recalibration_evaluation.json")
    calibration_body = ""
    if calibration_path.exists():
        calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
        temperature = calibration["fitted_temperature"]
        selection_years = calibration.get("selection_years") or []
        confirmation_year = calibration.get("confirmation_year")
        calibration_body = f"""
        <div class="r-statrow" style="grid-template-columns:1fr 1fr">
          <div><div class="r-k">Temperature</div><div class="r-v">T = {temperature:.3f}</div>
          <div class="r-s">T &lt; 1 sharpens the raw forecasts</div></div>
          <div><div class="r-k">Validation</div><div class="r-v">2-stage</div>
          <div class="r-s">selection folds {min(selection_years) if selection_years else ''}
          &ndash;{max(selection_years) if selection_years else ''}, confirmed on
          held-out {confirmation_year}</div></div>
        </div>
        <div class="r-callout"><strong>Why no calibration curve?</strong> A
        reliability plot needs more scored matches per probability bucket
        than one live tournament provides. Rather than draw a curve from
        thin bins, we report the validated temperature and will publish the
        curve once the sample supports it.</div>
        """
    section4_body = f"""
    <div class="r-grid2">
      <div>
        <table class="r-table">
          <thead><tr><th>Match</th><th>Result</th><th class="r-num">P(outcome)</th>
          <th class="r-num">Log loss</th></tr></thead>
          <tbody>{misses_rows}</tbody>
        </table>
        <p class="r-note">Pattern: heavy favorites held to low-scoring draws.
        The model prices these low, not at zero &mdash; that is how
        probabilistic forecasts are supposed to fail.</p>
      </div>
      <div>{calibration_body}</div>
    </div>
    """
    section4 = research_section_html(
        4,
        "Where the model missed, and how it's calibrated",
        "The five worst live misses by log loss, and what we adjusted after fitting.",
        section4_body,
    )

    retrospective_details = _legacy_track_record_section(
        "Retrospective diagnostic — not prospective evidence",
        "Re-runs the current model over every match played so far, using "
        "today's ratings. Useful for 'how good is the current model', not "
        "as a record of pre-match predictions.",
        records["retrospective"],
    )
    section5 = research_section_html(
        5,
        "Retrospective diagnostic",
        "A different question from the track record above: how would today's model score if it replayed every match so far?",
        retrospective_details,
    )

    return intro + section1 + section2 + section3 + section4 + section5


def model_summary_html() -> str:
    backtest = json.loads(Path("models/backtest_report.json").read_text(encoding="utf-8"))
    fitted = backtest["overall_mean_scores"]["fitted"]
    previous = backtest["overall_mean_scores"]["current"]
    comparison = (
        "a little sharper than the previous version"
        if fitted["log_loss"] < previous["log_loss"]
        else "about the same as the previous version"
    )
    return f"""
    <section class="lab-card" style="border-color:rgba(178,34,52,.25)">
      <div class="eyebrow">Why trust these numbers?</div>
      <h2>Checked against {backtest['total_test_matches']:,} real matches before going live</h2>
      <p class="context">The baseline forecast comes from Dixon-Coles, a
      well-known statistical model for football scorelines, fitted on each
      team's Elo rating. Before shipping it, we tested it on
      {backtest['total_test_matches']:,} real matches from 2018-2026, always
      predicting games it hadn't seen the result of yet. This version came
      out {comparison}.</p>
      <p class="small">Want the exact numbers, what we tried and didn't ship,
      and how we keep our own track record honest? Open the
      <strong>Methodology</strong> tab.</p>
    </section>
    """


def methodology_html() -> str:
    backtest = json.loads(Path("models/backtest_report.json").read_text(encoding="utf-8"))
    ship = json.loads(Path("results/ship_decision.json").read_text(encoding="utf-8"))
    fitted = backtest["overall_mean_scores"]["fitted"]
    previous = backtest["overall_mean_scores"]["current"]
    neutral = backtest["neutral_mean_scores"]

    live_path = Path("predictions/live/2026-06-13T190000Z-WC26-008")
    live = json.loads((live_path / "forecast.json").read_text(encoding="utf-8"))
    manifest = json.loads((live_path / "manifest.json").read_text(encoding="utf-8"))
    live_fixture = live["fixtures"][0]

    health = application_health()
    provenance = forecast_provenance()

    evaluation_path = repository.path.parents[1] / "scenarios" / "evaluation.json"
    metrics = (
        json.loads(evaluation_path.read_text(encoding="utf-8"))
        if evaluation_path.exists()
        else {}
    )
    tuned = ship.get("tuned_model", {})

    intro = """
    <section class="lab-card">
      <div class="eyebrow">Methodology &amp; receipts</div>
      <h2>How this works, and how we keep ourselves honest</h2>
      <p class="context">This tab is for the curious: the model behind the
      numbers, the benchmarks, the experiments we tried and didn't ship, and
      how we audit our own predictions so results can't be quietly rewritten
      after the fact.</p>
    </section>
    """

    numbers = f"""
    <section class="lab-card">
      <h3>The numbers behind "tested against real matches"</h3>
      <div class="score-grid">
        <div class="score-box"><span>Matches tested</span><strong>{backtest['total_test_matches']:,}</strong><span class="small">2018-2026, walk-forward</span></div>
        <div class="score-box"><span>Log loss now</span><strong>{fitted['log_loss']:.3f}</strong><span class="small">was {previous['log_loss']:.3f}</span></div>
        <div class="score-box"><span>Neutral-venue log loss</span><strong>{neutral['fitted']['log_loss']:.3f}</strong><span class="small">was {neutral['current']['log_loss']:.3f}</span></div>
      </div>
      <p class="small">Log loss measures how well the predicted probabilities
      matched what actually happened: lower means better-calibrated
      confidence. "Walk-forward" means every test prediction was made without
      letting the model see that match's result first.</p>
    </section>
    """

    live_proof = f"""
    <section class="lab-card">
      <h3>A prediction we can't take back</h3>
      <p class="context">To prove forecasts aren't adjusted after the fact,
      every prediction gets frozen and fingerprinted before kickoff. Take
      <strong>{html.escape(live_fixture['home'])} vs
      {html.escape(live_fixture['away'])}</strong>: we froze
      {live_fixture['p_home']:.0%} / {live_fixture['p_draw']:.0%} /
      {live_fixture['p_away']:.0%} at
      {live['generated_at'][:16].replace('T', ' ')} UTC, ahead of its
      {live_fixture['kickoff_utc'][11:16]} UTC kickoff. The fingerprint
      (<code>{manifest['sha256'][:16]}…</code>) is sitting in the repo, so
      anyone can check it wasn't touched afterwards.</p>
    </section>
    """

    ai_card_class = "lab-card warn" if ship.get("ship_decision") == "NO-SHIP" else "lab-card"
    ai_experiment = f"""
    <section class="{ai_card_class}">
      <h3>An AI experiment that didn't make the cut</h3>
      <p class="context">The "scenario reader" (the part that turns "star
      striker is out" into a number) is a small 360M-parameter language model
      running locally; nothing you type leaves this app. We tried fine-tuning
      a custom version on football-specific examples. It got better at
      recognising the right category of news, but its confidence scores came
      out unreliable, so our own safety check failed it
      (<strong>{html.escape(ship.get('ship_decision', 'PENDING'))}</strong>:
      {html.escape(ship.get('reason', ''))}). The app falls back to the
      original model plus a rule-based backup instead. Either way, the AI
      only ever reads the news; the statistics still decide the odds.</p>
      <div class="score-grid" style="margin-top:1rem">
        <div class="score-box"><span>Base model</span><strong>{metrics.get('factor_micro_f1', 0):.3f}</strong><span class="small">factor micro-F1</span></div>
        <div class="score-box{' warn' if tuned else ''}"><span>Fine-tuned attempt</span><strong>{tuned.get('factor_micro_f1', 0):.3f}</strong><span class="small">factor micro-F1</span></div>
        <div class="score-box"><span>Runtime</span><strong>{html.escape(extractor.name)}</strong><span class="small">swappable backend</span></div>
      </div>
    </section>
    """

    rejected = """
    <section class="lab-card">
      <h3>Other things we tried and didn't keep</h3>
      <ul class="context">
        <li><strong>A "host nation" bonus.</strong> Testing whether host
        teams deserve an Elo boost was inconclusive, so we removed the
        heuristic rather than guess.</li>
        <li><strong>A tournament-opener draw adjustment.</strong> Failed its
        historical check, so it's not applied.</li>
        <li><strong>Betting-market odds.</strong> Not used for our own
        forecasts yet. The Compare tab shows them for context, but they'd
        need to pass the same testing as everything else here before feeding
        into our model.</li>
      </ul>
    </section>
    """

    factor_rows = "".join(
        f"<tr><td>{html.escape(factor.value.replace('_', ' ').title())}</td>"
        f"<td>{html.escape(rule.rationale)}</td></tr>"
        for factor, rule in RULES.items()
    )
    factors = f"""
    <section class="lab-card">
      <h3>What kinds of news can move a forecast?</h3>
      <p class="context">When you describe a scenario, the reader checks it
      against this list of situations. Each one nudges expected goals by a
      small, fixed amount, so the AI never gets to invent a probability on
      its own.</p>
      <table><thead><tr><th>Situation</th><th>Why it matters</th></tr></thead>
      <tbody>{factor_rows}</tbody></table>
    </section>
    """

    audit = f"""
    <section class="lab-card">
      <h3>How we audit our own track record</h3>
      <p class="context">Every prediction is saved before its match is
      played. The Track Record tab only counts predictions frozen,
      fingerprinted, and timestamped <em>before</em> kickoff: {health['eligible_prospective_forecasts']}
      of them so far. Older test data doesn't count toward the headline
      numbers, so we can't quietly mix in easier after-the-fact comparisons.
      Current model version: <code>{provenance['model_version']}</code>.</p>
    </section>
    """

    return (
        intro + numbers + live_proof + ai_experiment + rejected + factors + audit
    )


def how_it_works_summary_markdown() -> str:
    return """
Every team carries an Elo rating, the same idea as a chess rating. That
number feeds into Dixon-Coles, a well-worn statistical model for football
scorelines, and we've checked the result against thousands of past matches so
that a "70% favourite" actually wins about 70% of the time.

When you describe a scenario, a small model running on this machine checks it
against a short list of situations we already understand, like *key player
out*, and nudges the expected goals by a fixed amount. It doesn't invent a
probability on its own; it just spots which situation applies, and the
statistics handle the rest.

Want the full walkthrough, the benchmark numbers, and how this compares to
other public predictions? That's all in the **Methodology** tab.
"""


def how_it_works_markdown() -> str:
    return """
## How this actually works

Every team carries an Elo rating, the same kind of number chess players use,
updated after each result. A higher rating means the model expects that team
to score more and concede less.

Those ratings feed into Dixon-Coles, a statistical model analysts have used
for football scorelines for decades. Rather than one guess, it produces a
full grid of scoreline probabilities: 0-0, 1-0, 2-1, and so on. Recent results
count for more than old ones, since a result from last month says more about
a team's current form than one from three years ago. We tried several "how
much more" settings against real results and kept whichever predicted best.

We then checked the model's confidence levels against thousands of matches
and applied a small correction, so a "70% favourite" really does win about
70% of the time rather than 85% or 55%.

### Reading the news

When you type a scenario like "star striker is out", a small language model
runs locally and checks it against a short list of situations we already
understand: a key attacker missing, a fatigue disadvantage, and so on. It
doesn't invent a probability. It just recognises which situation applies,
and each one nudges the expected goals by a small, fixed amount before
Dixon-Coles recalculates the odds. The AI reads; the statistics decide.

### Keeping score

Every prediction is frozen and timestamped before kickoff, so the Track
Record tab shows what the model actually said in advance, not a version
improved with hindsight.

---

These are probabilities, not certainties. Even a 60% favourite loses 4 times
out of 10. For the benchmark numbers, the experiments that didn't make the
cut, and how we audit ourselves, see the **Methodology** tab.
"""


initial_match = repository.by_label(labels[0])
initial_baseline = baseline_forecast(initial_match)
VISITOR_COPY = visitor_tab_copy()
if world_cup_labels:
    initial_world_cup_label = world_cup_labels[0]
    initial_world_cup_fixture = world_cup_fixtures[initial_world_cup_label]
    initial_world_cup_match = fixture_as_match(
        initial_world_cup_fixture,
        world_cup_repository,
    )
    initial_world_cup_forecast = match_forecast(
        initial_world_cup_fixture,
        world_cup_repository.team_by_name,
    )
world_cup_probabilities = simulate_tournament(world_cup_repository)

LIGHT_THEME = Soft(
    primary_hue="blue",
    secondary_hue="red",
    neutral_hue="slate",
)

with gr.Blocks(title="World Cup 2026 Forecaster") as demo:
    match_id_state = gr.State(initial_match.match_id)
    baseline_state = gr.State(initial_baseline.model_dump(mode="json"))
    adjusted_state = gr.State(initial_baseline.model_dump(mode="json"))

    cutoff_display = world_cup_repository.snapshot.get("information_cutoff", "")
    gr.HTML(
        hero_html(
            extractor.name,
            cutoff=cutoff_display,
            overdue_note=overdue_results_note(world_cup_repository),
        )
    )

    with gr.Accordion(
        "How this works",
        open=False,
        elem_classes="gr-accordion",
    ) as how_it_works_accordion:
        gr.Markdown(how_it_works_summary_markdown())
        with gr.Row(elem_classes="how-it-works-launch-row"):
            beat_model_launch = gr.Button(
                "Try Beat the Model →", elem_classes="how-it-works-launch-btn"
            )
            methodology_launch = gr.Button(
                "Read the Methodology →", elem_classes="how-it-works-launch-btn"
            )

    with gr.Tabs() as main_tabs:
        with gr.Tab("World Cup 2026"):
            with gr.Row():
                world_cup_mode = gr.Radio(
                    choices=[
                        ("Probability view", "probability"),
                        ("Compact view", "compact"),
                    ],
                    value="probability",
                    label="Forecast view",
                )
            upcoming_card = gr.HTML(
                upcoming_html(world_cup_repository, mode="probability")
            )

            world_cup_mode.change(
                update_world_cup_upcoming,
                inputs=world_cup_mode,
                outputs=upcoming_card,
                show_progress="hidden",
            )

            gr.HTML(model_summary_html())
            gr.HTML(tournament_benchmark_html(world_cup_repository))

            if world_cup_labels:
                gr.Markdown("## Apply late-breaking evidence to an upcoming match")
                gr.Markdown(
                    "Type in a piece of news and watch the forecast shift. This "
                    "is experimental — a small local model reads your text "
                    "and proposes adjustments, so check the extracted factors "
                    "below before trusting the result."
                )
                live_fixture_selector = gr.Dropdown(
                    choices=world_cup_labels,
                    value=initial_world_cup_label,
                    label="Upcoming fixture",
                )
                live_baseline_card = gr.HTML(
                    forecast_html(
                        initial_world_cup_forecast,
                        initial_world_cup_match,
                        "2026 baseline forecast",
                    )
                )
                live_scenario = gr.Textbox(
                    label="Pre-match report",
                    placeholder=(
                        f"Example: {initial_world_cup_fixture.home}'s first-choice "
                        "striker is confirmed out."
                    ),
                    lines=3,
                )
                live_analyze_button = gr.Button(
                    "Adjust 2026 forecast",
                    variant="primary",
                    elem_classes="primary-button",
                )
                live_factors_card = gr.HTML(
                    factors_html(
                        ScenarioExtraction(),
                        apply_extraction(
                            initial_world_cup_match,
                            ScenarioExtraction(),
                        ),
                    )
                )
                live_adjusted_card = gr.HTML(
                    forecast_html(
                        initial_world_cup_forecast,
                        initial_world_cup_match,
                        "Scenario forecast (experimental)",
                    )
                )
                live_comparison_card = gr.HTML(
                    match_comparison_html(
                        initial_world_cup_fixture, initial_world_cup_forecast
                    )
                )
                live_fixture_selector.change(
                    select_world_cup_fixture,
                    inputs=live_fixture_selector,
                    outputs=[
                        live_baseline_card,
                        live_factors_card,
                        live_adjusted_card,
                        live_comparison_card,
                    ],
                )
                live_analyze_button.click(
                    run_world_cup_scenario,
                    inputs=[live_fixture_selector, live_scenario],
                    outputs=[live_factors_card, live_adjusted_card],
                )
                live_scenario.submit(
                    run_world_cup_scenario,
                    inputs=[live_fixture_selector, live_scenario],
                    outputs=[live_factors_card, live_adjusted_card],
                )
            else:
                gr.HTML(
                    """
                    <section class="lab-card">
                      <div class="eyebrow">Scenario lab</div>
                      <h2>The group-stage scenario window is closed</h2>
                      <p class="context">All 72 group fixtures have been
                      played. The original pre-kickoff forecasts remain frozen
                      and are graded in the Track Record tab; this panel is
                      disabled so completed matches cannot be presented as
                      live prediction opportunities.</p>
                    </section>
                    """
                )

            with gr.Accordion("Group tables & standings", open=False):
                with gr.Row():
                    group_selector = gr.Dropdown(
                        choices=list("ABCDEFGHIJKL"),
                        value="A",
                        label="Group",
                    )
                group_card = gr.HTML(group_html(world_cup_repository, "A"))
                group_selector.change(
                    select_world_cup_group,
                    inputs=group_selector,
                    outputs=group_card,
                    show_progress="hidden",
                )

            with gr.Accordion("Complete 72-match group table", open=False):
                gr.HTML(all_fixtures_html(world_cup_repository))

            gr.HTML(
                tournament_probabilities_html(
                    world_cup_probabilities,
                    world_cup_repository,
                )
            )

        with gr.Tab("Player Awards"):
            gr.HTML(awards_html(world_cup_repository, world_cup_probabilities))

        with gr.Tab(VISITOR_COPY["evidence_title"], id="evidence"):
            with gr.Column(elem_classes="research-shell"):
                gr.HTML(track_record_html(world_cup_repository))
                with gr.Row(elem_classes="r-cta"):
                    gr.HTML(
                        research_cta_html(
                            "Think you can do better?",
                            "Predict historical matches with exactly the "
                            "information the model had.",
                        )
                    )
                    evidence_to_beat_model = gr.Button(
                        "Beat the Model →", elem_classes="r-cta-btn"
                    )

        with gr.Tab("Compare with other forecasters"):
            with gr.Column(elem_classes="research-shell"):
                gr.HTML(
                    tournament_comparison_html(
                        world_cup_probabilities, world_cup_repository
                    )
                )
                with gr.Row(elem_classes="r-cta"):
                    gr.HTML(
                        research_cta_html(
                            "Numbers are easy to compare, hard to earn.",
                            "See how every one of our forecasts was sealed and scored.",
                        )
                    )
                    compare_to_evidence = gr.Button(
                        "Read the Evidence →", elem_classes="r-cta-btn"
                    )
                compare_to_evidence.click(
                    lambda: gr.Tabs(selected="evidence"),
                    outputs=main_tabs,
                )

        # These two are deliberately last and have no visible nav button
        # (hidden in theme.py by tab position) -- the only way in is the
        # "Try Beat the Model" / "Read the Methodology" buttons inside the
        # "How this works" accordion, or the cross-links below. Keeping
        # them as real, full-width Tabs (rather than nested inside the
        # accordion) means their content gets the same layout as every
        # other research page instead of being squeezed into a collapsed
        # strip.
        with gr.Tab(VISITOR_COPY["challenge_title"], id="beat_the_model"):
            with gr.Column(elem_classes="research-shell"):
                gr.HTML(challenge_intro_html(match_count=len(labels)))
                with gr.Column(elem_classes="challenge-panel"):
                    match_selector = gr.Dropdown(
                        choices=labels,
                        value=labels[0],
                        label="Choose a past match",
                        info="The final score is hidden until you commit your forecast.",
                    )
                    match_card = gr.HTML(match_html(initial_match))
                    baseline_card = gr.HTML(
                        forecast_html(initial_baseline, initial_match, "Baseline forecast")
                    )

                    scenario = gr.Textbox(
                        label="Add evidence before kickoff",
                        placeholder=(
                            "Example: Argentina's first-choice striker is confirmed out."
                        ),
                        lines=3,
                    )
                    with gr.Row():
                        analyze_button = gr.Button(
                            "Apply evidence", variant="primary", elem_classes="primary-button"
                        )
                        clear_button = gr.ClearButton(
                            [scenario], value="Clear", elem_classes="secondary-button"
                        )

                    factors_card = gr.HTML(
                        factors_html(
                            ScenarioExtraction(),
                            apply_extraction(initial_match, ScenarioExtraction()),
                        )
                    )
                    adjusted_card = gr.HTML(
                        forecast_html(
                            initial_baseline, initial_match, "Scenario forecast"
                        )
                    )

                    gr.Markdown("### Commit probabilities")
                    with gr.Row():
                        user_home = gr.Slider(
                            0, 100, value=45, step=1, label="Home win %"
                        )
                        user_draw = gr.Slider(
                            0, 100, value=25, step=1, label="Draw %"
                        )
                        user_away = gr.HTML(derived_away_html(45, 25))
                    reveal_button = gr.Button(
                        "Commit forecast and reveal result",
                        variant="primary",
                        elem_classes="primary-button",
                    )
                    reveal_card = gr.HTML()

                    match_selector.change(
                        select_match,
                        inputs=match_selector,
                        outputs=[
                            match_id_state,
                            baseline_state,
                            adjusted_state,
                            match_card,
                            baseline_card,
                            factors_card,
                            adjusted_card,
                            reveal_card,
                            user_away,
                        ],
                    )
                    analyze_button.click(
                        run_scenario,
                        inputs=[match_selector, scenario],
                        outputs=[adjusted_state, factors_card, adjusted_card, reveal_card],
                    )
                    scenario.submit(
                        run_scenario,
                        inputs=[match_selector, scenario],
                        outputs=[adjusted_state, factors_card, adjusted_card, reveal_card],
                    )
                    user_home.change(
                        update_user_forecast,
                        inputs=[user_home, user_draw],
                        outputs=user_away,
                    )
                    user_draw.change(
                        update_user_forecast,
                        inputs=[user_home, user_draw],
                        outputs=user_away,
                    )
                    reveal_button.click(
                        reveal,
                        inputs=[
                            match_selector,
                            baseline_state,
                            adjusted_state,
                            user_home,
                            user_draw,
                        ],
                        outputs=reveal_card,
                    )

                with gr.Row(elem_classes="r-cta"):
                    gr.HTML(
                        research_cta_html(
                            "Ready for the real evidence?",
                            "See how every one of the model's own forecasts scored "
                            "this summer, not just these 20 historical picks.",
                        )
                    )
                    beat_model_to_evidence = gr.Button(
                        "Read the Evidence →", elem_classes="r-cta-btn"
                    )

        with gr.Tab("Methodology", id="methodology"):
            gr.Markdown(how_it_works_markdown())
            gr.HTML(methodology_html())

    # Cross-tab links wired here (not inline) so each button can reference
    # main_tabs / how_it_works_accordion regardless of which one was
    # defined first in the layout above.
    beat_model_launch.click(
        lambda: (gr.Tabs(selected="beat_the_model"), gr.Accordion(open=False)),
        outputs=[main_tabs, how_it_works_accordion],
    )
    methodology_launch.click(
        lambda: (gr.Tabs(selected="methodology"), gr.Accordion(open=False)),
        outputs=[main_tabs, how_it_works_accordion],
    )
    evidence_to_beat_model.click(
        lambda: gr.Tabs(selected="beat_the_model"),
        outputs=main_tabs,
    )
    beat_model_to_evidence.click(
        lambda: gr.Tabs(selected="evidence"),
        outputs=main_tabs,
    )

demo.queue(default_concurrency_limit=8)
