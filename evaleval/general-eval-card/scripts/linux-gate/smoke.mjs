// Linux/amd64 DuckDB read-path smoke — runs the REAL read paths the app uses on
// the prod-pinned @duckdb/node-api binding, inside a linux/amd64 container, and
// asserts the binding can marshal them via readAll()+getRowObjectsJson().
//
// This is the net for the class of failure that passes on Mac and broke prod:
// the "Invalid Error: don't know what type:" struct/timestamp marshalling crash
// on the linux-x64 binding. It mirrors prod's getConnection() exactly: in-memory
// tables loaded over httpfs (NO /data mmap — a local-file mmap on HF's /data
// mount could read back incoherent pages and throw the same error).
//
// SNAPSHOT_URL is passed in by scripts/linux-gate.sh.
import { DuckDBConnection } from "@duckdb/node-api"

const SNAP = (process.env.SNAPSHOT_URL || "").replace(/\/+$/, "")
if (!SNAP) { console.error("linux-gate smoke: SNAPSHOT_URL required"); process.exit(2) }

const VIEWS = {
  models_view: "models_view.parquet",
  evals_view: "evals_view.parquet",
  eval_results_view: "eval_results_view.parquet",
}

const c = await DuckDBConnection.create()
// Prod read path: materialise each view into an in-memory table over httpfs.
for (const [v, f] of Object.entries(VIEWS)) {
  await c.run(`CREATE OR REPLACE TABLE ${v} AS SELECT * FROM read_parquet('${SNAP}/${f}')`)
}

async function probe(label, sql) {
  const t = Date.now()
  const r = await c.runAndRead(sql)
  await r.readAll()                 // the chunk-fetch that throws on a bad type
  const rows = r.getRowObjectsJson() // the JS marshalling the linux binding crashed on
  if (!rows.length) throw new Error(`${label} returned 0 rows (expected data)`)
  console.log(`  ok  ${label}: ${rows.length} rows (${Date.now() - t}ms)`)
}

try {
  // getModelSummaryById's actual read path: raw SELECT * on models_view (which
  // carries STRUCT/JSON/TIMESTAMP columns) — a real prod read that marshals today.
  await probe("models_view SELECT* (getModelSummaryById)", `SELECT * FROM models_view LIMIT 5`)

  // The scalar leaderboard query we will serve (RANK window over eval_results_view).
  await probe("leaderboard scalar query", `
    SELECT evaluation_id, metric_summary_id, model_route_id, score,
      RANK()   OVER (PARTITION BY evaluation_id, metric_summary_id
                     ORDER BY (CASE WHEN lower_is_better THEN score ELSE -score END) ASC) AS rank,
      COUNT(*) OVER (PARTITION BY evaluation_id, metric_summary_id) AS total
    FROM eval_results_view
    WHERE score IS NOT NULL AND evaluation_id IS NOT NULL
      AND metric_summary_id IS NOT NULL AND model_route_id IS NOT NULL
    LIMIT 200`)

  console.log("LINUX-GATE SMOKE: PASS — prod binding marshalled the real read paths")
  process.exit(0)
} catch (e) {
  console.error(`LINUX-GATE SMOKE: FAIL — ${e?.name}: ${e?.message}`)
  process.exit(1)
}
