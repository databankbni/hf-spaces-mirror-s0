from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

from underdog_lab.world_cup.bracket import (
    KNOCKOUT_PATH,
    ROUND_OF_32_SLOTS,
    THIRD_PLACE_MATCH,
    assign_third_place_groups,
    build_round_of_32,
)
from underdog_lab.world_cup.data import TournamentRepository
from underdog_lab.world_cup.forecasting import match_forecast
from underdog_lab.world_cup.simulation import (
    _knockout_win_probability,
    simulate_tournament,
)
from underdog_lab.world_cup.ui import (
    confidence_tier,
    normalize_forecast_view,
    overdue_results_note,
    upcoming_html,
)
from underdog_lab.world_cup.models import Standing
from underdog_lab.world_cup.standings import calculate_standings, rank_standings


def test_visitor_journeys_use_distinct_names_and_explanations():
    from underdog_lab.ui.components import visitor_tab_copy

    copy = visitor_tab_copy()

    assert copy["challenge_title"] == "Beat the Model"
    assert copy["evidence_title"] == "Evidence"
    assert "frozen before kickoff" in copy["evidence_intro"]


def test_challenge_intro_explains_the_four_step_flow():
    from underdog_lab.ui.components import challenge_intro_html

    html = challenge_intro_html(match_count=20)

    assert "Beat the Model" in html
    assert "20 curated historical matches" in html
    assert "Choose a match" in html
    assert "Study the context" in html
    assert "Add evidence" in html
    assert "Reveal" in html and "compare" in html
    assert "Same information" in html


def test_ui_uses_pills_only_for_compact_status_and_keeps_controls_consistent():
    css = Path("src/underdog_lab/ui/theme.py").read_text(encoding="utf-8")

    assert ".challenge-panel" in css
    assert ".journey-intro" in css
    assert ".status-chip" in css
    assert ".metric-pill" in css
    assert ".factor-chip" in css


def test_player_stat_legend_defines_card_abbreviations():
    from underdog_lab.world_cup.ui import player_stat_legend_html

    html = player_stat_legend_html()

    for label in ("OVR", "POT", "PAC", "SHO", "PAS", "DRI", "DEF", "PHY"):
        assert f">{label}</strong>" in html


def test_player_cards_separate_estimated_attributes_from_model_form():
    from underdog_lab.world_cup.ui import _player_card_html, player_stat_methodology_html

    row = {
        "name": "Example Player",
        "team": "Spain",
        "position": "FW",
        "form_rating": 84,
        "overall_rating": 91,
        "attributes": {
            "pace": 90,
            "shooting": 88,
            "passing": 82,
            "dribbling": 89,
            "defending": 40,
            "physical": 78,
        },
    }

    card = _player_card_html(1, row, rating_key="overall_rating", rating_label="OVR")
    methodology = player_stat_methodology_html()

    assert "estimated-attributes" in card
    assert "model-form" in card
    assert "attribute-panel" in card
    assert "model-signal" in card
    assert "ESTIMATE" in card
    assert "MODEL SIGNAL" in card
    assert "projected run signal" in card
    assert "not licensed EA data" in methodology
    assert "public player ratings" in methodology


def test_player_glossary_is_compact_and_defines_core_and_goalkeeper_terms():
    from underdog_lab.world_cup.ui import player_stat_legend_html

    glossary = player_stat_legend_html()

    assert "Glossary" in glossary
    assert "Player attributes" in glossary
    assert "Goalkeeper attributes" in glossary
    assert "PAC" in glossary and "pace" in glossary
    assert "DIV" in glossary and "goalkeeper diving" in glossary


def test_awards_intro_renders_glossary_instead_of_template_placeholders():
    from underdog_lab.world_cup.simulation import simulate_tournament
    from underdog_lab.world_cup.ui import awards_html

    repository = TournamentRepository()
    html = awards_html(repository, simulate_tournament(repository, iterations=2))

    assert "{player_stat_legend_html()}" not in html
    assert "Glossary · card abbreviations" in html
    assert "How to read the cards" in html


def test_player_awards_sections_opt_out_of_global_card_shadow():
    from underdog_lab.world_cup.simulation import simulate_tournament
    from underdog_lab.world_cup.ui import awards_html

    repository = TournamentRepository()
    html = awards_html(repository, simulate_tournament(repository, iterations=2))
    css = Path("src/underdog_lab/ui/theme.py").read_text(encoding="utf-8")

    assert html.count("player-awards-section") >= 5
    assert ".player-awards-section" in css
    assert "box-shadow: none" in css


def test_repository_contains_full_group_stage():
    repository = TournamentRepository()

    assert len(repository.teams) == 48
    assert len(repository.fixtures) == 72
    assert repository.team_by_name["Spain"].elo == 2157
    assert repository.team_by_name["Scotland"].elo == 1782
    assert all(len(repository.group_teams(group)) == 4 for group in "ABCDEFGHIJKL")
    assert all(
        len(repository.group_fixtures(group)) == 6 for group in "ABCDEFGHIJKL"
    )
    assert repository.group_fixtures("B")[1].date.isoformat() == "2026-06-13"
    assert repository.group_fixtures("D")[1].date.isoformat() == "2026-06-13"
    assert all(fixture.kickoff_utc is not None for fixture in repository.fixtures)


def test_overdue_results_note_reports_unresolved_fixtures():
    repository = TournamentRepository(
        snapshot_path=Path("tests/fixtures/world_cup/current_snapshot.json")
    )
    earliest_kickoff = min(
        fixture.kickoff_utc for fixture in repository.fixtures
    )

    assert overdue_results_note(repository, now=earliest_kickoff) == (
        "All recorded results are up to date."
    )

    much_later = datetime(2027, 1, 1, tzinfo=timezone.utc)
    note = overdue_results_note(repository, now=much_later)
    assert "match(es) have kicked off but a result has not been recorded" in note
    assert "WC26-025" in note


def test_complete_snapshot_produces_final_group_a_table():
    repository = TournamentRepository()
    standings = calculate_standings(
        [team.team for team in repository.group_teams("A")],
        repository.group_fixtures("A"),
    )

    assert standings[0].team == "Mexico"
    assert standings[0].points == 9
    assert standings[1].team == "South Africa"
    assert standings[1].points == 4
    assert sum(row.played for row in standings) == 12


def test_head_to_head_breaks_equal_points_before_overall_goal_difference():
    table = {
        "Alpha": Standing(team="Alpha", points=6, goals_for=10, goals_against=1),
        "Beta": Standing(team="Beta", points=6, goals_for=3, goals_against=2),
    }

    ranked = rank_standings(
        table,
        [("Beta", "Alpha", 1, 0)],
        fifa_ranks={"Alpha": 1, "Beta": 20},
    )

    assert [row.team for row in ranked] == ["Beta", "Alpha"]


def test_match_forecast_is_normalized():
    repository = TournamentRepository()
    forecast = match_forecast(repository.fixtures[0], repository.team_by_name)

    assert abs(forecast.p_home + forecast.p_draw + forecast.p_away - 1.0) < 1e-9
    assert forecast.lambda_home > 0
    assert forecast.lambda_away > 0


def test_host_flag_does_not_apply_an_ungated_rating_boost():
    repository = TournamentRepository()
    mexico = repository.team_by_name["Mexico"]

    assert mexico.host is True
    assert mexico.rating == mexico.elo


def test_upcoming_html_reports_completed_tournament():
    repository = TournamentRepository()
    html = upcoming_html(repository, mode="compact")

    # The final (Match 104) is resolved in the checked-in bracket, so there
    # are no unplayed fixtures left to forecast. The panel must say so
    # honestly instead of showing stale "what's next" or conditional-final
    # copy for a tournament that has already ended.
    assert "No unplayed fixture remains" in html
    assert "Track Record tab" in html
    assert "What the model predicts next" not in html
    assert "Conditional final" not in html


def test_confidence_tiers_distinguish_signal_strength():
    assert confidence_tier(0.65, 0.2) == "Concentrated forecast"
    assert confidence_tier(0.52, 0.11) == "Moderate lean"
    assert confidence_tier(0.42, 0.06) == "Narrow lean"
    assert confidence_tier(0.36, 0.02) == "Near-even"


def test_forecast_view_accepts_gradio_values_and_legacy_labels():
    assert normalize_forecast_view("probability") == "probability"
    assert normalize_forecast_view("Probability view") == "probability"
    assert normalize_forecast_view("compact") == "compact"
    assert normalize_forecast_view("Pick mode") == "compact"
    assert normalize_forecast_view(None) == "probability"


def test_simulation_produces_one_champion_per_iteration():
    repository = TournamentRepository()
    probabilities = simulate_tournament(repository, iterations=100, seed=7)

    assert abs(sum(row["champion"] for row in probabilities.values()) - 1.0) < 1e-9
    assert all(0.0 <= row["advance"] <= 1.0 for row in probabilities.values())
    assert all(
        row["champion"] <= row["final"] <= row["semifinal"]
        for row in probabilities.values()
    )


def test_knockout_probability_is_compressed_and_symmetric():
    repository = TournamentRepository()
    spain = _knockout_win_probability("Spain", "South Africa", repository)
    south_africa = _knockout_win_probability(
        "South Africa",
        "Spain",
        repository,
    )

    # Spain vs South Africa is the largest Elo gap in the field (~650). The
    # fitted Dixon-Coles model clamps lambda_home at 4.0 for gaps this
    # large, so the result is compressed (well short of 1.0) but can
    # legitimately exceed the old hand-set model's ~0.97 ceiling -- the
    # calibration table (models/backtest_report.json) shows the 90-100%
    # bucket is itself well-calibrated (predicted 0.95, observed 0.948).
    assert 0.5 < spain < 0.99
    assert abs(spain + south_africa - 1.0) < 1e-8


def test_round_of_32_uses_published_slots_without_same_group_rematches():
    repository = TournamentRepository()
    groups = {team.team: team.group for team in repository.teams}
    ranked = {
        group: [
            type("Row", (), {"team": team.team})()
            for team in repository.group_teams(group)
        ]
        for group in "ABCDEFGHIJKL"
    }
    best_thirds = [ranked[group][2] for group in "ABCDEFGH"]
    matches = build_round_of_32(ranked, best_thirds, groups)

    assert [match for match, _, _ in matches] == list(range(73, 89))
    assert all(groups[first] != groups[second] for _, first, second in matches)
    assert len({team for _, first, second in matches for team in (first, second)}) == 32


def test_all_495_third_place_combinations_have_a_legal_assignment():
    third_slots = {
        slot.match: slot.second_groups
        for slot in ROUND_OF_32_SLOTS
        if slot.second_kind == "third"
    }
    checked = 0
    for groups in combinations("ABCDEFGHIJKL", 8):
        assignment = assign_third_place_groups(groups)
        assert set(assignment.values()) == set(groups)
        assert all(group in third_slots[match] for match, group in assignment.items())
        checked += 1
    assert checked == 495


def test_annex_c_reference_mapping_matches_the_published_first_row():
    assert assign_third_place_groups("EFGHIJKL") == {
        74: "F",
        77: "G",
        79: "E",
        80: "K",
        81: "I",
        82: "H",
        85: "J",
        87: "L",
    }


def test_knockout_path_contains_every_match_after_round_of_32():
    matches = {
        match
        for round_matches in KNOCKOUT_PATH.values()
        for match, _, _ in round_matches
    }

    assert matches | {THIRD_PLACE_MATCH[0]} == set(range(89, 105))
    assert KNOCKOUT_PATH["round_of_16"][0] == (89, 73, 75)
    assert THIRD_PLACE_MATCH == (103, 101, 102)
    assert KNOCKOUT_PATH["champion"] == ((104, 101, 102),)


def test_benchmark_semifinalists_derive_from_frozen_artifact():
    import json
    from pathlib import Path

    from underdog_lab.world_cup.comparison import frozen_long_range_top4

    payload = json.loads(
        Path("predictions/2026-06-13/forecast.json").read_text(encoding="utf-8")
    )
    expected = tuple(
        team
        for team, _ in sorted(
            payload["champion_probabilities"].items(),
            key=lambda item: item[1],
            reverse=True,
        )[:4]
    )
    assert frozen_long_range_top4() == expected
    assert len(expected) == 4
