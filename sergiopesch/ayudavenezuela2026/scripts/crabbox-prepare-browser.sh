#!/usr/bin/env bash
set -euo pipefail

seed_zip="${PWD}/.crabbox-seed/chromium-headless-shell-linux-arm64-1228.zip"
browser_root="${PWD}/.crabbox/browser/chromium-headless-shell-1228"
browser_executable="${browser_root}/chrome-linux/headless_shell"

if [ ! -x "${browser_executable}" ]; then
  if [ -f "${seed_zip}" ]; then
    mkdir -p "${browser_root}"
    if command -v unzip >/dev/null 2>&1; then
      unzip -q "${seed_zip}" -d "${browser_root}"
    elif command -v python3 >/dev/null 2>&1; then
      python3 - "${seed_zip}" "${browser_root}" <<'PY'
import sys
from zipfile import ZipFile

archive, output = sys.argv[1], sys.argv[2]
with ZipFile(archive) as zip_file:
    zip_file.extractall(output)
PY
    else
      echo "Chromium seed is present but neither unzip nor python3 is available." >&2
      exit 1
    fi
    chmod +x "${browser_executable}"
  else
    npx playwright install chromium
  fi
fi

if [ -x "${browser_executable}" ]; then
  printf '%s\n' "${browser_executable}"
fi
