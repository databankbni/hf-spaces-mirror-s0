import "./server-only-shim.mjs"
import fs from "fs"
import path from "path"

// Audit script for `notes/transformations/11-benchmark-card-attachment.md`.
// Walks .cache/hf-data/ and quantifies:
//   1. % of evals with `benchmark_card` already inline vs needing runtime lookup
//   2. distribution of which candidate position (1st/2nd/3rd/none) resolves
//      under each retry order (summary path: name, name, key; list path: name,
//      key, name)
//   3. benchmark cards in benchmark-metadata.json with no inbound match from
//      any eval (orphaned cards)
//   4. evals reachable only via 2nd or 3rd candidate (the load-bearing retry
//      tail — these are the rows that would 404 if pipeline switched to a
//      single-candidate lookup without first inlining benchmark_card)
//   5. map-build first-write-wins collisions (cards silently dropped)

const CACHE_DIR = ".cache/hf-data"

if (!fs.existsSync(CACHE_DIR)) {
  console.error(`[verify-benchmark-card-attachment] Cache missing at ${CACHE_DIR}.`)
  console.error("Run `pnpm cache-hf-data` first to prime the local HF data cache.")
  process.exit(1)
}

// ---------------------------------------------------------------------------
// Verbatim copies of the TS transformation pieces.
// ---------------------------------------------------------------------------

function normalizeBenchmarkKey(name) {
  if (!name) return ""
  return name
    .replace(/^[a-z0-9_]+ ?\//i, "")
    .toLowerCase()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
}

function candidateBenchmarkKeys(name) {
  const base = normalizeBenchmarkKey(name)
  return Array.from(
    new Set([
      base,
      base.replace(/-/g, " "),
      base.replace(/ /g, "-"),
      base.replace(/[^a-z0-9]/g, ""),
    ])
  )
}

function buildMap(cards) {
  const map = new Map()
  const collisions = []
  for (const card of Object.values(cards)) {
    if (!card?.benchmark_details?.name) continue
    for (const key of candidateBenchmarkKeys(card.benchmark_details.name)) {
      const existing = map.get(key)
      if (existing) {
        if (existing !== card) {
          collisions.push({
            key,
            kept: existing.benchmark_details.name,
            dropped: card.benchmark_details.name,
          })
        }
      } else {
        map.set(key, card)
      }
    }
  }
  return { map, collisions }
}

function getBenchmarkCard(map, benchmarkName) {
  for (const key of candidateBenchmarkKeys(benchmarkName)) {
    const card = map.get(key)
    if (card) return card
  }
  return null
}

// ---------------------------------------------------------------------------
// Replicate hfEvalEntryToListItem just for the two composite_benchmark_* fields.
// (Source: lib/model-data.ts:427-505. We don't need the rest of the adapter.)
// ---------------------------------------------------------------------------

function deriveCompositeFields(entry) {
  // Pipeline doesn't always populate `evaluation_name`; the adapter has a
  // chain of fallbacks. For audit purposes use the same chain.
  const rawDisplayName =
    entry.evaluation_name || entry.display_name || entry.benchmark_leaf_name || entry.eval_summary_id
  // composite_benchmark_key = entry.benchmark
  // composite_benchmark_name = a display-name lookup; we approximate with
  // benchmark_parent_name || benchmark (matches getBenchmarkDisplayName fallback).
  return {
    evaluation_name: rawDisplayName,
    composite_benchmark_key: entry.benchmark ?? "",
    composite_benchmark_name: entry.benchmark_parent_name || entry.benchmark || "",
  }
}

// ---------------------------------------------------------------------------
// Load corpus
// ---------------------------------------------------------------------------

const benchmarkMetadata = JSON.parse(
  fs.readFileSync(path.join(CACHE_DIR, "benchmark-metadata.json"), "utf8")
)
const evalList = JSON.parse(fs.readFileSync(path.join(CACHE_DIR, "eval-list.json"), "utf8"))
const evals = evalList.evals ?? []
const evalsDir = path.join(CACHE_DIR, "evals")
const evalDetailFiles = fs.readdirSync(evalsDir)

console.log(`=== Corpus ===`)
console.log(`  benchmark-metadata.json cards: ${Object.keys(benchmarkMetadata).length}`)
console.log(`  eval-list.json entries: ${evals.length}`)
console.log(`  evals/*.json detail files: ${evalDetailFiles.length}`)

// ---------------------------------------------------------------------------
// 1. Inline-vs-lookup coverage
// ---------------------------------------------------------------------------

let inline = 0
let needsLookup = 0
for (const e of evals) {
  if (e.benchmark_card) inline++
  else needsLookup++
}
console.log(`\n=== Inline benchmark_card coverage in eval-list.json ===`)
console.log(
  `  inline (pipeline already populated): ${inline} (${((inline / evals.length) * 100).toFixed(1)}%)`
)
console.log(
  `  needs runtime lookup: ${needsLookup} (${((needsLookup / evals.length) * 100).toFixed(1)}%)`
)

// Same check on the per-eval detail files
let detailInline = 0
let detailMissing = 0
for (const f of evalDetailFiles) {
  const j = JSON.parse(fs.readFileSync(path.join(evalsDir, f), "utf8"))
  if (j.benchmark_card) detailInline++
  else detailMissing++
}
console.log(`\n=== Inline benchmark_card coverage in evals/*.json ===`)
console.log(
  `  inline: ${detailInline} (${((detailInline / evalDetailFiles.length) * 100).toFixed(1)}%)`
)
console.log(
  `  missing: ${detailMissing} (${((detailMissing / evalDetailFiles.length) * 100).toFixed(1)}%)`
)

// ---------------------------------------------------------------------------
// 2. Build map and run both retry orders
// ---------------------------------------------------------------------------

const { map, collisions } = buildMap(benchmarkMetadata)

console.log(`\n=== Map build ===`)
console.log(`  total keys indexed: ${map.size}`)
console.log(`  first-write-wins collisions: ${collisions.length}`)
if (collisions.length) {
  console.log(`  collision examples (kept ← dropped):`)
  for (const c of collisions.slice(0, 10)) {
    console.log(`    [${c.key}] ${JSON.stringify(c.kept)} ← ${JSON.stringify(c.dropped)}`)
  }
}

// ---------------------------------------------------------------------------
// 3. Resolution position distribution under each retry order
// ---------------------------------------------------------------------------

function resolutionPosition(map, candidates) {
  const filtered = candidates.filter(Boolean)
  for (let i = 0; i < filtered.length; i++) {
    if (getBenchmarkCard(map, filtered[i])) return i
  }
  return -1
}

const summaryPositions = new Map() // pos → count
const listPositions = new Map()
const summaryMisses = []
const listMisses = []
const tailHitsSummary = [] // resolved only via candidate 1 or 2 (i.e. retry-load-bearing)
const tailHitsList = []
const matchedCardIdsSummary = new Set()

for (const e of evals) {
  if (e.benchmark_card) continue // already inline; lookup never runs
  const composite = deriveCompositeFields(e)

  const summaryCands = [composite.evaluation_name, composite.composite_benchmark_name, composite.composite_benchmark_key]
  const listCands = [composite.evaluation_name, composite.composite_benchmark_key, composite.composite_benchmark_name]

  const sPos = resolutionPosition(map, summaryCands)
  const lPos = resolutionPosition(map, listCands)

  if (sPos === -1) summaryMisses.push({ id: e.eval_summary_id, candidates: summaryCands })
  else summaryPositions.set(sPos, (summaryPositions.get(sPos) ?? 0) + 1)

  if (lPos === -1) listMisses.push({ id: e.eval_summary_id, candidates: listCands })
  else listPositions.set(lPos, (listPositions.get(lPos) ?? 0) + 1)

  if (sPos > 0)
    tailHitsSummary.push({ id: e.eval_summary_id, position: sPos, candidates: summaryCands })
  if (lPos > 0) tailHitsList.push({ id: e.eval_summary_id, position: lPos, candidates: listCands })

  if (sPos !== -1) {
    const filtered = summaryCands.filter(Boolean)
    const hit = getBenchmarkCard(map, filtered[sPos])
    if (hit?.benchmark_details?.name) matchedCardIdsSummary.add(hit.benchmark_details.name)
  }
}

const totalLookupCount = evals.length - inline
function pct(n) {
  return totalLookupCount === 0 ? "0.0" : ((n / totalLookupCount) * 100).toFixed(1)
}

console.log(`\n=== Summary path retry positions (order: name, name, key) — ${totalLookupCount} evals ===`)
for (const [pos, n] of [...summaryPositions.entries()].sort((a, b) => a[0] - b[0])) {
  console.log(`  position ${pos}: ${n} hits (${pct(n)}%)`)
}
console.log(`  misses: ${summaryMisses.length} (${pct(summaryMisses.length)}%)`)

console.log(`\n=== List path retry positions (order: name, key, name) — ${totalLookupCount} evals ===`)
for (const [pos, n] of [...listPositions.entries()].sort((a, b) => a[0] - b[0])) {
  console.log(`  position ${pos}: ${n} hits (${pct(n)}%)`)
}
console.log(`  misses: ${listMisses.length} (${pct(listMisses.length)}%)`)

// ---------------------------------------------------------------------------
// 4. Cards reachable only via 2nd or 3rd candidate (load-bearing retry tail)
// ---------------------------------------------------------------------------

console.log(`\n=== Tail-only hits (summary path, position > 0) ===`)
console.log(`  count: ${tailHitsSummary.length}`)
for (const t of tailHitsSummary.slice(0, 10)) {
  console.log(`  [pos ${t.position}] ${t.id}`)
  console.log(`    candidates: ${JSON.stringify(t.candidates)}`)
}

console.log(`\n=== Tail-only hits (list path, position > 0) ===`)
console.log(`  count: ${tailHitsList.length}`)
for (const t of tailHitsList.slice(0, 10)) {
  console.log(`  [pos ${t.position}] ${t.id}`)
  console.log(`    candidates: ${JSON.stringify(t.candidates)}`)
}

// ---------------------------------------------------------------------------
// 5. Disagreement between summary and list paths
// ---------------------------------------------------------------------------

const disagreements = []
for (const e of evals) {
  if (e.benchmark_card) continue
  const composite = deriveCompositeFields(e)
  const summaryCands = [composite.evaluation_name, composite.composite_benchmark_name, composite.composite_benchmark_key].filter(Boolean)
  const listCands = [composite.evaluation_name, composite.composite_benchmark_key, composite.composite_benchmark_name].filter(Boolean)
  let summaryHit = null
  for (const c of summaryCands) {
    const h = getBenchmarkCard(map, c)
    if (h) { summaryHit = h; break }
  }
  let listHit = null
  for (const c of listCands) {
    const h = getBenchmarkCard(map, c)
    if (h) { listHit = h; break }
  }
  if (summaryHit !== listHit) {
    disagreements.push({
      id: e.eval_summary_id,
      summary: summaryHit?.benchmark_details?.name ?? null,
      list: listHit?.benchmark_details?.name ?? null,
    })
  }
}
console.log(`\n=== Summary-vs-list path disagreements (different card depending on entry point) ===`)
console.log(`  count: ${disagreements.length}`)
for (const d of disagreements.slice(0, 10)) {
  console.log(`  ${d.id}: summary→${JSON.stringify(d.summary)} list→${JSON.stringify(d.list)}`)
}

// ---------------------------------------------------------------------------
// 6. Orphaned benchmark cards (no eval reaches them)
// ---------------------------------------------------------------------------

const reachedCardNames = new Set()
for (const e of evals) {
  // Use the inline card if present (because that bypasses the lookup loop)
  if (e.benchmark_card?.benchmark_details?.name) {
    reachedCardNames.add(e.benchmark_card.benchmark_details.name)
    continue
  }
  const composite = deriveCompositeFields(e)
  const allCands = [
    composite.evaluation_name,
    composite.composite_benchmark_name,
    composite.composite_benchmark_key,
  ].filter(Boolean)
  for (const c of allCands) {
    const h = getBenchmarkCard(map, c)
    if (h?.benchmark_details?.name) {
      reachedCardNames.add(h.benchmark_details.name)
      break
    }
  }
}

const allCardNames = new Set(
  Object.values(benchmarkMetadata)
    .map((c) => c?.benchmark_details?.name)
    .filter(Boolean)
)
const orphaned = [...allCardNames].filter((n) => !reachedCardNames.has(n))

console.log(`\n=== Benchmark cards with no inbound eval match (orphans) ===`)
console.log(`  total cards: ${allCardNames.size}`)
console.log(`  reached by at least one eval: ${reachedCardNames.size}`)
console.log(`  orphaned: ${orphaned.length}`)
for (const n of orphaned.slice(0, 20)) {
  console.log(`  - ${JSON.stringify(n)}`)
}
