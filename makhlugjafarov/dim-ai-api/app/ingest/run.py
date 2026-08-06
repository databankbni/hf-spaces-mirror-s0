"""
app/ingest/run.py — thin re-export shim (CP6b).

All logic has moved to the Ingestion bounded context:
  - run_ingestion -> app.ingestion.application.run_ingestion

This shim preserves back-compat for any code that still imports from app.ingest.run.
Do not add new logic here.
"""
from __future__ import annotations

from app.ingestion.application.run_ingestion import (
    run_ingestion as run_ingestion,
    main as main,
)

__all__ = ["run_ingestion", "main"]

if __name__ == "__main__":
    main()
