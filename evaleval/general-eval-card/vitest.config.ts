import { fileURLToPath } from "url"

import { defineConfig } from "vitest/config"

export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
      "server-only": fileURLToPath(new URL("./tests/server-only-stub.ts", import.meta.url)),
    },
  },
  test: {
    // upstream-drift.test.ts walks the full live HF cache (~16s) and is opt-in
    // via `pnpm test:drift`. The drift script sets RUN_DRIFT=1; the test file
    // self-skips otherwise. We DON'T exclude the path here because vitest's
    // exclude wins over an explicit path arg, which would silently make
    // `pnpm test:drift` find zero tests.
    // tests/e2e/ is the Playwright (@playwright/test) suite — a different runner.
    // Excluded so `pnpm test` (vitest) doesn't try to collect its *.spec.ts.
    exclude: ["**/node_modules/**", "**/dist/**", "**/tests/e2e/**"],
  },
})
