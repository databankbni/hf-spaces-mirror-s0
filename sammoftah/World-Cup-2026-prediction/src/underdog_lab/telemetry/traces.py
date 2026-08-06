from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from underdog_lab.config import TRACE_DIR


def append_trace(event: dict, path: Path | None = None) -> None:
    destination = path or TRACE_DIR / "events.jsonl"
    destination.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "trace_id": str(uuid4()),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    with destination.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=True) + "\n")
