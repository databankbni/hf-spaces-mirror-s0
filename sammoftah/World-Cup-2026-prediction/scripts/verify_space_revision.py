from __future__ import annotations

import argparse
import json
import time
import urllib.request


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def reachable(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.status == 200
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", required=True)
    parser.add_argument("--expected", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    deadline = time.monotonic() + args.timeout
    last = {}
    while time.monotonic() < deadline:
        try:
            last = fetch_json(
                f"https://huggingface.co/api/spaces/{args.space}"
            )
        except Exception as error:
            last = {"transient_error": str(error)}
            time.sleep(15)
            continue
        runtime = last.get("runtime") or {}
        runtime_sha = runtime.get("sha") or runtime.get("revision")
        repository_sha = last.get("sha")
        if (
            repository_sha == args.expected
            and runtime_sha == args.expected
            and runtime.get("stage") == "RUNNING"
            and reachable(args.url)
        ):
            print(json.dumps({"status": "deployed", "sha": args.expected}))
            return 0
        time.sleep(15)
    raise SystemExit(
        "Space did not reach expected runtime revision: "
        f"expected={args.expected} last={json.dumps(last)}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
