import pytest

from scripts.update_snapshot import add_result, validate_result_rows


def test_batch_result_validation_rejects_unknown_fixture():
    with pytest.raises(ValueError, match="Unknown tournament fixture"):
        validate_result_rows(
            [
                {
                    "group": "A",
                    "home": "Unknown",
                    "away": "Mexico",
                    "home_goals": 0,
                    "away_goals": 1,
                }
            ]
        )


def test_existing_result_cannot_be_corrected_silently():
    snapshot = {
        "results": [
            {
                "group": "A",
                "home": "Mexico",
                "away": "South Africa",
                "home_goals": 2,
                "away_goals": 0,
            }
        ]
    }

    with pytest.raises(ValueError, match="allow-corrections"):
        add_result(snapshot, "A", "Mexico", "South Africa", 1, 0)
