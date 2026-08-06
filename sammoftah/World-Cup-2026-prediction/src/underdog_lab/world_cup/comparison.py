"""Comparisons against publicly published third-party World Cup forecasts.

All numbers come from `data/world_cup_2026/external_forecasts.json`, a
one-time dated snapshot of independently published projections (an
analytics "supercomputer" model, a sports-data outlet's team projections,
and betting-market consensus). Nothing here is fetched live.
"""

from __future__ import annotations

import html
import json
from functools import lru_cache
from pathlib import Path

from underdog_lab.ui.components import (
    research_hero_html,
    research_section_html,
)
from underdog_lab.world_cup.flags import team_label
from underdog_lab.world_cup.predictions import scored_track_records

EXTERNAL_FORECASTS_PATH = Path("data/world_cup_2026/external_forecasts.json")
FROZEN_LONG_RANGE_FORECAST_PATH = Path("predictions/2026-06-13/forecast.json")


@lru_cache(maxsize=1)
def frozen_long_range_top4() -> tuple[str, ...]:
    """The four highest champion-probability teams from the frozen June 13
    tournament forecast. Read from the immutable artifact rather than
    hardcoded, so the claim in the benchmark card is exactly as strong as
    the checked-in evidence."""
    if not FROZEN_LONG_RANGE_FORECAST_PATH.exists():
        return ()
    payload = json.loads(
        FROZEN_LONG_RANGE_FORECAST_PATH.read_text(encoding="utf-8")
    )
    champion = payload.get("champion_probabilities", {})
    return tuple(
        team
        for team, _ in sorted(
            champion.items(), key=lambda item: item[1], reverse=True
        )[:4]
    )


@lru_cache(maxsize=1)
def load_external_forecasts() -> dict:
    if not EXTERNAL_FORECASTS_PATH.exists():
        return {}
    return json.loads(EXTERNAL_FORECASTS_PATH.read_text(encoding="utf-8"))


def _normalize(*values: float) -> tuple[float, ...]:
    total = sum(values)
    if total <= 0:
        return values
    return tuple(value / total for value in values)


def match_comparison_html(fixture, forecast) -> str:
    """A small 'how does this compare?' table for one fixture, or '' if
    no third-party data is available for it."""
    data = load_external_forecasts().get("match_odds")
    if not data:
        return ""
    entry = data.get("fixtures", {}).get(fixture.fixture_id)
    if not entry:
        return ""

    our_home, our_draw, our_away = forecast.p_home, forecast.p_draw, forecast.p_away
    ext_home, ext_draw, ext_away = _normalize(
        entry["p_home"], entry["p_draw"], entry["p_away"]
    )

    rows = f"""
    <tr><td>Our model</td><td>{our_home:.0%}</td><td>{our_draw:.0%}</td><td>{our_away:.0%}</td>
    <td class="small">as of {html.escape(data.get('captured_at', ''))}</td></tr>
    <tr><td>{html.escape(data['label'])}</td><td>{ext_home:.0%}</td><td>{ext_draw:.0%}</td><td>{ext_away:.0%}</td>
    <td class="small">as of {html.escape(entry.get('captured_at', ''))}</td></tr>
    """
    return f"""
    <section class="lab-card">
      <div class="eyebrow">How does this compare?</div>
      <h3>{team_label(fixture.home)} vs {team_label(fixture.away)}</h3>
      <div class="table-scroll"><table>
        <thead><tr><th>Source</th><th>{team_label(fixture.home)}</th><th>Draw</th><th>{team_label(fixture.away)}</th><th></th></tr></thead>
        <tbody>{rows}</tbody>
      </table></div>
      <p class="small">{html.escape(data.get('note', ''))} Source:
      <a href="{html.escape(data['url'])}" target="_blank" rel="noopener">{html.escape(data['source'])}</a>.</p>
    </section>
    """


def tournament_comparison_html(probabilities: dict, repository) -> str:
    external = load_external_forecasts()
    title_data = external.get("tournament_title")
    group_data = external.get("group_stage")
    odds_data = external.get("title_odds_partial")
    source_count = sum(1 for data in (title_data, group_data, odds_data) if data)
    source_names = ", ".join(
        html.escape(data["label"]) for data in (title_data, group_data, odds_data) if data
    )
    snapshot_dates = sorted(
        {data.get("captured_at", "") for data in (title_data, group_data) if data}
    )

    hero = research_hero_html(
        title="Compare with other forecasters",
        dek=(
            "How our probabilities line up against public projections we "
            "snapshotted before the tournament. Same teams, different "
            "models, different dates &mdash; read the caveat before the "
            "columns."
        ),
        meta=(
            f"{source_count} external source{'s' if source_count != 1 else ''} "
            f"compared &middot; our column is the live model, updated with "
            "the current bracket"
        ),
        stat_label="Sources compared",
        stat_value=str(source_count),
        stat_note=source_names or "No external snapshots available.",
    )

    warning = ""
    if len(snapshot_dates) == 1 and snapshot_dates[0]:
        warning = f"""
        <div class="r-warn">&#9888; <strong>The snapshots are not
        contemporaneous.</strong> The external sources below were captured
        on {html.escape(snapshot_dates[0])}, before the tournament began. Our
        column updates with the live bracket. Differences partly reflect
        information, not only modelling &mdash; that is why we show both,
        and date every column.</div>
        """

    sections = [hero]
    if warning:
        sections.append(f'<section class="r-block">{warning}</section>')

    section_number = 1
    if title_data:
        rows = []
        for team, ext_probability in sorted(
            title_data["title_probability"].items(),
            key=lambda item: item[1],
            reverse=True,
        ):
            our_probability = probabilities.get(team, {}).get("champion", 0.0)
            bar_pct = min(100, round(our_probability * 100))
            rows.append(
                f"<tr><td>{team_label(team)}</td>"
                f"<td class='r-num'>{ext_probability:.1%}</td>"
                f"<td class='r-num'>{our_probability:.1%}</td>"
                f"<td><div class='r-bar'><i style='width:{bar_pct}%'></i></div></td></tr>"
            )
        body = f"""
        <table class="r-table">
          <thead><tr><th>Team</th>
          <th class="r-num">{html.escape(title_data['label'])}<br>
          <span style="font-weight:400">{html.escape(title_data.get('captured_at', ''))}</span></th>
          <th class="r-num">Our model<br><span style="font-weight:400">live today</span></th>
          <th>Live probability</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
        <div class="r-src">{html.escape(title_data.get('note', ''))} Source:
        <a href="{html.escape(title_data['url'])}" target="_blank" rel="noopener">{html.escape(title_data['source'])}</a>,
        captured {html.escape(title_data.get('captured_at', ''))}.</div>
        """
        sections.append(
            research_section_html(
                section_number,
                "Who lifts the trophy?",
                f"{html.escape(title_data['label'])}'s pre-tournament title probabilities vs. our live model.",
                body,
            )
        )
        section_number += 1

    if odds_data:
        rows = []
        for team, american in odds_data["odds_american"].items():
            implied = 100.0 / (american + 100.0)
            our_probability = probabilities.get(team, {}).get("champion", 0.0)
            rows.append(
                f"<tr><td>{team_label(team)}</td>"
                f"<td class='r-num'>+{american}</td>"
                f"<td class='r-num'>{implied:.1%}</td>"
                f"<td class='r-num'>{our_probability:.1%}</td></tr>"
            )
        body = f"""
        <table class="r-table">
          <thead><tr><th>Team</th>
          <th class="r-num">Opening odds</th>
          <th class="r-num">Implied probability</th>
          <th class="r-num">Our model<br><span style="font-weight:400">live today</span></th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
        <div class="r-src">{html.escape(odds_data.get('note', ''))} Source:
        <a href="{html.escape(odds_data['url'])}" target="_blank" rel="noopener">{html.escape(odds_data['source'])}</a>,
        captured {html.escape(odds_data.get('captured_at', ''))}.</div>
        """
        sections.append(
            research_section_html(
                section_number,
                "A third check: the opening betting line",
                "Pre-tournament market pricing, converted from American odds "
                "to implied probability. Only two teams' opening lines are "
                "still published, so this is a spot-check, not a full-field "
                "table like the two above.",
                body,
            )
        )
        section_number += 1

    if group_data:
        rows = []
        teams_by_group = {team.team: team.group for team in repository.teams}
        for team, ext in sorted(
            group_data["teams"].items(),
            key=lambda item: teams_by_group.get(item[0], "Z") + item[0],
        ):
            ours = probabilities.get(team, {})
            rows.append(
                f"<tr><td>{team_label(team)}</td>"
                f"<td>{teams_by_group.get(team, '?')}</td>"
                f"<td class='r-num'>{ext['group_win']:.1%}</td>"
                f"<td class='r-num'>{ours.get('group_winner', 0.0):.1%}</td>"
                f"<td class='r-num'>{ext['qualify']:.1%}</td>"
                f"<td class='r-num'>{ours.get('advance', 0.0):.1%}</td></tr>"
            )
        body = f"""
        <div class="table-scroll"><table class="r-table">
          <thead><tr><th>Team</th><th>Group</th>
          <th class="r-num">{html.escape(group_data['label'])}<br><span style="font-weight:400">group win</span></th>
          <th class="r-num">Our model<br><span style="font-weight:400">group win</span></th>
          <th class="r-num">{html.escape(group_data['label'])}<br><span style="font-weight:400">qualify</span></th>
          <th class="r-num">Our model<br><span style="font-weight:400">advance</span></th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table></div>
        <div class="r-src">{html.escape(group_data.get('note', ''))} Source:
        <a href="{html.escape(group_data['url'])}" target="_blank" rel="noopener">{html.escape(group_data['source'])}</a>,
        captured {html.escape(group_data.get('captured_at', ''))}.</div>
        """
        sections.append(
            research_section_html(
                section_number,
                "Group-stage projections",
                f"{html.escape(group_data['label'])} published qualification odds for all 48 teams before the tournament.",
                body,
            )
        )
        section_number += 1

    return "".join(sections)


def tournament_benchmark_html(repository) -> str:
    """Show the honest headline score and the tournament-readiness signal."""
    records = scored_track_records(
        repository.tournament_fixtures, repository.team_by_name
    )
    summary = records["prospective"]
    long_range_top4 = set(frozen_long_range_top4())
    actual_semifinalists = set()
    for match in repository.knockout_fixtures:
        if match.stage == "semifinal" and match.resolved:
            actual_semifinalists.update((match.home, match.away))
    semifinal_hit = (
        len(actual_semifinalists & long_range_top4)
        if actual_semifinalists and long_range_top4
        else 0
    )
    return f"""
    <section class="lab-card" style="border-color:rgba(53,114,74,.35)">
      <div class="eyebrow">Performance spotlight</div>
      <h2>What went well — and what is still unproven</h2>
      <p class="context">Our verified pre-match forecasts currently have
      <strong>{summary['accuracy']:.1%}</strong> top-pick accuracy across
      <strong>{summary['n']}</strong> predictions, with
      <strong>{summary['log_loss_skill_vs_uniform']:+.1%}</strong> log-loss
      skill versus an equal 1/3 baseline. The four highest
      champion-probability teams in the frozen June 13 tournament forecast
      ({', '.join(sorted(long_range_top4))}) include
      <strong>{semifinal_hit}/4</strong> of the actual semifinalists. That
      is encouraging directional evidence, not proof that we beat the
      market; note the June 13 batch carries the pre-registration caveats
      documented in predictions/INTEGRITY_NOTES.md.</p>
      <div class="score-grid">
        <div class="score-box"><span>Verified predictions</span><strong>{summary['n']}</strong></div>
        <div class="score-box"><span>Top-pick accuracy</span><strong>{summary['accuracy']:.1%}</strong></div>
        <div class="score-box"><span>Skill vs equal odds</span><strong>{summary['log_loss_skill_vs_uniform']:+.1%}</strong></div>
        <div class="score-box"><span>Semifinalists identified</span><strong>{semifinal_hit}/4</strong></div>
      </div>
      <p class="small">Knockout results are ingested from the live ESPN
      bracket with the raw provider response checked in beside the snapshot.
      The third-place and final forecasts are pre-registered as immutable
      artifacts under predictions/live/ and are scored only after the final
      whistle.</p>
    </section>
    """
