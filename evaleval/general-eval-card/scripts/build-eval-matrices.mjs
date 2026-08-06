#!/usr/bin/env node
// Precompute per-evaluation multi-metric and per-slice score matrices and
// emit them as one JSON map at data/eval-matrices.json.
//
// The runtime eval-summary endpoint currently only returns one
// (metric, model) row per model — sourced from the primary metric of
// `eval_results_view`. The other declared `leaderboard_metrics` (and
// per-slice subtask scores hiding inside `fact_results`) are dropped on
// the floor, which is why the eval page can't render a multi-metric
// leaderboard or a slice dropdown.
//
// Both views are reconstructable from the warehouse parquet files; this
// script does the join once at build time so the runtime path is a flat
// O(1) lookup against the precomputed map.
//
// Output schema:
//   {
//     snapshot_id,                     // pinned for cache busting
//     generated_at,
//     evals: {
//       "<evaluation_id>": {
//         // Per-(model, metric) values across the eval's full
//         // leaderboard_metrics list. Drives the multi-metric matrix.
//         leaderboard_rows: [
//           { model_route_id, values: { "<column_key>": score | null } }
//         ],
//         // Subtask-scope metric entries to *append* to the eval's
//         // leaderboard_metrics. Each carries column_key
//         // "<metric_id>::<slice_key>" so it slots into values{} above.
//         subtask_metrics: [BenchmarkLeaderboardMetric]
//       }
//     }
//   }
//
// Run via the build chain (`pnpm build`) or standalone:
//   node scripts/build-eval-matrices.mjs

import { DuckDBInstance } from "@duckdb/node-api"
import fs from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

// DuckDB-node returns its list / struct / map values as opaque wrapper
// classes whose payload lives behind `.items` / `.entries`. Walk through
// these so downstream code can treat the result as plain JSON.
function normalizeDuck(value) {
  if (value == null) return value
  if (typeof value === "bigint") return Number(value)
  if (Array.isArray(value)) return value.map(normalizeDuck)
  if (typeof value === "object") {
    const ctor = value.constructor?.name ?? ""
    if (ctor === "DuckDBListValue" || ctor === "DuckDBArrayValue") {
      return (value.items ?? []).map(normalizeDuck)
    }
    if (ctor === "DuckDBStructValue") {
      return normalizeDuck(value.entries)
    }
    if (ctor === "DuckDBMapValue" && Array.isArray(value.entries)) {
      const out = {}
      for (const e of value.entries) out[String(e.key)] = normalizeDuck(e.value)
      return out
    }
    if (ctor === "DuckDBDecimalValue" && typeof value.toString === "function") {
      return Number(value.toString())
    }
    if (ctor.startsWith("DuckDB") && typeof value.toString === "function") {
      return value.toString()
    }
    const out = {}
    for (const [k, v] of Object.entries(value)) out[k] = normalizeDuck(v)
    return out
  }
  return value
}

function readDuckRows(reader) {
  return reader.getRowObjects().map(normalizeDuck).map((row) => normalizeDuck(row))
}

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const WAREHOUSE = path.join(ROOT, ".cache/hf-data/warehouse/latest")
const OUT_PATH = path.join(ROOT, "data/eval-matrices.json")

async function main() {
  // Sanity check: the warehouse parquet files must exist locally.
  // `pnpm cache-hf-data` (legacy) or a manual download populates them; the
  // v2 build-time path streams them via duckdb's HTTPS reader, so when we
  // can't find them locally we point duckdb at SNAPSHOT_URL instead.
  const snapshotUrl = process.env.SNAPSHOT_URL?.replace(/\/+$/, "")
  let base = WAREHOUSE
  let useRemote = false
  try {
    await fs.access(path.join(WAREHOUSE, "eval_results_view.parquet"))
  } catch {
    if (!snapshotUrl) {
      console.error(
        "[build-eval-matrices] no local warehouse cache and no SNAPSHOT_URL — abort.",
      )
      process.exit(1)
    }
    base = snapshotUrl
    useRemote = true
  }

  const t0 = Date.now()
  const db = await DuckDBInstance.create()
  const con = await db.connect()

  const fileRef = (name) => {
    const url = useRemote ? `${base}/${name}` : path.join(base, name)
    return `'${url.replace(/'/g, "''")}'`
  }

  // Reading snapshot_id from snapshot_meta.json so the output can be
  // matched against the pinned build snapshot.
  let snapshotId = "unknown"
  try {
    const metaText = useRemote
      ? await (await fetch(`${base}/snapshot_meta.json`)).text()
      : await fs.readFile(path.join(WAREHOUSE, "snapshot_meta.json"), "utf8")
    snapshotId = JSON.parse(metaText).snapshot_id ?? "unknown"
  } catch (err) {
    console.warn(
      `[build-eval-matrices] couldn't resolve snapshot_id: ${err instanceof Error ? err.message : String(err)}`,
    )
  }

  // 1. All (eval, model, metric, score) rows. Includes non-primary
  //    metrics that getEvalSummaryById currently filters out.
  const metricRows = await con.runAndReadAll(`
    SELECT
      r.evaluation_id,
      r.metric_id,
      r.model_route_id,
      r.score,
      r.is_verified_evaluator
    FROM read_parquet(${fileRef("eval_results_view.parquet")}) r
    WHERE r.score IS NOT NULL
      AND r.model_route_id IS NOT NULL
  `)

  // 2. Per-slice (composite_slug, benchmark, model, metric, slice_key,
  //    score) rows. The upstream pipeline parks slice scores in
  //    fact_results rather than threading them through eval_results_view,
  //    so we have to reach in here. We carry composite_slug because some
  //    benchmarks (e.g. `gpqa`) appear under multiple composites and
  //    fact_results emits a per-source pseudo-slice (slice_key =
  //    "artificial analysis", "llm stats", "openeval gpqa", ...) for
  //    each source family. Joining slices on (composite_slug,
  //    benchmark_id) keeps each composite's slices in its own lane,
  //    so HF Open LLM v2's GPQA doesn't inherit Artificial Analysis's
  //    pseudo-slice, etc. Also drop the self-rollup (slice_key ==
  //    benchmark_id) since that duplicates the eval's overall score.
  //    AVG collapses the rare duplicate (model, slice) pairs.
  const sliceRows = await con.runAndReadAll(`
    SELECT
      f.composite_slug,
      f.benchmark_id,
      f.parent_benchmark_id,
      f.metric_id,
      f.slice_key,
      f.slice_name,
      f.model_id,
      AVG(f.score) AS score,
      bool_or(f.is_verified_evaluator) AS is_verified_evaluator
    FROM read_parquet(${fileRef("fact_results.parquet")}) f
    WHERE f.score IS NOT NULL
      AND f.slice_key IS NOT NULL
      AND f.metric_id IS NOT NULL
      AND f.composite_slug IS NOT NULL
      -- Drop any slice that's a self-rollup of the eval — slice_key
      -- equals the benchmark, the composite, or the parent benchmark
      -- after normalising separators (so "global mmlu lite" filters
      -- against benchmark_id "global-mmlu-lite", "fibble_arena"
      -- against "fibble-arena", "artificial analysis" against
      -- composite "artificial-analysis-llms", etc.).
      AND regexp_replace(lower(f.slice_key), '[^a-z0-9]+', '', 'g')
          != regexp_replace(lower(f.benchmark_id), '[^a-z0-9]+', '', 'g')
      AND regexp_replace(lower(f.slice_key), '[^a-z0-9]+', '', 'g')
          != regexp_replace(lower(f.composite_slug), '[^a-z0-9]+', '', 'g')
      -- Also drop slices whose slug is a strict prefix of the
      -- composite_slug (e.g. "artificial analysis" vs
      -- composite "artificial-analysis-llms" — the slice is just
      -- the source family naming itself, not a real subtask).
      AND NOT regexp_replace(lower(f.composite_slug), '[^a-z0-9]+', '', 'g')
          LIKE regexp_replace(lower(f.slice_key), '[^a-z0-9]+', '', 'g') || '%'
      AND (
        f.parent_benchmark_id IS NULL
        OR regexp_replace(lower(f.slice_key), '[^a-z0-9]+', '', 'g')
           != regexp_replace(lower(f.parent_benchmark_id), '[^a-z0-9]+', '', 'g')
      )
    GROUP BY 1,2,3,4,5,6,7
  `)

  // 3. eval → (composite_slug, benchmark_id) mapping so we can join
  //    slice rows back to the right evaluation_id. composite_slug is
  //    what disambiguates HF Open LLM v2's GPQA from Artificial
  //    Analysis's GPQA — both share benchmark_id `gpqa`. Also pull
  //    leaderboard_metrics so we know each metric's metric_summary_id /
  //    unit / lower_is_better when synthesising subtask-scope entries.
  const evalRows = await con.runAndReadAll(`
    SELECT
      evaluation_id,
      benchmark_id,
      parent_benchmark_id,
      composite_slug,
      leaderboard_metrics
    FROM read_parquet(${fileRef("evals_view.parquet")})
  `)

  // 4. Map model_id → model_route_id so per-slice rows (which carry
  //    model_id) can land alongside per-metric rows (model_route_id).
  const modelKeyRows = await con.runAndReadAll(`
    SELECT DISTINCT model_id, model_route_id
    FROM read_parquet(${fileRef("eval_results_view.parquet")})
    WHERE model_route_id IS NOT NULL
  `)

  await con.disconnectSync()

  // Index the model_id → route_id map so slice lookups are O(1).
  const modelIdToRoute = new Map()
  for (const row of modelKeyRows.getRowObjects().map(normalizeDuck)) {
    if (!modelIdToRoute.has(row.model_id)) {
      modelIdToRoute.set(row.model_id, row.model_route_id)
    }
  }

  // Group eval rows by evaluation_id, indexed by (composite_slug,
  // benchmark_id) for the slice join. Two evals can share a benchmark_id
  // across composites (gpqa under both hfopenllm-v2 and
  // artificial-analysis-llms), so the composite_slug component is what
  // keeps them separated.
  const evalsByCompositeBench = new Map()
  const evalsById = new Map()
  const compositeBenchKey = (composite, bench) =>
    `${composite ?? ""}|${bench ?? ""}`
  for (const row of evalRows.getRowObjects().map(normalizeDuck)) {
    evalsById.set(row.evaluation_id, row)
    const bid = row.benchmark_id ?? null
    const composite = row.composite_slug ?? null
    if (bid && composite) {
      const key = compositeBenchKey(composite, bid)
      if (!evalsByCompositeBench.has(key)) evalsByCompositeBench.set(key, [])
      evalsByCompositeBench.get(key).push(row.evaluation_id)
    }
  }

  // Bucket metric rows by evaluation_id and within that by model.
  // out[evalId].rows[modelRoute].values = { column_key: score }
  const out = {}
  const ensureEval = (evalId) => {
    if (!out[evalId]) {
      out[evalId] = {
        leaderboard_rows: new Map(), // route_id → values
        subtask_metric_keys: new Set(), // tracks which subtask cols we've seen
        subtask_metrics: [],
      }
    }
    return out[evalId]
  }

  // modelEntry holds parallel maps: `values` (column_key → score) and
  // `verified` (column_key → bool), so the per-cell verified-evaluator flag
  // rides alongside each non-primary metric / slice column.
  const ensureModelEntry = (bucket, route) => {
    let modelEntry = bucket.leaderboard_rows.get(route)
    if (!modelEntry) {
      modelEntry = { values: {}, verified: {} }
      bucket.leaderboard_rows.set(route, modelEntry)
    }
    return modelEntry
  }

  for (const row of metricRows.getRowObjects().map(normalizeDuck)) {
    const bucket = ensureEval(row.evaluation_id)
    const modelEntry = ensureModelEntry(bucket, row.model_route_id)
    modelEntry.values[row.metric_id] = Number(row.score)
    if (row.is_verified_evaluator != null) {
      modelEntry.verified[row.metric_id] = Boolean(row.is_verified_evaluator)
    }
  }

  // Plant slice scores. Each (metric_id, slice_key) becomes a column
  // keyed "<metric_id>::<slice_key>" so it slots into values{} alongside
  // root metrics. The matching subtask leaderboard metric metadata is
  // emitted in subtask_metrics for the runtime to splice into the eval's
  // leaderboard_metrics array.
  for (const row of sliceRows.getRowObjects().map(normalizeDuck)) {
    const evalIds = evalsByCompositeBench.get(
      compositeBenchKey(row.composite_slug, row.benchmark_id),
    )
    if (!evalIds) continue
    const route = modelIdToRoute.get(row.model_id)
    if (!route) continue
    const sliceKey = String(row.slice_key)
    const sliceName = row.slice_name ? String(row.slice_name) : sliceKey
    const metricId = String(row.metric_id)
    const columnKey = `${metricId}::${sliceKey}`
    const score = Number(row.score)
    if (!Number.isFinite(score)) continue

    for (const evalId of evalIds) {
      const bucket = ensureEval(evalId)
      const modelEntry = ensureModelEntry(bucket, route)
      modelEntry.values[columnKey] = score
      if (row.is_verified_evaluator != null) {
        modelEntry.verified[columnKey] = Boolean(row.is_verified_evaluator)
      }

      if (!bucket.subtask_metric_keys.has(columnKey)) {
        bucket.subtask_metric_keys.add(columnKey)
        // Look up the parent eval's metric metadata so the subtask-scope
        // entry inherits unit / lower_is_better. Fall back to defaults
        // when the registry doesn't carry the metric.
        const evalMeta = evalsById.get(evalId)
        const rootMetric = (evalMeta?.leaderboard_metrics ?? []).find(
          (m) => m.metric_id === metricId,
        )
        bucket.subtask_metrics.push({
          column_key: columnKey,
          metric_summary_id: rootMetric?.metric_summary_id ?? `${evalId}%3A${metricId}`,
          metric_id: metricId,
          metric_name: rootMetric?.metric_name ?? metricId,
          display_name: rootMetric?.display_name ?? metricId,
          canonical_display_name: rootMetric?.canonical_display_name ?? null,
          lower_is_better: rootMetric?.lower_is_better ?? false,
          unit: rootMetric?.unit ?? null,
          scope: "subtask",
          subtask_key: sliceKey,
          subtask_name: sliceName,
        })
      }
    }
  }

  // Materialise: convert internal Maps to JSON-friendly arrays. Drop
  // evals that ended up with a single root metric and no subtasks since
  // the runtime can already render those through the existing path.
  const finalEvals = {}
  for (const [evalId, bucket] of Object.entries(out)) {
    const rows = []
    for (const [routeId, entry] of bucket.leaderboard_rows) {
      rows.push({ model_route_id: routeId, values: entry.values, verified: entry.verified })
    }
    // Skip evals where every model has at most one metric and no
    // subtask data — adds no information beyond the existing summary.
    const hasMultiMetric = rows.some((r) => Object.keys(r.values).length > 1)
    if (!hasMultiMetric && bucket.subtask_metrics.length === 0) continue
    finalEvals[evalId] = {
      leaderboard_rows: rows,
      subtask_metrics: bucket.subtask_metrics,
    }
  }

  const payload = {
    snapshot_id: snapshotId,
    generated_at: new Date().toISOString(),
    evals: finalEvals,
  }

  await fs.mkdir(path.dirname(OUT_PATH), { recursive: true })
  await fs.writeFile(OUT_PATH, JSON.stringify(payload))

  const sizeMb = (
    Buffer.byteLength(JSON.stringify(payload), "utf8") / 1024 / 1024
  ).toFixed(2)
  console.log(
    `[build-eval-matrices] wrote ${Object.keys(finalEvals).length} evals to ${path.relative(ROOT, OUT_PATH)} (${sizeMb} MB) in ${Date.now() - t0}ms`,
  )
}

main().catch((err) => {
  console.error("[build-eval-matrices] failed:", err)
  process.exit(1)
})
