from datetime import date

from underdog_lab.forecasting.tournament_editions import assign_edition_metadata


def test_editions_and_openers_are_inferred_without_stage_claims():
    matches = [
        {
            "date": date(2018, 6, 1),
            "tournament": "WC",
            "home_team": "AA",
            "away_team": "BB",
        },
        {
            "date": date(2018, 6, 2),
            "tournament": "WC",
            "home_team": "AA",
            "away_team": "CC",
        },
        {
            "date": date(2022, 11, 1),
            "tournament": "WC",
            "home_team": "DD",
            "away_team": "EE",
        },
    ]

    rows = assign_edition_metadata(matches)

    assert [row["edition_id"] for row in rows] == [
        "WC-2018",
        "WC-2018",
        "WC-2022",
    ]
    assert rows[0]["is_inferred_opener"] is True
    assert rows[1]["is_inferred_opener"] is False
