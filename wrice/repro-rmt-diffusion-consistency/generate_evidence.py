from __future__ import annotations

import json
from pathlib import Path

from rmt_diffusion.evidence import build_evidence


def main() -> None:
    root = Path(__file__).resolve().parent
    out = root / "evidence" / "bundle.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_evidence(), indent=2, sort_keys=True) + "\n")
    print(out)


if __name__ == "__main__":
    main()
