#!/usr/bin/env tsx
// Generate lib/model-url-redirects.ts from the warehouse models_view.
//
// The producer folds variants / dated snapshots / older-cased spellings into a
// group whose model_route_id is the addressable page; the folded spellings live
// only in raw_model_ids. This emits a folded-spelling -> group-route 301 map so
// a link to any folded spelling lands on the real group page. Targets are always
// addressable by construction, so the map can never 301 to a dead URL.
//
// Usage:
//   DATA_BACKEND=v2 SNAPSHOT_URL=<warehouse-url-or-file> tsx scripts/generate-model-redirects.ts
//   tsx scripts/generate-model-redirects.ts --snapshot <warehouse-url> --out lib/model-url-redirects.ts

import { writeFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

import { DuckDBConnection } from "@duckdb/node-api"

import {
  buildRedirectsFromModelsView,
  serializeRedirectModule,
  type ModelsViewRow,
} from "../lib/model-url-redirects-build"

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..")
const DEFAULT_OUT = resolve(REPO_ROOT, "lib/model-url-redirects.ts")

function parseArg(flag: string): string | undefined {
  const i = process.argv.indexOf(flag)
  return i >= 0 ? process.argv[i + 1] : undefined
}

// @duckdb/node-api returns LIST columns as { items: [...] }.
function listItems(v: unknown): string[] {
  if (Array.isArray(v)) return v.map(String)
  if (v && typeof v === "object" && Array.isArray((v as { items?: unknown[] }).items)) {
    return (v as { items: unknown[] }).items.map(String)
  }
  return []
}

function str(v: unknown): string | null {
  return v == null ? null : String(v)
}

async function main() {
  const snapshot = (parseArg("--snapshot") ?? process.env.SNAPSHOT_URL ?? "").replace(/\/+$/, "")
  if (!snapshot) {
    throw new Error("need --snapshot <warehouse-url> or SNAPSHOT_URL set")
  }
  const outPath = resolve(parseArg("--out") ?? DEFAULT_OUT)

  const con = await DuckDBConnection.create()
  await con.run("INSTALL httpfs; LOAD httpfs;")
  const reader = await con.runAndReadAll(
    `SELECT model_route_id, model_id, route_id, model_key, model_group_id, raw_model_ids
     FROM read_parquet('${snapshot}/models_view.parquet')`,
  )
  const raw = reader.getRowObjects() as Array<Record<string, unknown>>
  const rows: ModelsViewRow[] = raw.map((r) => ({
    model_route_id: String(r.model_route_id ?? ""),
    model_id: str(r.model_id),
    route_id: str(r.route_id),
    model_key: str(r.model_key),
    model_group_id: str(r.model_group_id),
    raw_model_ids: listItems(r.raw_model_ids),
  }))

  const { redirects, ambiguous } = buildRedirectsFromModelsView(rows)
  writeFileSync(outPath, serializeRedirectModule(redirects, { source: snapshot }))

  // eslint-disable-next-line no-console
  console.log(
    `wrote ${outPath}: ${redirects.size} redirects from ${rows.length} models_view rows` +
      (ambiguous.size ? `; ${ambiguous.size} ambiguous spellings excluded` : ""),
  )
  if (ambiguous.size > 0) {
    // eslint-disable-next-line no-console
    console.log(`  ambiguous (fan out to >1 group): ${[...ambiguous.keys()].slice(0, 10).join(", ")}`)
  }
}

main().catch((e) => {
  // eslint-disable-next-line no-console
  console.error(e)
  process.exit(1)
})
