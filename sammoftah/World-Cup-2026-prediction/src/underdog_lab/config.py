from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
MODEL_DIR = ROOT / "models"
TRACE_DIR = DATA_DIR / "traces"

EXTRACTOR_BACKEND = os.getenv("UNDERDOG_EXTRACTOR", "auto")
LLAMA_CLI = os.getenv("UNDERDOG_LLAMA_CLI", "llama-cli")
MODEL_PATH = Path(os.getenv("UNDERDOG_MODEL_PATH", MODEL_DIR / "model.gguf"))
MODEL_REPO = os.getenv(
    "UNDERDOG_MODEL_REPO",
    "bartowski/SmolLM2-360M-Instruct-GGUF",
)
MODEL_FILENAME = os.getenv(
    "UNDERDOG_MODEL_FILENAME",
    "SmolLM2-360M-Instruct-Q8_0.gguf",
)
MAX_SCORE = int(os.getenv("UNDERDOG_MAX_SCORE", "8"))
RULESET_VERSION = "ruleset_v1"
