from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from underdog_lab.world_cup.data import TournamentRepository

from underdog_lab.domain import MatchRecord
from underdog_lab.release.health import RESULT_GRACE_PERIOD
from underdog_lab.world_cup.awards import award_predictions, card_attributes
from underdog_lab.world_cup.data import TournamentRepository
from underdog_lab.world_cup.flags import team_label
from underdog_lab.world_cup.forecasting import match_forecast, top_scorelines
from underdog_lab.world_cup.player_images import player_photo_html
from underdog_lab.world_cup.models import TournamentFixture
from underdog_lab.world_cup.predictions import eligible_forecasts
from underdog_lab.world_cup.standings import calculate_standings


def _leading_outcomes(fixture: TournamentFixture, forecast):
    options = [
        ("home", forecast.p_home, f"{fixture.home} win"),
        ("draw", forecast.p_draw, "Draw"),
        ("away", forecast.p_away, f"{fixture.away} win"),
    ]
    return sorted(options, key=lambda item: item[1], reverse=True)


def confidence_tier(probability: float, margin: float) -> str:
    if probability >= 0.6 and margin >= 0.15:
        return "Concentrated forecast"
    if margin >= 0.1:
        return "Moderate lean"
    if margin >= 0.05:
        return "Narrow lean"
    return "Near-even"


def normalize_forecast_view(mode: str | None) -> str:
    normalized = (mode or "").strip().lower()
    aliases = {
        "probability": "probability",
        "probability mode": "probability",
        "probability view": "probability",
        "compact": "compact",
        "compact mode": "compact",
        "compact view": "compact",
        "pick": "compact",
        "pick mode": "compact",
    }
    return aliases.get(normalized, "probability")


def _meta_label(fixture: TournamentFixture) -> str:
    if fixture.matchday >= 73:
        return (
            f"{fixture.date.strftime('%a %b %d')} · {fixture.group}"
            f" · Match {fixture.matchday}"
        )
    return (
        f"{fixture.date.strftime('%a %b %d')} · Group {fixture.group}"
        f" · Matchday {fixture.matchday}"
    )


def _fixture_card(
    fixture: TournamentFixture,
    forecast,
    *,
    mode: str,
    extra_note: str = "",
) -> str:
    scorelines = top_scorelines(forecast)
    best_score, best_score_probability = scorelines[0]
    scoreline_summary = ", ".join(
        f"{html.escape(score)} ({probability:.0%})"
        for score, probability in scorelines
    )
    if normalize_forecast_view(mode) == "compact":
        leading, runner_up, _ = _leading_outcomes(fixture, forecast)
        outcome, probability, label = leading
        margin = probability - runner_up[1]
        clear_favorite = margin >= 0.05
        signal_label = confidence_tier(probability, margin)
        result_label = label if clear_favorite else (
            f"{label} / {runner_up[2]}"
        )
        pick_class = f"pick-pill {outcome}"
        return f"""
        <div class="forecast-card pick-card" style="margin-bottom:10px">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap">
            <div style="min-width:0">
              <div class="match-meta">{_meta_label(fixture)}</div>
              <div class="teams" style="margin:8px 0">
                <div class="team">{team_label(fixture.home)}</div>
                <div class="versus">VS</div>
                <div class="team">{team_label(fixture.away)}</div>
              </div>
              <div class="forecast-note">
                Most likely exact score:
                <strong>{html.escape(best_score)}</strong>
                ({best_score_probability:.0%}). Top three scorelines:
                {scoreline_summary}
              </div>
              {extra_note}
            </div>
            <div class="{pick_class}">
              <div class="pick-label">{html.escape(signal_label)}</div>
              <div class="pick-result">{html.escape(result_label)}</div>
              <div class="signal-detail">{probability:.0%} probability · {margin:.0%} margin</div>
            </div>
          </div>
        </div>
        """

    rows = []
    for outcome, label, probability, css_class in (
        ("home", fixture.home, forecast.p_home, "home-fill"),
        ("draw", "Draw", forecast.p_draw, "draw-fill"),
        ("away", fixture.away, forecast.p_away, "away-fill"),
    ):
        label_html = team_label(label) if outcome != "draw" else html.escape(label)
        rows.append(
            f"""
            <div class="prob-row" style="margin:4px 0">
              <div class="prob-label">{label_html}</div>
              <div class="prob-track"><div class="prob-fill {css_class}" style="width:{probability*100:.1f}%"></div></div>
              <div class="prob-value">{probability:.0%}</div>
            </div>
            """
        )
    return f"""
    <div class="forecast-card" style="margin-bottom:10px">
      <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap">
        <div style="min-width:0">
          <div class="match-meta">{_meta_label(fixture)}</div>
          <div class="teams" style="margin:8px 0">
            <div class="team">{team_label(fixture.home)}</div>
            <div class="versus">VS</div>
            <div class="team">{team_label(fixture.away)}</div>
          </div>
        </div>
        <div class="pick-summary">
          <div class="pick-label">Most likely exact score</div>
          <div class="pick-result">{html.escape(best_score)}</div>
          <div class="signal-detail">{best_score_probability:.0%} probability</div>
        </div>
      </div>
      {''.join(rows)}
      <div class="forecast-note">Top three scorelines: {scoreline_summary}</div>
      {extra_note}
    </div>
    """


def upcoming_html(repository: "TournamentRepository", mode: str = "probability") -> str:
    """Top-of-page upcoming match predictions — the first thing users see."""
    from underdog_lab.world_cup.forecasting import match_forecast

    unplayed = [f for f in repository.fixtures if not f.played]
    knockout = [
        _knockout_as_fixture(f)
        for f in repository.knockout_fixtures
        if not f.played
        and f.home in repository.team_by_name
        and f.away in repository.team_by_name
    ]
    upcoming = sorted(
        [*unplayed, *knockout], key=lambda f: (f.date, f.group, f.matchday)
    )[:10]
    final_scenarios = _final_scenarios(repository)

    if not upcoming:
        return """
        <section class="lab-card player-awards-section">
          <div class="eyebrow">Upcoming matches</div>
          <h2>No unplayed fixture remains</h2>
          <p class="context">Every recorded tournament fixture has a result. See the Track Record tab for how the pre-registered forecasts scored.</p>
        </section>
        """

    from underdog_lab.world_cup.forecasting import knockout_advance_probability

    rows = []
    for f in upcoming:
        fc = match_forecast(f, repository.team_by_name)
        extra_note = ""
        if f.matchday >= 73:
            advance_home = knockout_advance_probability(
                f.home, f.away, repository.team_by_name
            )
            extra_note = (
                "<div class='forecast-note'>Knockout tie — the bars above are "
                "regulation-90-minute probabilities. If it goes to extra time "
                "and penalties: <strong>"
                f"{team_label(f.home)} {advance_home:.0%}</strong> · <strong>"
                f"{team_label(f.away)} {1 - advance_home:.0%}</strong> "
                "to advance (Elo-weighted draw resolution).</div>"
            )
        rows.append(_fixture_card(f, fc, mode=mode, extra_note=extra_note))

    return f"""
    <section class="lab-card" style="margin-bottom:18px; border-color:rgba(178,34,52,.25)">
      <div class="eyebrow">Upcoming matches</div>
      <h2>What the model predicts next</h2>
      <p class="context">Next {len(upcoming)} unplayed tournament fixtures with
      Elo-driven Dixon-Coles probabilities. Probability view shows the full
      distribution; compact view summarizes how concentrated the model output
      is without presenting it as real-world certainty or a betting pick.</p>
      {''.join(rows)}
      {final_scenarios}
    </section>
    """


def _knockout_as_fixture(fixture) -> TournamentFixture:
    return TournamentFixture(
        fixture_id=fixture.fixture_id,
        group=fixture.stage.replace("_", " ").title(),
        matchday=fixture.match_number,
        date=fixture.date,
        home=fixture.home,
        away=fixture.away,
        home_goals=fixture.home_goals,
        away_goals=fixture.away_goals,
    )


def _final_scenarios(repository: "TournamentRepository") -> str:
    """Conditional final cards, shown only while semifinal 2 is undecided.

    Once both finalists are resolved, the final appears as a regular
    upcoming-fixture card and the conditional scenarios would be stale."""
    final = next((f for f in repository.knockout_fixtures if f.stage == "final"), None)
    semifinal = next((f for f in repository.knockout_fixtures if f.match_number == 102), None)
    if final is None or final.played or final.home not in repository.team_by_name or semifinal is None:
        return ""
    if semifinal.played or final.resolved:
        return ""
    candidates = [team for team in (semifinal.home, semifinal.away) if team in repository.team_by_name]
    if not candidates:
        return ""
    cards = []
    for opponent in candidates:
        fixture = TournamentFixture(
            fixture_id="conditional-final",
            group="Final scenario",
            matchday=104,
            date=final.date,
            home=final.home,
            away=opponent,
        )
        forecast = match_forecast(fixture, repository.team_by_name)
        cards.append(
            f"<div class='forecast-card' style='margin-top:8px'><div class='match-meta'>Conditional final · if {html.escape(opponent)} wins semifinal 2</div>"
            f"<div class='teams' style='margin:8px 0'><div class='team'>{team_label(final.home)}</div><div class='versus'>VS</div><div class='team'>{team_label(opponent)}</div></div>"
            f"<div class='context'>Model win probabilities: {forecast.p_home:.0%} {team_label(final.home)} · {forecast.p_draw:.0%} draw · {forecast.p_away:.0%} {team_label(opponent)}</div></div>"
        )
    return "<div class='eyebrow' style='margin-top:14px'>Final scenarios</div>" + "".join(cards)


def fixture_label(fixture: TournamentFixture) -> str:
    status = (
        f"{fixture.home_goals}-{fixture.away_goals}"
        if fixture.played
        else fixture.date.strftime("%b %d")
    )
    return f"{fixture.home} vs {fixture.away} · {status} · Group {fixture.group}"


def fixture_as_match(
    fixture: TournamentFixture,
    repository: TournamentRepository,
) -> MatchRecord:
    forecast = match_forecast(fixture, repository.team_by_name)
    return MatchRecord(
        match_id=fixture.fixture_id,
        kickoff_date=fixture.date,
        competition="FIFA World Cup 2026",
        stage=f"Group {fixture.group}, matchday {fixture.matchday}",
        home_team=fixture.home,
        away_team=fixture.away,
        venue="Neutral tournament venue",
        neutral_venue=True,
        home_goals=fixture.home_goals or 0,
        away_goals=fixture.away_goals or 0,
        pre_match_home_elo=repository.team_by_name[fixture.home].rating,
        pre_match_away_elo=repository.team_by_name[fixture.away].rating,
        lambda_home=forecast.lambda_home,
        lambda_away=forecast.lambda_away,
        context=(
            "Tournament forecast from the frozen 2026 snapshot. "
            "Scenario evidence is applied as a bounded adjustment."
        ),
    )


def freshness_note(cutoff_iso: str, now: datetime | None = None) -> str:
    """Describe how stale ``information_cutoff`` is relative to ``now``.

    The snapshot only contains results known as of its cutoff. Once a day
    or more has passed, fixtures that have since been played may still be
    shown as "upcoming" until the snapshot is refreshed.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = datetime.fromisoformat(cutoff_iso.replace("Z", "+00:00"))
    age_days = (now - cutoff).total_seconds() / 86400

    if age_days < 1:
        return "Snapshot data is current."
    if age_days < 2:
        return "Snapshot data is about a day old and may not include yesterday's results yet."
    return (
        f"Snapshot data is {age_days:.0f} days old. Results since then are "
        "not yet reflected — fixtures shown as \"upcoming\" may already "
        "have been played."
    )


def overdue_results_note(
    repository: TournamentRepository, now: datetime | None = None
) -> str:
    """Describe whether any fixtures are missing a result past the grace period.

    The snapshot's ``information_cutoff`` only tells us how old the data is,
    not whether specific matches that have since kicked off are still
    unresolved in it.
    """
    now = now or datetime.now(timezone.utc)
    overdue = [
        fixture
        for fixture in repository.fixtures
        if (
            not fixture.played
            and fixture.kickoff_utc is not None
            and fixture.kickoff_utc + RESULT_GRACE_PERIOD <= now
        )
    ]
    if not overdue:
        return "All recorded results are up to date."
    ids = ", ".join(fixture.fixture_id for fixture in overdue)
    return (
        f"{len(overdue)} match(es) have kicked off but a result has not been "
        f"recorded yet ({ids}). The snapshot will refresh once results are "
        "confirmed."
    )


def snapshot_html(repository: TournamentRepository) -> str:
    played = sum(fixture.played for fixture in repository.fixtures)
    cutoff = html.escape(repository.snapshot["information_cutoff"])
    freshness = html.escape(freshness_note(repository.snapshot["information_cutoff"]))
    return f"""
    <section class="match-card world-cup-summary">
      <div class="eyebrow">Prospective tournament snapshot</div>
      <h2>2026 World Cup Forecaster</h2>
      <p class="context">Forecast every group match, inspect the current table,
      and simulate advancement and title probabilities from information frozen
      at <strong>{cutoff}</strong>.</p>
      <div class="score-grid">
        <div class="score-box"><span>Teams</span><strong>48</strong><span class="small">12 groups</span></div>
        <div class="score-box"><span>Group fixtures</span><strong>72</strong><span class="small">full match table</span></div>
        <div class="score-box"><span>Recorded results</span><strong>{played}</strong><span class="small">as of cutoff</span></div>
      </div>
      <p class="small data-freshness">{freshness}</p>
      <p class="small">This is an experimental Elo-to-goals model, not betting
      advice. Published kickoff dates and recorded results are snapshot data;
      exact kickoff times should be checked against FIFA.</p>
    </section>
    """


def group_html(repository: TournamentRepository, group: str) -> str:
    teams = [team.team for team in repository.group_teams(group)]
    fixtures = repository.group_fixtures(group)
    standings = calculate_standings(
        teams,
        fixtures,
        fifa_ranks={
            team.team: team.rank for team in repository.group_teams(group)
        },
    )
    standing_rows = "".join(
        f"""
        <tr>
          <td>{position}</td><td>{team_label(row.team)}</td><td>{row.played}</td>
          <td>{row.wins}</td><td>{row.draws}</td><td>{row.losses}</td>
          <td>{row.goals_for}:{row.goals_against}</td><td>{row.goal_difference:+d}</td>
          <td><strong>{row.points}</strong></td>
        </tr>
        """
        for position, row in enumerate(standings, start=1)
    )
    fixture_rows = []
    archived = eligible_forecasts(repository.fixtures)
    for fixture in fixtures:
        forecast = match_forecast(fixture, repository.team_by_name)
        result = (
            f"<strong>{fixture.home_goals}-{fixture.away_goals}</strong>"
            if fixture.played
            else "Scheduled"
        )
        if fixture.played:
            prediction = archived.get(fixture.fixture_id)
            probabilities = (
                (
                    f"<td>{prediction['p_home']:.0%}</td>"
                    f"<td>{prediction['p_draw']:.0%}</td>"
                    f"<td>{prediction['p_away']:.0%}</td>"
                )
                if prediction
                else "<td>—</td><td>—</td><td>—</td>"
            )
        else:
            probabilities = (
                f"<td>{forecast.p_home:.0%}</td>"
                f"<td>{forecast.p_draw:.0%}</td>"
                f"<td>{forecast.p_away:.0%}</td>"
            )
        fixture_rows.append(
            f"""
            <tr>
              <td>{fixture.date.strftime("%b %d")}</td>
              <td>{team_label(fixture.home)}</td>
              <td>{team_label(fixture.away)}</td>
              <td>{result}</td>
              {probabilities}
            </tr>
            """
        )
    return f"""
    <section class="lab-card player-awards-section">
      <div class="eyebrow">Group {html.escape(group)}</div>
      <h2>Table and match forecasts</h2>
      <div class="table-scroll">
        <table>
          <thead><tr><th>#</th><th>Team</th><th>P</th><th>W</th><th>D</th><th>L</th><th>GF:GA</th><th>GD</th><th>Pts</th></tr></thead>
          <tbody>{standing_rows}</tbody>
        </table>
      </div>
      <div class="table-scroll">
        <table>
          <thead><tr><th>Date</th><th>Team 1</th><th>Team 2</th><th>Status</th><th>1</th><th>X</th><th>2</th></tr></thead>
          <tbody>{''.join(fixture_rows)}</tbody>
        </table>
      </div>
    </section>
    """


def all_fixtures_html(repository: TournamentRepository) -> str:
    rows = []
    archived = eligible_forecasts(repository.fixtures)
    for fixture in repository.fixtures:
        forecast = match_forecast(fixture, repository.team_by_name)
        result = (
            f"{fixture.home_goals}-{fixture.away_goals}"
            if fixture.played
            else "Scheduled"
        )
        if fixture.played:
            prediction = archived.get(fixture.fixture_id)
            probabilities = (
                (
                    f"<td>{prediction['p_home']:.1%}</td>"
                    f"<td>{prediction['p_draw']:.1%}</td>"
                    f"<td>{prediction['p_away']:.1%}</td>"
                )
                if prediction
                else "<td>—</td><td>—</td><td>—</td>"
            )
        else:
            probabilities = (
                f"<td>{forecast.p_home:.1%}</td>"
                f"<td>{forecast.p_draw:.1%}</td>"
                f"<td>{forecast.p_away:.1%}</td>"
            )
        rows.append(
            f"""
            <tr>
              <td>{fixture.fixture_id}</td><td>{fixture.date.strftime("%b %d")}</td>
              <td>{html.escape(fixture.group)}</td><td>{team_label(fixture.home)}</td>
              <td>{team_label(fixture.away)}</td><td>{result}</td>
              {probabilities}
            </tr>
            """
        )
    return f"""
    <section class="lab-card">
      <div class="eyebrow">Complete known schedule</div>
      <h2>All 72 group-stage fixtures</h2>
      <div class="table-scroll probability-table">
        <table>
          <thead><tr><th>ID</th><th>Date</th><th>Group</th><th>Team 1</th><th>Team 2</th><th>Status</th><th>1</th><th>X</th><th>2</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </section>
    """


def _stat_tier(value: int) -> str:
    if value >= 85:
        return "tier-elite"
    if value < 60:
        return "tier-weak"
    return ""


def _player_card_html(rank: int, row: dict, *, rating_key: str, rating_label: str) -> str:
    campaign_chip = (
        '<span class="campaign-chip alive">Still playing</span>'
        if row.get("still_playing")
        else '<span class="campaign-chip">Campaign over</span>'
    )
    stat_cells = "".join(
        f"""
        <div class="stat-cell">
          <div class="stat-top"><span class="stat-label">{label}</span><span class="stat-value {_stat_tier(row["attributes"][key])}">{row["attributes"][key]}</span></div>
          <div class="stat-track"><div class="stat-fill {_stat_tier(row["attributes"][key])}" style="width:{row["attributes"][key]}%"></div></div>
        </div>
        """
        for key, label in card_attributes(row)
    )
    return f"""
    <div class="player-card">
      <div class="player-card-head">
        {player_photo_html(row["name"])}
        <div class="ovr-badge estimated-attributes" title="Estimated {rating_label} from public player ratings; not licensed EA data">
          <span class="ovr-value">{row[rating_key]}</span>
        </div>
        <div class="player-card-meta">
          <div class="player-rank">#{rank} shortlist position</div>
          <div class="player-name">{html.escape(row["name"])}</div>
          <div class="player-team">{team_label(row["team"])} {campaign_chip}</div>
        </div>
      </div>
      <div class="model-signal model-form">
        <span class="model-signal-kicker">MODEL SIGNAL</span>
        <strong>{row["form_rating"]}/99</strong>
        <span class="model-signal-note">projected run signal</span>
      </div>
      <div class="attribute-panel estimated-attributes">
        <div class="rating-layer-label">
          <span>ESTIMATE · player attributes</span>
          <small>public rating synthesis</small>
        </div>
        <div class="player-stats">{stat_cells}</div>
      </div>
    </div>
    """


def player_stat_legend_html() -> str:
    player_stats = (
        ("OVR", "overall rating"),
        ("POT", "potential rating"),
        ("PAC", "pace"),
        ("SHO", "shooting"),
        ("PAS", "passing"),
        ("DRI", "dribbling"),
        ("DEF", "defending"),
        ("PHY", "physical"),
    )
    goalkeeper_stats = (
        ("DIV", "goalkeeper diving"),
        ("HAN", "goalkeeper handling"),
        ("KIC", "goalkeeper kicking"),
        ("REF", "goalkeeper reflexes"),
        ("SPD", "goalkeeper speed"),
        ("POS", "goalkeeper positioning"),
    )
    player_items = "".join(
        f'<span class="stat-legend-item"><strong>{abbr}</strong>{meaning}</span>'
        for abbr, meaning in player_stats
    )
    goalkeeper_items = "".join(
        f'<span class="stat-legend-item"><strong>{abbr}</strong>{meaning}</span>'
        for abbr, meaning in goalkeeper_stats
    )
    return f"""
    <section class="stat-legend" aria-label="Player card glossary">
      <strong class="stat-legend-title">Glossary · card abbreviations</strong>
      <div class="stat-legend-groups">
        <div class="stat-legend-group"><span class="stat-legend-group-title">Player attributes</span><div class="stat-legend-grid">{player_items}</div></div>
        <div class="stat-legend-group"><span class="stat-legend-group-title">Goalkeeper attributes</span><div class="stat-legend-grid">{goalkeeper_items}</div></div>
      </div>
    </section>
    """


def player_stat_methodology_html() -> str:
    return """
    <section class="stat-methodology" aria-label="Player card methodology">
      <div class="stat-methodology-title">How to read the cards</div>
      <div class="stat-methodology-grid">
        <div class="stat-methodology-item estimated-attributes">
          <strong>Estimated attributes</strong>
          <span>OVR, POT and the six attribute bars are reconstructed from public player ratings. They are estimates, not licensed EA data.</span>
        </div>
        <div class="stat-methodology-item model-form">
          <strong>Model form</strong>
          <span>The blue form signal combines those estimates with the tournament simulation's projected team run. It is our ranking signal, not a player rating.</span>
        </div>
      </div>
    </section>
    """


def _award_section_html(
    title: str,
    description: str,
    rows: list[dict],
    *,
    rating_key: str = "overall_rating",
    rating_label: str = "OVR",
) -> str:
    if not rows:
        return f"""
        <section class="lab-card player-awards-section">
          <div class="eyebrow">Player awards</div>
          <h2>{html.escape(title)}</h2>
          <p class="context">{html.escape(description)}</p>
          <p class="small">No eligible players in the current shortlist.</p>
        </section>
        """

    cards = "".join(
        _player_card_html(rank, row, rating_key=rating_key, rating_label=rating_label)
        for rank, row in enumerate(rows, start=1)
    )
    return f"""
    <section class="lab-card player-awards-section">
      <div class="eyebrow">Player awards</div>
      <h2>{html.escape(title)}</h2>
      <p class="context">{html.escape(description)}</p>
      <div class="player-card-grid">{cards}</div>
    </section>
    """


def awards_html(
    repository: TournamentRepository,
    probabilities: dict[str, dict[str, float]],
) -> str:
    rankings = award_predictions(probabilities)
    still_playing = {
        team
        for fixture in repository.knockout_fixtures
        if not fixture.played
        for team in (fixture.home, fixture.away)
        if team in repository.team_by_name
    }
    for rows in rankings.values():
        for row in rows:
            row["still_playing"] = row["team"] in still_playing
    intro = f"""
    <section class="lab-card player-awards-section" style="border-color:rgba(178,34,52,.25)">
      <div class="eyebrow">Player awards</div>
      <h2>The mid-June shortlists, held to account</h2>
      <p class="context">These four shortlists were compiled from public
      club-season ratings in mid-June, in the opening days of the group
      stage, and the player data has not been touched since. They do not
      track tournament goals, assists, or clean sheets &mdash; the only live
      ingredient is the team-run signal from the bracket simulation above.
      That is deliberate: rather than quietly rewriting the lists as results
      came in, we left them frozen so you can judge how far club form plus a
      bracket forecast gets you once the real awards are handed out. Cards
      are EA FC-style; the OVR/POT badge and PAC/SHO/PAS/DRI/DEF/PHY ratings
      are our own estimates, not licensed EA data.</p>
      {player_stat_legend_html()}
      {player_stat_methodology_html()}
    </section>
    """
    return intro + "".join(
        [
            _award_section_html(
                "Golden Ball (best player)",
                "Ranked by mid-June club-season rating, boosted for players "
                "whose team the bracket gives a semifinal-or-further run. A "
                "deep run means more high-stakes minutes for the voters to "
                "remember.",
                rankings["golden_ball"],
            ),
            _award_section_html(
                "Golden Boot (top scorer)",
                "Ranked by club scoring rate and shooting ability, scaled by "
                "how many tournament matches the bracket gives this player's "
                "team. Club form, not tournament goals: the real Golden Boot "
                "table is the exam this list sits after the final.",
                rankings["golden_boot"],
            ),
            _award_section_html(
                "Golden Glove (best goalkeeper)",
                "Ranked by mid-June rating and expected minutes, with a bonus "
                "for teams projected to go deep. Knockout clean sheets carry "
                "more weight for this award than group-stage ones.",
                rankings["golden_glove"],
            ),
            _award_section_html(
                "Best Young Player (born 2005 or later)",
                "Ranked by potential rather than current form, for players "
                "eligible for FIFA's Young Player Award, with the same "
                "deep-run boost as the Golden Ball.",
                rankings["young_player"],
                rating_key="potential_rating",
                rating_label="POT",
            ),
        ]
    )


def tournament_probabilities_html(
    probabilities: dict[str, dict[str, float]],
    repository: TournamentRepository,
) -> str:
    ordered = sorted(
        repository.teams,
        key=lambda team: probabilities[team.team]["champion"],
        reverse=True,
    )
    rows = "".join(
        f"""
        <tr>
          <td>{position}</td><td>{team_label(team.team)}</td><td>{html.escape(team.group)}</td>
          <td>{probabilities[team.team]["advance"]:.1%}</td>
          <td>{probabilities[team.team]["quarterfinal"]:.1%}</td>
          <td>{probabilities[team.team]["semifinal"]:.1%}</td>
          <td><strong>{probabilities[team.team]["champion"]:.1%}</strong></td>
        </tr>
        """
        for position, team in enumerate(ordered, start=1)
    )
    return f"""
    <section class="lab-card">
      <div class="eyebrow">Monte Carlo forecast</div>
      <h2>Who wins the 2026 World Cup?</h2>
      <p class="context">3,000 simulations condition on recorded results and
      current World Football Elo ratings.
      Group qualification follows the 12-group format and the published FIFA
      Round-of-32 slots, including legal placement of the eight best
      third-place teams. Knockout games use Poisson regulation probabilities with a
      compressed extra-time and penalty edge, so these remain research
      estimates rather than an official bracket calculator.</p>
      <div class="table-scroll probability-table">
        <table>
          <thead><tr><th>#</th><th>Team</th><th>Group</th><th>Advance</th><th>QF</th><th>SF</th><th>Champion</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>
    """
