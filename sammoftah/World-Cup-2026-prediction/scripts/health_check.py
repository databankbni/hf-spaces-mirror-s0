from __future__ import annotations

import argparse
import json
from datetime import datetime

from underdog_lab.release.health import application_health


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--now",
        help="Optional ISO timestamp for reproducible checks.",
    )
    parser.add_argument(
        "--ignore-overdue-results",
        action="store_true",
        help=(
            "Do not fail on overdue results. The check is still reported, "
            "but does not affect the overall status. Useful when verifying "
            "a candidate snapshot that may only resolve some of the "
            "currently-overdue fixtures."
        ),
    )
    args = parser.parse_args()
    now = (
        datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        if args.now
        else None
    )
    report = application_health(now=now, ignore_overdue_results=args.ignore_overdue_results)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
