#!/bin/sh
set -eu

mkdir -p /app/data/fulltext
(
  if ! python /app/prepare_fulltext_index.py; then
    python /app/build_fulltext_db.py
  fi
) &

exec uvicorn app:app --host 0.0.0.0 --port 7860 --log-level info
