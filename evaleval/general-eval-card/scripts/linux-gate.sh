#!/usr/bin/env bash
#
# Linux gate — enforces the rule "never deploy code that hasn't run on linux."
# Pushing to the HF Space deploys to prod and runs NO tests there, so this gate
# (wired as a pre-push hook) is the only check between a local change and
# production. It catches the class of bug that passes on Mac and broke prod:
# the linux-x64 @duckdb/node-api binding crashing while marshalling
# struct/timestamp columns, and the connection singleton wedging on a transient
# boot error.
#
# Two legs:
#   (1) host vitest — unit/logic suite (fast; connection-reset + transforms).
#   (2) linux/amd64 DuckDB read-path smoke on the prod-pinned binding (the real
#       net for the Mac↔linux divergence).
#
# Requires Docker. Coverage grows: add parity / render-equivalence tests to the
# linux leg as they land (see scripts/linux-gate/README.md).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Default to the latest published snapshot; pin by exporting SNAPSHOT_URL first.
if [ -z "${SNAPSHOT_URL:-}" ]; then
  echo "[linux-gate] resolving latest published snapshot (set SNAPSHOT_URL to pin)…"
  SNAPSHOT_URL="$(node "$ROOT/scripts/resolve-latest-snapshot.mjs")" || {
    echo "[linux-gate] could not resolve latest snapshot — set SNAPSHOT_URL explicitly" >&2
    exit 2
  }
fi

echo "[linux-gate] (1/2) host unit/logic suite (vitest)…"
pnpm vitest run

echo "[linux-gate] (2/2) linux/amd64 DuckDB read-path smoke (prod binding)…"
DUCKDB_VERSION="$(grep -m1 -oE '@duckdb/node-api@[0-9][A-Za-z0-9.+-]*' pnpm-lock.yaml | sed 's#.*@##' || true)"
DUCKDB_VERSION="${DUCKDB_VERSION:-1.5.3-r.2}"
echo "[linux-gate]   binding @duckdb/node-api@${DUCKDB_VERSION} (from pnpm-lock); snapshot ${SNAPSHOT_URL}"
docker build --platform=linux/amd64 --build-arg "DUCKDB_VERSION=${DUCKDB_VERSION}" \
  -t evalcard-linux-gate "$ROOT/scripts/linux-gate" >/dev/null
docker run --platform=linux/amd64 --rm -e SNAPSHOT_URL="$SNAPSHOT_URL" evalcard-linux-gate

echo "[linux-gate] PASS ✅"
