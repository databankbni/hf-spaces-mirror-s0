import { defineConfig } from "@playwright/test"

// Frontend preflight e2e (opt-in): `SNAPSHOT_URL=<warehouse> pnpm test:e2e`.
// NOT part of `pnpm test` and nothing gates deploy — it's a correctness check you
// run before shipping a meaningful frontend change. See tests/PREFLIGHT.md.
//
// The webServer block boots `pnpm dev` against the snapshot itself (and reuses an
// already-running one), so there's no manual server dance. When SNAPSHOT_URL is
// unset the spec self-skips.
const SNAPSHOT_URL = process.env.SNAPSHOT_URL
const PORT = Number(process.env.PORT || 3211)

export default defineConfig({
  testDir: "tests/e2e",
  // Each test sweeps many pages; give them room (they parallelize internally).
  timeout: 300_000,
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: { baseURL: `http://localhost:${PORT}` },
  webServer: SNAPSHOT_URL
    ? {
        command: `pnpm dev -p ${PORT}`,
        url: `http://localhost:${PORT}`,
        timeout: 120_000,
        reuseExistingServer: true,
        env: { DATA_BACKEND: "v2", SNAPSHOT_URL },
      }
    : undefined,
})
