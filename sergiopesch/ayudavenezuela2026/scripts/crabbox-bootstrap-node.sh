#!/usr/bin/env bash
set -euo pipefail

if command -v npm >/dev/null 2>&1; then
  exit 0
fi

node_version="${NODE_VERSION:-22.13.1}"
case "$(uname -m)" in
  x86_64 | amd64) node_arch="x64" ;;
  arm64 | aarch64) node_arch="arm64" ;;
  *)
    echo "Unsupported runner architecture: $(uname -m)" >&2
    exit 1
    ;;
esac

node_name="node-v${node_version}-linux-${node_arch}"
node_root="${PWD}/.crabbox/node"
node_dir="${node_root}/${node_name}"
node_archive="${node_root}/${node_name}.tar.xz"
node_seed_archive="${PWD}/.crabbox-seed/${node_name}.tar.xz"
node_url="https://nodejs.org/dist/v${node_version}/${node_name}.tar.xz"

mkdir -p "${node_root}"

download_node_archive() {
  rm -f "${node_archive}"

  if command -v curl >/dev/null 2>&1; then
    for attempt in 1 2 3 4 5; do
      echo "Downloading ${node_name} with curl (attempt ${attempt}/5)" >&2
      if curl --fail --location --show-error --silent --retry 3 --retry-all-errors --connect-timeout 30 --max-time 240 "${node_url}" -o "${node_archive}"; then
        return 0
      fi
      rm -f "${node_archive}"
      sleep "$((attempt * 2))"
    done
  fi

  if command -v wget >/dev/null 2>&1; then
    for attempt in 1 2 3 4 5; do
      echo "Downloading ${node_name} with wget (attempt ${attempt}/5)" >&2
      if wget --tries=3 --timeout=60 -qO "${node_archive}" "${node_url}"; then
        return 0
      fi
      rm -f "${node_archive}"
      sleep "$((attempt * 2))"
    done
  fi

  if command -v python3 >/dev/null 2>&1; then
    for attempt in 1 2 3 4 5; do
      echo "Downloading ${node_name} with python3 (attempt ${attempt}/5)" >&2
      if python3 - "${node_url}" "${node_archive}" <<'PY'
import sys
from urllib.request import urlopen

url, output = sys.argv[1], sys.argv[2]
with urlopen(url, timeout=240) as response, open(output, "wb") as target:
    target.write(response.read())
PY
      then
        return 0
      fi
      rm -f "${node_archive}"
      sleep "$((attempt * 2))"
    done
  fi

  echo "Could not download ${node_url}; runner needs npm or outbound access to nodejs.org." >&2
  return 1
}

if [ ! -x "${node_dir}/bin/npm" ]; then
  echo "npm is missing; downloading ${node_name} for Crabbox" >&2
  if [ -f "${node_seed_archive}" ]; then
    echo "Using synced Node seed archive ${node_seed_archive}" >&2
    cp "${node_seed_archive}" "${node_archive}"
  else
    download_node_archive
  fi
  tar -xJf "${node_archive}" -C "${node_root}"
fi

if command -v sudo >/dev/null 2>&1; then
  sudo mkdir -p /usr/local/bin
  sudo ln -sf "${node_dir}/bin/node" /usr/local/bin/node
  sudo ln -sf "${node_dir}/bin/npm" /usr/local/bin/npm
  sudo ln -sf "${node_dir}/bin/npx" /usr/local/bin/npx
else
  export PATH="${node_dir}/bin:${PATH}"
fi

hash -r
npm --version >/dev/null
