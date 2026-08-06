from __future__ import annotations

import argparse
from pathlib import Path

from underdog_lab.release.preflight import run_preflight


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/submission_preflight.json"),
    )
    parser.add_argument(
        "--allow-human-pending",
        action="store_true",
        help="Return success when only account-dependent human actions remain.",
    )
    parser.add_argument(
        "--online",
        action="store_true",
        help="Verify public URLs, GitHub visibility, and Space runtime.",
    )
    args = parser.parse_args()
    report = run_preflight(
        args.root.resolve(),
        args.output.resolve(),
        online=args.online,
    )
    print(f"Submission preflight: {report['status']}")
    if report["failed_machine_checks"]:
        print("Failed checks: " + ", ".join(report["failed_machine_checks"]))
        return 1
    if report["pending_human_actions"]:
        print("Human actions: " + ", ".join(report["pending_human_actions"]))
        return 0 if args.allow_human_pending else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
