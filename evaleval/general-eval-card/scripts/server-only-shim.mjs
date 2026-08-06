// Monkey-patch require/import to no-op the `server-only` package, which
// throws when imported outside a Next.js Server Component context. This lets
// the audit script + adapter tests import lib/hf-data.ts and lib/model-data.ts
// directly. Same trick as tests/server-only-stub.ts but at the require/import
// resolution level instead of via vitest's alias config.

import { createRequire } from "node:module"
import Module from "node:module"

const require = createRequire(import.meta.url)
const original = Module.prototype.require
Module.prototype.require = function patchedRequire(specifier) {
  if (specifier === "server-only") return {}
  return original.apply(this, arguments)
}
