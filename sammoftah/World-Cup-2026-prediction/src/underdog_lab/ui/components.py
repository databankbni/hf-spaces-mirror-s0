from __future__ import annotations

import html

from underdog_lab.domain import Forecast, MatchRecord
from underdog_lab.forecasting.scoring import brier_score, log_loss
from underdog_lab.scenarios.schemas import AdjustmentResult, ScenarioExtraction
from underdog_lab.world_cup.flags import team_label
from underdog_lab.world_cup.forecasting import top_scorelines


def research_hero_html(
    *,
    title: str,
    dek: str,
    meta: str,
    stat_label: str,
    stat_value: str,
    stat_note: str,
    stat_tone: str = "",
) -> str:
    """Editorial hero for a Research tab: headline, dek, meta line, and one
    headline statistic pulled from real data."""
    return f"""
    <section class="r-block">
      <div class="r-hero">
        <div class="r-hero-main">
          <h1>{html.escape(title)}</h1>
          <p class="r-dek">{dek}</p>
          <p class="r-meta">{meta}</p>
        </div>
        <div class="r-headstat">
          <div class="r-k">{html.escape(stat_label)}</div>
          <div class="r-v {stat_tone}">{stat_value}</div>
          <div class="r-s">{stat_note}</div>
        </div>
      </div>
    </section>
    """


def research_section_html(number: int, title: str, subtitle: str, body: str) -> str:
    """A numbered editorial section: '1. Title' + a short subtitle + body HTML."""
    return f"""
    <section class="r-block">
      <span class="r-secno">{number}</span>
      <h2>{html.escape(title)}</h2>
      <p class="r-sub">{subtitle}</p>
      {body}
    </section>
    """


def research_stat_row_html(
    items: list[tuple[str, str, str]] | list[tuple[str, str, str, str]],
) -> str:
    """A row of compact stat boxes: (label, value, subtext[, tone-class])."""
    cells = []
    for item in items:
        label, value, sub = item[0], item[1], item[2]
        tone = item[3] if len(item) > 3 else ""
        cells.append(
            f"""<div><div class="r-k">{html.escape(label)}</div>
            <div class="r-v {tone}">{value}</div>
            <div class="r-s">{sub}</div></div>"""
        )
    return f'<div class="r-statrow">{"".join(cells)}</div>'


def research_cta_html(title: str, subtitle: str) -> str:
    """Text half of a Research-tab call to action. Pair with a real
    ``gr.Button(elem_classes="r-cta-btn")`` inside a
    ``gr.Row(elem_classes="r-cta")`` so the action actually switches tabs —
    a CTA that only looks clickable is worse than no CTA."""
    return f"""
    <div>
      <div class="r-cta-title">{html.escape(title)}</div>
      <div class="r-cta-sub">{html.escape(subtitle)}</div>
    </div>
    """


def visitor_tab_copy() -> dict[str, str]:
    return {
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


def challenge_intro_html(match_count: int = 20) -> str:
    hero = research_hero_html(
        title="Beat the Model",
        dek=(
            "Forecast a historical match using only what was knowable before "
            "kickoff, then see whether new evidence should have changed the "
            "call &mdash; and how your probabilities score against the model's."
        ),
        meta=(
            f"{match_count} curated historical matches &middot; results stay "
            "hidden until you commit &middot; a learning experiment, not a "
            "betting tool or a leaderboard"
        ),
        stat_label="The honest rule",
        stat_value="Same information",
        stat_note=(
            "You see exactly what the model saw at kickoff. No hindsight, "
            "no final score, no evidence the model didn't have."
        ),
    )
    stepper = """
    <div class="r-stepper">
      <div class="r-step on"><div class="r-dot">1</div><div>
        <div class="r-t">Choose a match</div><div class="r-d">pick a past fixture</div></div></div>
      <div class="r-step"><div class="r-dot">2</div><div>
        <div class="r-t">Study the context</div><div class="r-d">pre-kickoff information</div></div></div>
      <div class="r-step"><div class="r-dot">3</div><div>
        <div class="r-t">Add evidence &amp; predict</div><div class="r-d">optional factor, then win/draw/win</div></div></div>
      <div class="r-step"><div class="r-dot">4</div><div>
        <div class="r-t">Reveal &amp; compare</div><div class="r-d">you vs. baseline vs. scenario</div></div></div>
    </div>
    """
    return hero + stepper


def evidence_summary_html(records: dict) -> str:
    coverage = records["coverage"]
    summary = records["prospective"]
    skill = summary["log_loss_skill_vs_uniform"]
    stat_value = f"{skill:+.1%}" if skill is not None else "&mdash;"
    stat_tone = "good" if (skill or 0) > 0 else ("bad" if skill else "")
    return research_hero_html(
        title="Evidence",
        dek=(
            "Every number below is a pre-registered forecast scored against a "
            "real result, or a walk-forward backtest run before the model "
            "shipped. Nothing here is graded in hindsight."
        ),
        meta=(
            f"{coverage['scored']} of {coverage['completed']} completed matches "
            "have a verified pre-kickoff artifact &middot; artifacts are sealed "
            "with SHA-256 manifests &middot; forecasts recorded after kickoff "
            "are rejected automatically, not silently backfilled"
        ),
        stat_label="Log-loss skill vs. equal odds",
        stat_value=stat_value,
        stat_note=(
            f"{summary['n']} pre-registered matches scored so far. Positive "
            "means better than guessing &#8531; on each outcome."
        ),
        stat_tone=stat_tone,
    )


def _format_cutoff(cutoff_iso: str) -> str:
    if not cutoff_iso:
        return ""
    return cutoff_iso[:16].replace("T", " ") + " UTC"


BRAND_BALL_SVG = """
<svg class="brand-ball" viewBox="0 0 24 24" width="28" height="28" aria-hidden="true">
  <circle cx="12" cy="12" r="9.5" fill="none" stroke="currentColor" stroke-width="1.3"/>
  <path d="M3.6,9.2 C7.8,4.6 16.2,4.6 20.4,9.2" fill="none"
        stroke="#2489c9" stroke-width="1.6" stroke-linecap="round"/>
  <path d="M3.2,13.6 C7.6,18.6 16.4,18.6 20.8,13.6" fill="none"
        stroke="#c15b62" stroke-width="1.6" stroke-linecap="round"/>
  <path d="M8,7.4 C10.4,10.6 13.6,13.4 16,16.6" fill="none"
        stroke="currentColor" stroke-width="1" stroke-linecap="round" opacity="0.5"/>
</svg>
"""


def brand_bar_html() -> str:
    """Compact site identity: ball mark + wordmark + year tag, sitting above
    the hero on every tab. A small, self-contained inline SVG icon --
    no image asset, no external request, styled to read as a line-art mark
    rather than a decorative render."""
    return f"""
    <div class="brand-bar">
      <div class="brand-mark">
        {BRAND_BALL_SVG}
        <div class="brand-word">
          <span class="brand-title">World Cup 2026</span>
          <span class="brand-sub">Forecaster</span>
        </div>
      </div>
      <span class="brand-tag">2026</span>
    </div>
    """


def hero_html(extractor_name: str, cutoff: str = "", overdue_note: str = "") -> str:
    meta_bits = []
    if cutoff:
        meta_bits.append(f"Forecasts last updated {_format_cutoff(cutoff)}")
    if overdue_note and overdue_note != "All recorded results are up to date.":
        meta_bits.append(overdue_note)
    meta_html = (
        f'<div class="cutoff-badge">{html.escape(" · ".join(meta_bits))}</div>'
        if meta_bits
        else ""
    )
    return f"""
    {brand_bar_html()}
    <section class="hero">
      <div class="eyebrow">FIFA World Cup 2026 · Forecast Dashboard</div>
      <h1>World Cup 2026 Forecaster</h1>
      <p>Forecasts for all 72 group-stage matches, a Monte Carlo simulation
      of the full bracket, and a scenario tool: describe a team-news update
      and see exactly how much the model's probabilities move.</p>
      <p class="small">The model is Elo ratings feeding a Dixon-Coles
      scoring distribution, fitted on 11,000+ international matches and
      backtested before this tournament started. Independent project, not
      affiliated with FIFA. The <strong>Methodology</strong> tab has the
      fit, the backtest, and where the model gets it wrong.</p>
      {meta_html}
      <div class="metric-strip">
        <span class="metric-pill"><strong>Coverage</strong> 48 teams · 72 group matches</span>
        <span class="metric-pill"><strong>Model</strong> Elo + Dixon-Coles statistics</span>
        <span class="metric-pill"><strong>Scenario reader</strong> {html.escape(extractor_name)}, runs locally</span>
      </div>
    </section>
    """


def match_html(match: MatchRecord) -> str:
    venue = "Neutral venue" if match.neutral_venue else "Recorded venue advantage"
    return f"""
    <section class="match-card">
      <div class="match-meta">{html.escape(match.competition)} / {html.escape(match.stage)} / {match.kickoff_date.year}</div>
      <div class="teams">
        <div class="team">{team_label(match.home_team)}</div>
        <div class="versus">VS</div>
        <div class="team">{team_label(match.away_team)}</div>
      </div>
      <p class="context">{html.escape(match.context)}</p>
      <div class="small">{html.escape(match.venue)} / {venue}</div>
    </section>
    """


def forecast_html(
    forecast: Forecast,
    match: MatchRecord,
    title: str,
    *,
    comparison: Forecast | None = None,
) -> str:
    values = (
        ("home", match.home_team, forecast.p_home, "home-fill"),
        ("draw", "Draw", forecast.p_draw, "draw-fill"),
        ("away", match.away_team, forecast.p_away, "away-fill"),
    )
    rows = []
    for outcome, label, probability, css_class in values:
        delta = ""
        if comparison is not None:
            before = getattr(comparison, f"p_{outcome}")
            change = probability - before
            delta = f" ({change:+.1%})"
        label_html = team_label(label) if outcome != "draw" else html.escape(label)
        rows.append(
            f"""
            <div class="prob-row">
              <div class="prob-label">{label_html}</div>
              <div class="prob-track"><div class="prob-fill {css_class}" style="width:{probability * 100:.1f}%"></div></div>
              <div class="prob-value">{probability:.0%}{delta}</div>
            </div>
            """
        )
    best_score, best_score_probability = top_scorelines(forecast, limit=1)[0]
    return f"""
    <section class="forecast-card">
      <div class="eyebrow">{html.escape(title)}</div>
      {''.join(rows)}
      <div class="forecast-note">
        Expected goals: {match.home_team} {forecast.lambda_home:.2f},
        {match.away_team} {forecast.lambda_away:.2f}.
        Most likely single scoreline: {best_score} ({best_score_probability:.0%})
        &mdash; the mode of the exact-score distribution, not the match call;
        the outcome probabilities above are the forecast.
      </div>
    </section>
    """


def factors_html(
    extraction: ScenarioExtraction,
    result: AdjustmentResult,
    *,
    backend: str | None = None,
    backend_error: str | None = None,
) -> str:
    backend_block = ""
    if backend:
        degraded = "fallback" in backend.lower()
        css_class = "factor-chip dropped" if degraded else "factor-chip"
        backend_block = f"""
        <div class="{css_class}">
          <div class="factor-title">Extracted by {html.escape(backend)}</div>
          <div class="factor-detail">{
              "The local model was unavailable; deterministic rules handled this request."
              if degraded
              else "Local grammar-constrained model inference."
          }</div>
        </div>
        """
        if degraded and backend_error:
            backend_block += (
                '<p class="warning">Runtime fallback reason: '
                + html.escape(backend_error)
                + "</p>"
            )

    if not extraction.factors and not extraction.unsupported_claims:
        return f"""
        <section class="factor-card">
          <div class="eyebrow">Scenario evidence</div>
          <div class="factor-grid">{backend_block}</div>
          <p class="context">No supported factor was detected.</p>
        </section>
        """

    chips = []
    for applied in result.adjustments:
        factor = applied.factor
        state = "" if applied.applied else " dropped"
        status = "Applied" if applied.applied else "Not applied"
        chips.append(
            f"""
            <div class="factor-chip{state}">
              <div class="factor-title">{html.escape(factor.factor_type.value.replace("_", " ").title())} / {factor.team}</div>
              <div class="factor-detail">
                Severity {factor.severity:.0%}, certainty {factor.certainty:.0%}.
                {status}: {html.escape(applied.explanation)}
              </div>
            </div>
            """
        )
    unsupported = ""
    if extraction.unsupported_claims:
        unsupported = (
            '<p class="warning">Unsupported: '
            + html.escape("; ".join(extraction.unsupported_claims))
            + "</p>"
        )
    ambiguities = ""
    if extraction.ambiguities:
        ambiguities = (
            '<p class="warning">Ambiguous: '
            + html.escape("; ".join(extraction.ambiguities))
            + "</p>"
        )
    return f"""
    <section class="factor-card">
      <div class="eyebrow">Scenario evidence</div>
      <div class="factor-grid">{backend_block}{''.join(chips)}</div>
      {unsupported}{ambiguities}
    </section>
    """


def reveal_html(
    match: MatchRecord,
    baseline: Forecast,
    adjusted: Forecast,
    user_home: float,
    user_draw: float,
) -> str:
    user_away = 100.0 - user_home - user_draw
    if user_away < 0:
        return """
        <section class="reveal-card">
          <p class="warning">Home and draw probabilities exceed 100%.
          Reduce one slider before committing.</p>
        </section>
        """

    from underdog_lab.domain import UserForecast

    user = UserForecast(
        p_home=user_home / 100.0,
        p_draw=user_draw / 100.0,
        p_away=user_away / 100.0,
    )
    observed = match.observed_outcome
    scores = (
        ("Baseline", log_loss(baseline, observed), brier_score(baseline, observed)),
        ("Scenario", log_loss(adjusted, observed), brier_score(adjusted, observed)),
        ("You", log_loss(user, observed), brier_score(user, observed)),
    )
    boxes = "".join(
        f"""
        <div class="score-box">
          <span>{name}</span>
          <strong>{loss:.3f}</strong>
          <span class="small">log loss / Brier {brier:.3f}</span>
        </div>
        """
        for name, loss, brier in scores
    )
    return f"""
    <section class="reveal-card">
      <div class="eyebrow">Result revealed</div>
      <div class="result">{team_label(match.home_team)} {match.home_goals}-{match.away_goals} {team_label(match.away_team)}</div>
      <p class="context">{html.escape(match.reveal_notes or "")}</p>
      <div class="score-grid">{boxes}</div>
      <p class="small">Lower scores are better. A surprising outcome does not
      by itself invalidate a calibrated forecast.</p>
    </section>
    """


def derived_away_html(home: float, draw: float) -> str:
    away = 100.0 - home - draw
    tone = "warning" if away < 0 else "context"
    value = max(0.0, away)
    message = (
        "Reduce home or draw; the total is above 100%."
        if away < 0
        else "The third probability is derived so the forecast totals 100%."
    )
    return f"""
    <section class="forecast-card">
      <div class="eyebrow">Your away probability</div>
      <div class="result">{value:.0f}%</div>
      <p class="{tone}">{message}</p>
    </section>
    """
