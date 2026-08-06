from __future__ import annotations

import argparse
import json
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Space base URL, for example https://name.hf.space")
    args = parser.parse_args()
    with urllib.request.urlopen(args.url, timeout=60) as response:
        body = response.read(512).decode("utf-8", errors="replace")
        if response.status != 200:
            raise SystemExit(f"Unexpected status: {response.status}")
        print(json.dumps({"status": response.status, "preview": body[:120]}))


if __name__ == "__main__":
    main()
