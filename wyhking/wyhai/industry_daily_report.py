from __future__ import annotations

from pathlib import Path
from typing import Any

from crawler.config import configure_logging
from crawler.db import init_db
from crawler.report.daily_pdf import generate_daily_report
from crawler.utils.time_parse import date_range_window, natural_day_window, since_days_window


def _build_window(date: str | None = "yesterday", start_date: str | None = None, end_date: str | None = None):
    if date:
        return natural_day_window(date)
    if start_date or end_date:
        if not start_date or not end_date:
            raise ValueError("start_date 和 end_date 必须同时传入")
        return date_range_window(start_date, end_date)
    return since_days_window(1)


def generate_industry_daily_report(
    date: str | None = "yesterday",
    output: str | Path | None = None,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    yiche_screenshot: str | None = None,
    autohome_listings: str | None = None,
    guazi_listings: str | None = None,
) -> dict[str, Any]:
    """Generate the automotive industry daily report as an AI pricing assistant module.

    This is intentionally a thin wrapper around the verified crawler/report
    implementation so the pricing assistant can call the daily report capability
    without duplicating crawler logic.
    """

    configure_logging()
    init_db()

    output_pdf = Path(output or "outputs/daily_report_yesterday.pdf")
    listing_paths = {
        "汽车之家": autohome_listings,
        "瓜子": guazi_listings,
        "易车降价榜截图": yiche_screenshot,
    }
    result = generate_daily_report(
        _build_window(date=date, start_date=start_date, end_date=end_date),
        output_pdf,
        listing_paths=listing_paths,
    )

    return {
        "pdf_path": str(result["pdf"]),
        "dated_pdf_path": str(result.get("dated_pdf")),
        "html_path": str(result["html"]),
        "markdown_path": str(result["markdown"]),
        "sources_xlsx_path": str(result["sources_xlsx"]),
        "stats": result.get("stats", {}),
        "sections": result.get("sections", {}),
    }
