#!/usr/bin/env node
// Tier C — full-cache differential audit.
//
// Runs every major adapter against either pinned fixtures or the live HF
// cache, produces a deterministic JSON digest (per-adapter outputs_count,
// outputs_hash, field distributions, invariant violation counts), and
// supports a diff mode to compare two digests side-by-side.
//
// Usage:
//   node scripts/audit-adapters.mjs --output baseline.json   # capture digest
//   node scripts/audit-adapters.mjs --output candidate.json  # after a change
//   node scripts/audit-adapters.mjs --diff baseline.json candidate.json
//   node scripts/audit-adapters.mjs --against tests/fixtures # use pinned set
//   node scripts/audit-adapters.mjs --against .cache/hf-data --output live.json
//
// Default --against is .cache/hf-data (the full production cache snapshot).
// `--against tests/fixtures` falls back to manifest-listed IDs only.
//
// The script imports the same adapter functions the runtime uses, so output
// changes when either adapter logic changes OR input data changes. Use diff
// mode to separate the two: re-run with the same --against before and after a
// code change, diff the digests.

import "./server-only-shim.mjs"

import { promises as fs } from "fs"
import { createHash } from "crypto"
import path from "path"

const ROOT = path.resolve(import.meta.dirname, "..")

const args = parseArgs(process.argv.slice(2))

if (args.diff) {
  const [baselinePath, candidatePath] = args.diff
  await runDiff(baselinePath, candidatePath)
  process.exit(0)
}

const sourceDir = path.resolve(ROOT, args.against ?? ".cache/hf-data")
await ensureDir(sourceDir)

console.log(`[audit] reading from ${sourceDir}`)

// Lazy-load adapters AFTER tsx is registered.
const { flattenModelEvaluations } = await import("../lib/hf-data.ts")
const {
  hfModelCardToEvaluationCardData,
  hfEvalDetailToSummary,
  hfDeveloperDetailToSummary,
} = await import("../lib/model-data.ts")

const { evals, models, developers, modelCards } = await loadInputs(sourceDir, args.against === "tests/fixtures")

console.log(`[audit] inputs: ${evals.length} evals, ${models.length} models, ${developers.length} developers, ${modelCards.length} model cards`)

const digest = {
  version: 1,
  source: args.against ?? ".cache/hf-data",
  generated_at: new Date().toISOString(),
  inputs: {
    evals: evals.length,
    models: models.length,
    developers: developers.length,
    model_cards: modelCards.length,
  },
  adapters: {
    hfModelCardToEvaluationCardData: auditAdapter(modelCards, (entry) => entry.model_route_id, hfModelCardToEvaluationCardData, {
      categorical: ["developer"],
      numeric: ["evaluations_count", "benchmarks_count", "variant_count", "evaluator_count"],
    }),
    hfEvalDetailToSummary: auditAdapter(evals, (entry) => entry.eval_summary_id, hfEvalDetailToSummary, {
      categorical: ["category"],
      numeric: ["models_count", "metrics_count", "subtasks_count"],
    }),
    flattenModelEvaluations: auditAdapter(models, (entry) => entry.model_route_id, (input) => {
      // Hash the FULL evaluations (so a score/timestamp/metric_name change
      // is detected), but project to a small set of fields for distribution
      // tracking (so the per-field histograms stay readable).
      return flattenModelEvaluations(input)
    }, {
      categorical: ["category"],
      numeric: [],
      arrayOutput: true,
      // Pull these from a nested field for distribution tracking only — they
      // don't affect hashing because the full output is hashed via the items
      // themselves.
      categoricalGetters: {
        evaluator_relationship: (e) => e.source_metadata?.evaluator_relationship,
        benchmark_family_key: (e) => e.benchmark_family_key,
      },
    }),
    hfDeveloperDetailToSummary: auditAdapter(developers, (entry) => entry.developer, hfDeveloperDetailToSummary, {
      categorical: ["developer"],
      numeric: ["model_count", "benchmark_count", "evaluation_count"],
    }),
  },
}

if (args.output) {
  await fs.writeFile(args.output, `${JSON.stringify(digest, null, 2)}\n`)
  console.log(`[audit] wrote ${args.output}`)
} else {
  console.log(JSON.stringify(digest, null, 2))
}

// -----------------------------------------------------------------------------

function auditAdapter(inputs, getId, adapter, opts) {
  const fieldValues = {}
  for (const field of opts.categorical) fieldValues[field] = new Map()
  for (const field of opts.numeric) fieldValues[field] = []
  const getters = opts.categoricalGetters ?? {}
  for (const field of Object.keys(getters)) fieldValues[field] = new Map()

  let outputsHash = createHash("sha256")
  let throws = 0
  const throwsExamples = []
  let outputsCount = 0

  for (const input of inputs) {
    const id = getId(input) ?? "<no-id>"
    let output
    try {
      output = adapter(input)
    } catch (err) {
      throws += 1
      if (throwsExamples.length < 5) {
        throwsExamples.push({ id, error: err instanceof Error ? err.message : String(err) })
      }
      continue
    }

    const items = opts.arrayOutput ? output : [output]
    outputsCount += opts.arrayOutput ? items.length : 1

    for (const item of items) {
      // Hash the full item for change-detection — every leaf value contributes.
      outputsHash.update(JSON.stringify(stableSort(item)))

      for (const field of opts.categorical) {
        const v = String(item?.[field] ?? "<missing>")
        const counts = fieldValues[field]
        counts.set(v, (counts.get(v) ?? 0) + 1)
      }
      for (const field of opts.numeric) {
        const v = item?.[field]
        if (typeof v === "number" && Number.isFinite(v)) fieldValues[field].push(v)
      }
      for (const [field, getter] of Object.entries(getters)) {
        const v = String(getter(item) ?? "<missing>")
        fieldValues[field].set(v, (fieldValues[field].get(v) ?? 0) + 1)
      }
    }
  }

  const distributions = {}
  for (const field of [...opts.categorical, ...Object.keys(getters)]) {
    distributions[field] = Object.fromEntries(
      [...fieldValues[field].entries()].sort(([a], [b]) => a.localeCompare(b))
    )
  }
  for (const field of opts.numeric) {
    const arr = fieldValues[field]
    if (arr.length === 0) {
      distributions[field] = { count: 0 }
      continue
    }
    const sorted = [...arr].sort((a, b) => a - b)
    distributions[field] = {
      count: arr.length,
      sum: sorted.reduce((a, b) => a + b, 0),
      min: sorted[0],
      max: sorted[sorted.length - 1],
      median: sorted[Math.floor(sorted.length / 2)],
    }
  }

  return {
    inputs_count: inputs.length,
    outputs_count: outputsCount,
    outputs_hash: `sha256:${outputsHash.digest("hex").slice(0, 16)}`,
    throws,
    throws_examples: throwsExamples,
    field_distributions: distributions,
  }
}

function stableSort(value) {
  if (Array.isArray(value)) return value.map(stableSort)
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([k, v]) => [k, stableSort(v)])
    )
  }
  return value
}

async function loadInputs(sourceDir, isPinnedFixtures) {
  if (isPinnedFixtures) {
    return loadFromFixtures(sourceDir)
  }
  return loadFromCache(sourceDir)
}

async function loadFromFixtures(sourceDir) {
  const manifest = JSON.parse(await fs.readFile(path.join(sourceDir, "manifest.json"), "utf8"))
  const groups = { evals: [], models: [], developers: [], modelCards: [] }
  for (const entry of manifest.evals ?? []) {
    groups.evals.push(JSON.parse(await fs.readFile(path.join(sourceDir, "evals", `${entry.id}.json`), "utf8")))
  }
  for (const entry of manifest.models ?? []) {
    groups.models.push(JSON.parse(await fs.readFile(path.join(sourceDir, "models", `${entry.id}.json`), "utf8")))
  }
  for (const entry of manifest.developers ?? []) {
    groups.developers.push(JSON.parse(await fs.readFile(path.join(sourceDir, "developers", `${entry.id}.json`), "utf8")))
  }
  for (const entry of manifest.model_cards ?? []) {
    groups.modelCards.push(JSON.parse(await fs.readFile(path.join(sourceDir, "model-cards", `${entry.id}.json`), "utf8")))
  }
  return groups
}

async function loadFromCache(sourceDir) {
  const evalFiles = await fs.readdir(path.join(sourceDir, "evals")).catch(() => [])
  const modelFiles = await fs.readdir(path.join(sourceDir, "models")).catch(() => [])
  const developerFiles = await fs.readdir(path.join(sourceDir, "developers")).catch(() => [])
  const modelCardsRaw = await fs.readFile(path.join(sourceDir, "model-cards.json"), "utf8").catch(() => "[]")

  const groups = { evals: [], models: [], developers: [], modelCards: [] }
  for (const file of evalFiles) {
    if (!file.endsWith(".json")) continue
    groups.evals.push(JSON.parse(await fs.readFile(path.join(sourceDir, "evals", file), "utf8")))
  }
  for (const file of modelFiles) {
    if (!file.endsWith(".json")) continue
    groups.models.push(JSON.parse(await fs.readFile(path.join(sourceDir, "models", file), "utf8")))
  }
  for (const file of developerFiles) {
    if (!file.endsWith(".json")) continue
    groups.developers.push(JSON.parse(await fs.readFile(path.join(sourceDir, "developers", file), "utf8")))
  }
  groups.modelCards = JSON.parse(modelCardsRaw)
  return groups
}

async function runDiff(baselinePath, candidatePath) {
  const baseline = JSON.parse(await fs.readFile(baselinePath, "utf8"))
  const candidate = JSON.parse(await fs.readFile(candidatePath, "utf8"))

  console.log(`baseline:  ${baseline.source} @ ${baseline.generated_at}`)
  console.log(`candidate: ${candidate.source} @ ${candidate.generated_at}`)
  console.log()

  const adapterNames = new Set([...Object.keys(baseline.adapters ?? {}), ...Object.keys(candidate.adapters ?? {})])
  for (const name of [...adapterNames].sort()) {
    const b = baseline.adapters?.[name]
    const c = candidate.adapters?.[name]
    if (!b || !c) {
      console.log(`${name}: ${b ? "removed" : "added"}`)
      continue
    }

    const lines = []
    if (b.outputs_hash !== c.outputs_hash) lines.push(`  hash:        ${b.outputs_hash} → ${c.outputs_hash}`)
    if (b.outputs_count !== c.outputs_count) lines.push(`  outputs:     ${b.outputs_count} → ${c.outputs_count}`)
    if (b.throws !== c.throws) lines.push(`  throws:      ${b.throws} → ${c.throws}`)
    if (c.throws > b.throws && c.throws_examples?.length > 0) {
      lines.push(`  new errors:  ${c.throws_examples.slice(0, 3).map((e) => `${e.id}: ${e.error}`).join("; ")}`)
    }

    for (const field of new Set([...Object.keys(b.field_distributions ?? {}), ...Object.keys(c.field_distributions ?? {})])) {
      const distA = b.field_distributions?.[field] ?? {}
      const distB = c.field_distributions?.[field] ?? {}
      const aText = JSON.stringify(distA)
      const bText = JSON.stringify(distB)
      if (aText === bText) continue
      lines.push(`  ${field}:`)
      // Categorical: highlight added/removed/changed keys
      if (distA && typeof distA === "object" && !("count" in distA)) {
        const keys = new Set([...Object.keys(distA), ...Object.keys(distB)])
        for (const k of [...keys].sort()) {
          const va = distA[k]
          const vb = distB[k]
          if (va !== vb) lines.push(`    ${k}: ${va ?? "—"} → ${vb ?? "—"}`)
        }
      } else {
        // Numeric: show min/median/max
        for (const stat of ["count", "min", "median", "max", "sum"]) {
          if (distA[stat] !== distB[stat]) {
            lines.push(`    ${stat}: ${distA[stat]} → ${distB[stat]}`)
          }
        }
      }
    }

    if (lines.length === 0) {
      console.log(`${name}: no change`)
    } else {
      console.log(`${name}:`)
      for (const line of lines) console.log(line)
    }
    console.log()
  }
}

async function ensureDir(dir) {
  await fs.access(dir).catch(() => {
    throw new Error(`Source directory ${dir} not found.`)
  })
}

function parseArgs(argv) {
  const out = {}
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === "--output") out.output = argv[++i]
    else if (a === "--against") out.against = argv[++i]
    else if (a === "--diff") {
      out.diff = [argv[++i], argv[++i]]
    } else if (a === "--live") out.against = ".cache/hf-data"
    else if (a === "--help" || a === "-h") {
      console.log(`Usage: node scripts/audit-adapters.mjs [options]
  --output FILE         write digest as JSON
  --against PATH        source dir (default: .cache/hf-data); pinned: tests/fixtures
  --live                shorthand for --against .cache/hf-data
  --diff A B            diff two previously-written digests`)
      process.exit(0)
    }
  }
  return out
}
