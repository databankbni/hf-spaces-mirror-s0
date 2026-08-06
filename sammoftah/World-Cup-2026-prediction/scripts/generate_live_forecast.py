from __future__ import annotations

import argparse
from pathlib import Path

from underdog_lab.release.live_forecast import generate_live_forecast


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    forecast, manifest = generate_live_forecast(
        args.fixture_id,
        args.output_dir,
    )
    print(f"Wrote immutable forecast: {forecast}")
    print(f"Wrote SHA-256 manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
