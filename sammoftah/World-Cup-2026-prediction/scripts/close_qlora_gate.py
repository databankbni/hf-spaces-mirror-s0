from __future__ import annotations

import argparse
from pathlib import Path

from underdog_lab.release.qlora_gate import close_qlora_gate


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recompute and close the QLoRA release gate."
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/qlora_gate_report.json"),
    )
    args = parser.parse_args()
    report = close_qlora_gate(args.root.resolve(), args.output.resolve())
    print(
        f"QLoRA gate: {report['status']} "
        f"({report['computed_decision']}, "
        f"release_blocking={report['release_blocking']})"
    )
    return 0 if report["status"] == "closed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
