"""Thin Hugging Face Spaces launcher for the vllm-i64 API server."""

from __future__ import annotations

import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def _available_cpus() -> int:
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:
        return os.cpu_count() or 1


def _enabled(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


cpu_count = _available_cpus()
threads = max(1, min(int(os.environ.get("CPU_THREADS", cpu_count)), cpu_count))
os.environ.setdefault("OMP_NUM_THREADS", str(threads))
os.environ.setdefault("MKL_NUM_THREADS", str(threads))
os.environ.setdefault("OPENBLAS_NUM_THREADS", str(threads))
os.environ.setdefault("VLLM_I64_CPU_THREADS", str(threads))
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("MALLOC_ARENA_MAX", "2")

model_name = os.environ["MODEL_NAME"]
model_dir = os.environ.get("MODEL_DIR", "/home/user/app/model")
port = int(os.environ.get("PORT", "7860"))
config_path = Path(model_dir) / "config.json"


class _MaintenanceHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = (
            b'{"status":"maintenance",'
            b'"detail":"Checkpoint upload is still being finalized."}'
        )
        self.send_response(503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Retry-After", "30")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        return


def _wait_for_checkpoint() -> None:
    if config_path.is_file():
        return

    server = ThreadingHTTPServer(("0.0.0.0", port), _MaintenanceHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(
        f"Checkpoint not ready at {config_path}; serving maintenance status "
        "until the mounted model repository is complete.",
        flush=True,
    )
    try:
        while not config_path.is_file():
            time.sleep(10)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    print("Checkpoint detected; starting vllm-i64.", flush=True)


_wait_for_checkpoint()

import torch

use_cpu_int8 = not torch.cuda.is_available() and _enabled("CPU_INT8", True)

argv = [
    "vllm-i64", "serve", model_name,
    "--checkpoint", model_dir,
    "--host", "0.0.0.0",
    "--port", str(port),
    "--dtype", "float16" if torch.cuda.is_available() else "float32",
    "--quantization", "int8" if use_cpu_int8 else "none",
    "--max-batch-size", os.environ.get("MAX_BATCH_SIZE", "4"),
    "--max-kv-blocks", os.environ.get("MAX_KV_BLOCKS", "128"),
    "--chunk-size", os.environ.get("PREFILL_CHUNK_SIZE", "256"),
    "--rate-limit", os.environ.get("RATE_LIMIT", "60"),
    "--max-pending", os.environ.get("MAX_PENDING", "16"),
]
api_key = os.environ.get("VLLM_I64_API_KEY")
if api_key:
    argv.extend(["--api-key", api_key])
sys.argv = argv

from vllm_i64.cli import main

main()
