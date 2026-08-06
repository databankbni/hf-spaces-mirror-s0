# linux/amd64 gate image — runs the DuckDB read-path smoke on the SAME binding
# version prod uses, so a Mac-vs-linux marshalling divergence is caught before deploy.
# DUCKDB_VERSION is passed by scripts/linux-gate.sh, extracted from pnpm-lock.yaml
# so it can never drift from what prod actually ships.
# Platform is set by `docker build --platform=linux/amd64` in scripts/linux-gate.sh.
FROM node:18-bullseye-slim
RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates \
  && rm -rf /var/lib/apt/lists/*
WORKDIR /gate
ARG DUCKDB_VERSION=1.5.3-r.2
RUN npm install --no-audit --no-fund "@duckdb/node-api@${DUCKDB_VERSION}"
COPY smoke.mjs parity.mjs ./
# Default to the fast smoke; `docker run … parity.mjs` runs the heavier parity gate.
ENTRYPOINT ["node"]
CMD ["smoke.mjs"]
