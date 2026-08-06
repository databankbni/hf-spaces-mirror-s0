"""Simple benchmark harness for the /identify endpoint.

Usage (example):
  python benchmark_identify.py --image path/to/test.jpg --concurrency 4 --requests 50

This does NOT do server-side timing instrumentation; it measures client-perceived latency.
"""

import argparse
import os
import statistics
import time
import concurrent.futures

import requests


def one_request(session: requests.Session, url: str, image_path: str, timeout: float = 180.0):
    with open(image_path, "rb") as f:
        files = {"bird_image": (os.path.basename(image_path), f, "image/jpeg")}
        start = time.perf_counter()
        r = session.post(url, files=files, timeout=timeout)
        elapsed = time.perf_counter() - start
    return r.status_code, elapsed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True, help="Path to a test bird image")
    ap.add_argument("--url", default="http://127.0.0.1:5000/identify", help="/identify endpoint")
    ap.add_argument("--requests", type=int, default=20)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--timeout", type=float, default=180.0)
    args = ap.parse_args()

    image_path = args.image
    if not os.path.exists(image_path):
        raise SystemExit(f"Image not found: {image_path}")

    latencies = []
    codes = []

    with requests.Session() as session:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            futures = [
                ex.submit(one_request, session, args.url, image_path, args.timeout)
                for _ in range(args.requests)
            ]
            for fut in concurrent.futures.as_completed(futures):
                code, elapsed = fut.result()
                codes.append(code)
                latencies.append(elapsed)

    latencies.sort()

    def pct(p):
        if not latencies:
            return None
        idx = int(round((p / 100) * (len(latencies) - 1)))
        return latencies[idx]

    ok = sum(1 for c in codes if 200 <= c < 300)
    fail = len(codes) - ok

    print("=== /identify benchmark ===")
    print(f"Requests: {len(codes)} | OK: {ok} | Fail: {fail}")
    if latencies:
        print(f"Mean latency: {statistics.mean(latencies):.3f}s")
        print(f"P50 latency: {pct(50):.3f}s")
        print(f"P90 latency: {pct(90):.3f}s")
        print(f"P95 latency: {pct(95):.3f}s")
        print(f"P99 latency: {pct(99):.3f}s")
        print(f"Max latency: {max(latencies):.3f}s")


if __name__ == "__main__":
    main()

