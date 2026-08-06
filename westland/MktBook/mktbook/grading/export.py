"""CSV export for grading results."""
from __future__ import annotations

import csv
import io

from mktbook.db import queries


_HEADERS = [
    "timestamp",
    "grading_run_id",
    "workout_id",
    "student_name",
    "bot_name",
    "overall_score",
    "objective_score",
    "quality_score",
    "human_score",
    "volume_score",
    "total_messages",
    "total_conversations",
    "human_interactions",
    "llm_reasoning",
]


def _write_rows(writer: csv.writer, rows: list[dict]) -> None:
    for r in rows:
        writer.writerow([
            r["created_at"],
            r["grading_run_id"],
            r["workout_id"],
            r["student_name"],
            r["bot_name"],
            round(r["overall_score"], 2),
            round(r["objective_score"], 2),
            round(r["quality_score"], 2),
            round(r["human_score"], 2),
            round(r["volume_score"], 2),
            r["total_messages"],
            r["total_conversations"],
            r["human_interactions"],
            r["llm_reasoning"],
        ])


async def export_all_csv() -> str:
    """Export full grade history for all workouts as CSV text."""
    rows = await queries.get_all_grades_history()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(_HEADERS)
    _write_rows(writer, rows)
    return output.getvalue()
