from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class DailyReportDateQuery:
    requested_date: str | None
    mode: str
    matched_text: str
    is_explicit: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "requested_date": self.requested_date,
            "mode": self.mode,
            "matched_text": self.matched_text,
            "is_explicit": self.is_explicit,
        }


def _anchor_date(now: date | datetime | None = None) -> date:
    if isinstance(now, datetime):
        return now.date()
    return now or date.today()


def resolve_daily_report_date(text: Any, now: date | datetime | None = None) -> DailyReportDateQuery:
    """Resolve a report date without silently replacing it with the latest report.

    A day-only request such as ``11号日报`` means the most recent 11th that is
    not in the future. This is deterministic and works across month boundaries.
    """

    raw = str(text or "").strip()
    compact = re.sub(r"\s+", "", raw)
    today = _anchor_date(now)

    if re.search(r"前天", compact):
        target = today - timedelta(days=2)
        return DailyReportDateQuery(target.isoformat(), "exact", "前天", True)
    if re.search(r"昨天|昨日|上一期", compact):
        target = today - timedelta(days=1)
        return DailyReportDateQuery(target.isoformat(), "exact", "昨天", True)
    if re.search(r"今天|今日|最新", compact):
        return DailyReportDateQuery(None, "latest", "今天/最新", False)

    full = re.search(r"(?P<year>20\d{2})[年\-/\.](?P<month>\d{1,2})[月\-/\.](?P<day>\d{1,2})号?", compact)
    if full:
        try:
            target = date(int(full.group("year")), int(full.group("month")), int(full.group("day")))
            return DailyReportDateQuery(target.isoformat(), "exact", full.group(0), True)
        except ValueError:
            return DailyReportDateQuery(None, "invalid", full.group(0), True)

    month_day = re.search(r"(?P<month>\d{1,2})月(?P<day>\d{1,2})号?", compact)
    if month_day:
        month, day = int(month_day.group("month")), int(month_day.group("day"))
        year = today.year
        try:
            target = date(year, month, day)
            if target > today:
                target = date(year - 1, month, day)
            return DailyReportDateQuery(target.isoformat(), "exact", month_day.group(0), True)
        except ValueError:
            return DailyReportDateQuery(None, "invalid", month_day.group(0), True)

    day_only = re.search(r"(?<!\d)(?P<day>\d{1,2})号(?:的)?(?:行业|汽车|行情)?日报", compact)
    if day_only:
        day = int(day_only.group("day"))
        year, month = today.year, today.month
        for _ in range(14):
            try:
                target = date(year, month, day)
            except ValueError:
                target = None
            if target is not None and target <= today:
                return DailyReportDateQuery(target.isoformat(), "exact", day_only.group(0), True)
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        return DailyReportDateQuery(None, "invalid", day_only.group(0), True)

    return DailyReportDateQuery(None, "latest", "", False)
