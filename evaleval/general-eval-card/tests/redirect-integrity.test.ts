import { readFileSync } from "fs"
import { fileURLToPath } from "url"

import { DuckDBConnection } from "@duckdb/node-api"
import { beforeAll, describe, expect, it } from "vitest"

// Server-FREE data-contract checks for the model URL redirect map + resolver
// fallback invariants, asserted against a Stage-J warehouse snapshot. Opt-in via
// `SNAPSHOT_URL=<warehouse> pnpm test:integrity` — self-skips in the default
// `pnpm test` run (mirrors the RUN_DRIFT pattern in upstream-drift.test.ts) so it
// never blocks a dev or a deploy. The server-BOUND checks (page rendering, chart
// content, redirect-preservation) live in the Playwright e2e suite + PREFLIGHT.md.
//
// Why this exists: "the page returns 200" != "correct". The redirect map and the
// raw_model_ids fallback have invariants that, if violated, silently break model
// pages (folded ids 404, an inverted map 301s working URLs to dead leaves). See
// tests/PREFLIGHT.md for the full bug taxonomy.

const SNAPSHOT = (process.env.SNAPSHOT_URL || "").replace(/\/+$/, "")
const shouldRun = !!SNAPSHOT
const MAP_PATH = fileURLToPath(new URL("../lib/model-url-redirects.ts", import.meta.url))

const dec = (s: string) => { try { return decodeURIComponent(s) } catch { return s } }
const listItems = (v: unknown): string[] =>
  Array.isArray(v) ? v.map(String)
    : v && typeof v === "object" && Array.isArray((v as { items?: unknown[] }).items)
      ? (v as { items: unknown[] }).items.map(String)
      : []

describe.skipIf(!shouldRun)("redirect-map + fallback integrity (vs SNAPSHOT_URL)", () => {
  let map: [string, string][] = []
  let keys: Set<string>
  const addressable = new Set<string>() // decoded route forms that resolve to a page
  const rawOwners = new Map<string, Set<string>>() // raw spelling -> owning group(s)
  let nullRaw = 0
  let rowCount = 0

  beforeAll(async () => {
    map = [...readFileSync(MAP_PATH, "utf8").matchAll(/\["([^"]+)",\s*"([^"]+)"\]/g)].map((m) => [m[1], m[2]])
    keys = new Set(map.map(([k]) => k))
    const con = await DuckDBConnection.create()
    await con.run("INSTALL httpfs; LOAD httpfs;")
    const rows = (await con.runAndReadAll(
      `SELECT model_id, route_id, model_route_id, model_group_id, model_key, raw_model_ids
       FROM read_parquet('${SNAPSHOT}/models_view.parquet')`,
    )).getRowObjects()
    rowCount = rows.length
    for (const r of rows) {
      for (const v of [r.model_id, r.model_route_id, r.route_id, r.model_group_id, r.model_key]) {
        if (v) addressable.add(dec(String(v)))
      }
      if (r.raw_model_ids == null) nullRaw++
      for (const raw of listItems(r.raw_model_ids)) {
        const set = rawOwners.get(String(raw)) ?? rawOwners.set(String(raw), new Set()).get(String(raw))!
        set.add(String(r.model_id))
      }
    }
  }, 120_000)

  it("redirect map has no self-redirects", () => {
    expect(map.filter(([k, v]) => k === v)).toEqual([])
  })

  it("redirect map has no chains/loops (no target is also a key)", () => {
    expect(map.filter(([, v]) => keys.has(v)).map(([, v]) => v)).toEqual([])
  })

  it("every redirect target is an addressable route", () => {
    const dead = [...new Set(map.map(([, v]) => v))].filter((t) => !addressable.has(dec(t)))
    expect(dead, `dead targets: ${dead.slice(0, 8)}`).toEqual([])
  })

  it("direction is folded->group (no addressable id is a redirect KEY)", () => {
    // An addressable key means the map redirects a WORKING page away — the
    // inverted-map bug.
    const inverted = map.filter(([k]) => addressable.has(dec(k))).map(([k]) => k)
    expect(inverted, `addressable ids used as redirect keys: ${inverted.slice(0, 8)}`).toEqual([])
  })

  it("every redirect key is a known folded raw_model_id", () => {
    const orphan = map.filter(([k]) => !addressable.has(dec(k)) && !rawOwners.has(dec(k))).map(([k]) => k)
    expect(orphan, `orphan keys (neither addressable nor a raw id): ${orphan.slice(0, 8)}`).toEqual([])
  })

  it("no raw_model_id belongs to >1 group (LIMIT 1 fallback is unambiguous)", () => {
    const multi = [...rawOwners].filter(([, s]) => s.size > 1).map(([k]) => k)
    expect(multi, `raw ids in >1 group: ${multi.slice(0, 8)}`).toEqual([])
  })

  it("no models_view row has NULL raw_model_ids (the fallback scans this column)", () => {
    expect(nullRaw, `${nullRaw}/${rowCount} rows have NULL raw_model_ids`).toBe(0)
  })
})
