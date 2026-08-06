import { DuckDBConnection } from "@duckdb/node-api"
import { expect, test, type Browser } from "@playwright/test"

// Frontend correctness e2e — the layer naive "page returns 200" checks miss.
// Opt-in via `SNAPSHOT_URL=<warehouse> pnpm test:e2e`; self-skips otherwise.
// Verifies, against the live server + comparison-index ground truth:
//  - model/eval/developer pages render (incl. folded-id + encoded-name regressions),
//  - 100% of folded model ids resolve (the raw_model_ids fallback),
//  - comparison charts render real PEER bars (not just the current model), 0 "Unknown Model".
// Full bug taxonomy + known limitations: tests/PREFLIGHT.md.

const BASE = `http://localhost:${process.env.PORT || 3211}`
const SNAPSHOT = (process.env.SNAPSHOT_URL || "").replace(/\/+$/, "")
const SAMPLE = 30
const CHART_MODELS = 16

test.describe.configure({ mode: "serial" })
test.skip(!SNAPSHOT, "set SNAPSHOT_URL to run the frontend preflight e2e")

const ERROR_MARKERS = [
  "Model not found", "Failed to load model data", "Eval not found",
  "Benchmark not found", "Failed to load", "Application error",
  "Something went wrong", "This page could not be found",
]

const enc = (s: unknown) => encodeURIComponent(String(s))
const norm = (s: unknown) => String(s || "").toLowerCase().replace(/[^a-z0-9]/g, "")
const asArray = (j: any): any[] => Array.isArray(j) ? j
  : (j && typeof j === "object" && ["models", "evals", "developers", "items", "rows", "cards", "data"].map((k) => j[k]).find(Array.isArray)) || []
const sample = <T>(a: T[], n: number): T[] => a.length <= n ? a.slice() : Array.from({ length: n }, (_, i) => a[Math.floor(i * (a.length / n))])
const listItems = (v: any): string[] => Array.isArray(v) ? v.map(String) : Array.isArray(v?.items) ? v.items.map(String) : []
const getJson = async (p: string) => { const r = await fetch(`${BASE}${p}`); return r.ok ? r.json() : null }
const getJsonT = async (p: string, ms = 90_000, tries = 2) => {
  for (let i = 0; i < tries; i++) {
    try { const r = await fetch(`${BASE}${p}`, { signal: AbortSignal.timeout(ms) }); if (r.ok) return r.json() } catch { /* retry */ }
  }
  return null
}
async function mapLimit<T, R>(items: T[], limit: number, fn: (x: T) => Promise<R>): Promise<R[]> {
  const out = new Array<R>(items.length)
  let i = 0
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (i < items.length) { const idx = i++; out[idx] = await fn(items[idx]) }
  }))
  return out
}

let models: any[] = []
let evals: any[] = []
let devs: any[] = []
let folded: string[] = []
let expectedPeersFor: (routeId: string) => string[]

test.beforeAll(async () => {
  models = asArray(await getJson("/api/model-cards-lite"))
  evals = asArray(await getJson("/api/eval-list-lite"))
  devs = asArray(await getJson("/api/developers"))
  expect(models.length, "model-cards-lite empty").toBeGreaterThan(0)

  // Comparison-index is the chart ground truth — unavailable must be a HARD fail,
  // not a silent skip (else the whole chart layer disables itself).
  const ci = await getJsonT("/api/comparison-index")
  expect(ci?.by_model && ci?.evals, "comparison-index unavailable — chart check cannot run").toBeTruthy()
  expectedPeersFor = (routeId: string) => {
    const byModel = ci.by_model[routeId]
    if (!byModel) return []
    const peers = new Set<string>()
    for (const evalId of Object.keys(byModel)) {
      for (const metric of (ci.evals[evalId]?.metrics ?? [])) {
        for (const s of metric.scores) {
          if (s.model_route_id === routeId) continue
          const n = norm(s.model_family_name || s.model_family_id)
          if (n) peers.add(n)
        }
      }
    }
    return [...peers]
  }

  // Discover folded ids exhaustively from the warehouse (not a tiny stride).
  const con = await DuckDBConnection.create()
  await con.run("INSTALL httpfs; LOAD httpfs;")
  const rows = (await con.runAndReadAll(
    `SELECT model_id, raw_model_ids FROM read_parquet('${SNAPSHOT}/models_view.parquet') WHERE len(raw_model_ids) > 0`,
  )).getRowObjects()
  const set = new Set<string>()
  for (const r of rows) for (const raw of listItems(r.raw_model_ids)) {
    if (String(raw).toLowerCase() !== String(r.model_id).toLowerCase()) set.add(String(raw))
  }
  folded = [...set]
  expect(folded.length, "folded-id regression set empty — discovery/data path changed").toBeGreaterThan(0)
})

test("100% of folded model ids resolve (raw_model_ids fallback)", async () => {
  const statuses = await mapLimit(folded, 12, async (raw) => {
    const r = await fetch(`${BASE}/api/model-summary?id=${enc(raw)}`, { signal: AbortSignal.timeout(30_000) }).catch(() => null)
    return { raw, status: r ? r.status : 0 }
  })
  const bad = statuses.filter((s) => s.status !== 200).map((s) => s.raw)
  expect(bad, `${bad.length}/${folded.length} folded ids do not resolve: ${bad.slice(0, 8)}`).toEqual([])
})

test("model / eval / developer pages render (incl. regression sets)", async ({ browser }) => {
  const seen = new Set<string>()
  const targets: { cls: string; url: string }[] = []
  const add = (cls: string, url: string) => { if (url && !seen.has(url)) { seen.add(url); targets.push({ cls, url }) } }

  for (const m of sample(models, SAMPLE)) add("model", `/models/${enc(m.model_id || m.id || m.model_key)}`)
  for (const raw of sample(folded, 25)) add("model(folded)", `/models/${enc(raw)}`)
  for (const e of sample(evals, SAMPLE)) { const id = e.evaluation_id || e.id || e.benchmark_id; if (id) add("eval", `/evals/${String(id).replace(/%2F/g, "/")}`) }
  const devUrl = (rid: string) => `/developers/${String(rid).replace(/%2F/g, "/")}`
  const encodedDevs = devs.filter((d) => /[^A-Za-z0-9._/-]/.test(String(d.developer || "")) || /%(?!2F)/i.test(String(d.route_id || "")))
  expect(encodedDevs.length, "encoded-developer regression set empty — data path changed").toBeGreaterThan(0)
  for (const d of encodedDevs) if (d.route_id) add("developer(encoded)", devUrl(d.route_id))
  for (const d of sample(devs, 20)) if (d.route_id) add("developer", devUrl(d.route_id))

  const results = await mapLimit(targets, 6, async (t) => {
    const page = await browser.newPage()
    const errs: string[] = []
    page.on("console", (m) => { if (m.type() === "error") errs.push(m.text().slice(0, 120)) })
    page.on("pageerror", (e) => errs.push(String(e).slice(0, 120)))
    let status = 0
    try { const r = await page.goto(`${BASE}${t.url}`, { waitUntil: "networkidle", timeout: 45_000 }); status = r ? r.status() : 0; await page.waitForTimeout(700) }
    catch (e) { errs.push(`goto: ${String(e).slice(0, 120)}`) }
    const text = await page.evaluate(() => document.body?.innerText || "").catch(() => "")
    const marker = ERROR_MARKERS.find((m) => text.includes(m))
    await page.close()
    return (!(status > 0 && status < 400) || marker || errs.length)
      ? `${t.url} [${status}]${marker ? ` "${marker}"` : ""}${errs.length ? ` ${JSON.stringify(errs.slice(0, 2))}` : ""}`
      : null
  })
  const broken = results.filter(Boolean) as string[]
  expect(broken, `${broken.length} broken pages:\n  ${broken.slice(0, 15).join("\n  ")}`).toEqual([])
})

test("comparison charts render real peer bars (not only the current model)", async ({ browser }) => {
  const candidates = sample(models, CHART_MODELS)
    .map((m) => enc(m.model_id || m.id || m.model_key))
    .filter((routeId) => expectedPeersFor(routeId).length > 0)
  const per = await mapLimit(candidates, 6, async (routeId) => {
    const expected = expectedPeersFor(routeId)
    const page = await browser.newPage()
    const problems: string[] = []
    let bars: { id: string | null; cur: boolean }[] = []
    try {
      await page.goto(`${BASE}/models/${routeId}`, { waitUntil: "networkidle", timeout: 45_000 })
      await page.waitForTimeout(1000)
      const unknown = ((await page.evaluate(() => document.body?.innerText || "")).match(/Unknown Model/g) || []).length
      bars = await page.$$eval("[data-model-bar]", (els) =>
        els.map((e) => ({ id: e.getAttribute("data-model-bar"), cur: e.getAttribute("data-bar-current") === "1" })))
      const peerBars = bars.filter((b) => !b.cur)
      const currentBars = bars.length - peerBars.length
      // MULTIPLE charts rendered but NONE show a peer bar => the only-current-model bug.
      if (currentBars >= 2 && peerBars.length === 0) problems.push(`${routeId}: ${expected.length} peers in index but 0 peer bars`)
      if (peerBars.some((b) => b.id === routeId)) problems.push(`${routeId}: current model rendered as its own peer (double-count)`)
      if (unknown > 0) problems.push(`${routeId}: ${unknown} "Unknown Model" labels`)
    } catch (e) { problems.push(`${routeId}: ${String(e).slice(0, 80)}`) }
    await page.close()
    return { bars: bars.length, problems }
  })
  const charted = candidates.length
  const totalBars = per.reduce((n, r) => n + r.bars, 0)
  const broken = per.flatMap((r) => r.problems)
  expect(charted, "no sampled model had expected peers — chart check was vacuous").toBeGreaterThan(0)
  // Suite-wide: peers expected but NO bars anywhere => the data-model-bar hook was
  // dropped or charts don't render — the chart check silently disabled itself.
  expect(totalBars, "0 chart bars across charted pages — data-model-bar hook missing or charts broken").toBeGreaterThan(0)
  expect(broken, `chart problems:\n  ${broken.slice(0, 15).join("\n  ")}`).toEqual([])
})
