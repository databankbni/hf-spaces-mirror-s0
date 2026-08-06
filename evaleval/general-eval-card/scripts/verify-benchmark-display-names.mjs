import "./server-only-shim.mjs"
import fs from "fs"

// Audit `getBenchmarkDisplayName` from lib/model-data.ts:90-148 against the
// full live cache in .cache/hf-data/. Prints distribution stats: how many
// distinct keys hit BENCHMARK_NAMES, how many fall through to humanizeToken,
// examples of each, and which input field (benchmark / benchmark_parent_key /
// benchmark_family_key) drives each call.
//
// If .cache/hf-data/ is missing or empty, run `pnpm cache-hf-data` first.
//
// Spec: notes/transformations/08-benchmark-display-names.md
// Tests: tests/transformations/benchmark-display-names.test.ts

// ---------------------------------------------------------------------------
// Replicate lib/model-data.ts:90-148 verbatim
// ---------------------------------------------------------------------------

function humanizeToken(token) {
  return token
    .split(/[_-]+/g)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
}

const BENCHMARK_NAMES = {
  hfopenllm_v2: "HF Open LLM v2",
  helm_lite: "HELM Lite",
  helm_capabilities: "HELM Capabilities",
  helm_classic: "HELM Classic",
  helm_instruct: "HELM Instruct",
  helm_mmlu: "HELM MMLU",
  reward_bench: "RewardBench",
  reward_bench_2: "RewardBench 2",
  bfcl: "BFCL",
  global_mmlu_lite: "Global MMLU Lite",
  swe_bench: "SWE-bench",
  arc_agi: "ARC-AGI",
  tau_bench_2: "TAU-Bench 2",
  ace: "ACE",
  apex_agents: "APEX Agents",
  apex_v1: "APEX v1",
  appworld: "AppWorld",
  browsecompplus: "BrowseComp+",
  livecodebenchpro: "LiveCodeBench Pro",
  sciarena: "SciArena",
  terminal_bench_2_0: "Terminal Bench 2.0",
  la_leaderboard: "LA Leaderboard",
  theory_of_mind: "Theory of Mind",
  fibble_arena: "Fibble Arena",
  fibble1_arena: "Fibble Arena v1",
  fibble2_arena: "Fibble Arena v2",
  fibble3_arena: "Fibble Arena v3",
  fibble4_arena: "Fibble Arena v4",
  fibble5_arena: "Fibble Arena v5",
  wordle_arena: "Wordle Arena",
}

function normalizeBenchmarkKeyForLookup(key) {
  return key.toLowerCase().replace(/[-.\s]+/g, "_").replace(/^_+|_+$/g, "")
}

function getBenchmarkDisplayName(benchmark) {
  return BENCHMARK_NAMES[normalizeBenchmarkKeyForLookup(benchmark)] ?? humanizeToken(benchmark)
}

function classify(value) {
  if (value == null || value === "") return "empty"
  return BENCHMARK_NAMES[normalizeBenchmarkKeyForLookup(value)] ? "mapHit" : "fallback"
}

// ---------------------------------------------------------------------------
// Cache check
// ---------------------------------------------------------------------------

const cacheDir = ".cache/hf-data"
if (!fs.existsSync(cacheDir)) {
  console.error(`ERROR: ${cacheDir} not found. Run \`pnpm cache-hf-data\` first.`)
  process.exit(1)
}

const evalListPath = `${cacheDir}/eval-list.json`
const modelCardsLitePath = `${cacheDir}/model-cards-lite.json`

if (!fs.existsSync(evalListPath)) {
  console.error(`ERROR: ${evalListPath} not found. Run \`pnpm cache-hf-data\` first.`)
  process.exit(1)
}

// ---------------------------------------------------------------------------
// Pass 1 — eval-list.json (587 entries; the suite/benchmark key universe)
// ---------------------------------------------------------------------------

const evalListRaw = JSON.parse(fs.readFileSync(evalListPath, "utf8"))
const evals = Array.isArray(evalListRaw) ? evalListRaw : evalListRaw.evals
console.log(`=== Audit: getBenchmarkDisplayName across ${evals.length} eval-list.json entries ===\n`)

const fields = [
  "benchmark",
  "benchmark_parent_key",
  "benchmark_family_key",
  "benchmark_parent_name",
]

for (const field of fields) {
  const distinct = new Set()
  const buckets = { mapHit: 0, fallback: 0, empty: 0 }
  const distinctBuckets = { mapHit: new Set(), fallback: new Set(), empty: new Set() }
  const examples = { mapHit: [], fallback: [] }

  for (const e of evals) {
    const raw = e[field]
    if (raw != null && raw !== "") distinct.add(raw)
    const bucket = classify(raw)
    buckets[bucket]++
    if (raw != null && raw !== "") distinctBuckets[bucket].add(raw)
  }

  for (const value of distinct) {
    const bucket = classify(value)
    if (bucket === "mapHit" && examples.mapHit.length < 5) {
      examples.mapHit.push({ raw: value, displayed: getBenchmarkDisplayName(value) })
    } else if (bucket === "fallback" && examples.fallback.length < 10) {
      examples.fallback.push({ raw: value, displayed: getBenchmarkDisplayName(value) })
    }
  }

  console.log(`--- field: ${field} ---`)
  console.log(`  ${distinct.size} distinct values across ${evals.length} calls`)
  console.log(`  call buckets: ${JSON.stringify(buckets)}`)
  console.log(
    `  distinct buckets: mapHit=${distinctBuckets.mapHit.size} fallback=${distinctBuckets.fallback.size} empty=${distinctBuckets.empty.size}`,
  )
  if (distinct.size > 0) {
    const mapHitPct = ((distinctBuckets.mapHit.size / distinct.size) * 100).toFixed(1)
    const fallbackPct = ((distinctBuckets.fallback.size / distinct.size) * 100).toFixed(1)
    console.log(`  distinct mapHit: ${mapHitPct}%; distinct fallback: ${fallbackPct}%`)
  }
  if (examples.mapHit.length) {
    console.log("  mapHit examples:")
    for (const e of examples.mapHit) console.log(`    '${e.raw}' -> '${e.displayed}'`)
  }
  if (examples.fallback.length) {
    console.log("  fallback examples (the visibly-wrong cases live here):")
    for (const e of examples.fallback) console.log(`    '${e.raw}' -> '${e.displayed}'`)
  }
  console.log()
}

// ---------------------------------------------------------------------------
// Pass 2 — model-cards-lite.json — `benchmark_names` + `top_benchmark_scores`
// (these are the per-card rollups that pass through `getBenchmarkDisplayName`
// at lib/model-data.ts:410 and surrounding rollup paths)
// ---------------------------------------------------------------------------

if (fs.existsSync(modelCardsLitePath)) {
  console.log(`=== Audit: getBenchmarkDisplayName via model-cards-lite.json benchmark fields ===\n`)
  const cards = JSON.parse(fs.readFileSync(modelCardsLitePath, "utf8"))
  const cardsArr = Array.isArray(cards) ? cards : Object.values(cards)
  console.log(`  total cards: ${cardsArr.length}`)

  // benchmark_names is an array; top_benchmark_scores has .benchmark and .benchmarkKey
  const distinctBenchmarkNames = new Set()
  const distinctTopScoreKeys = new Set()
  const distinctTopScoreBenchmarks = new Set()

  for (const c of cardsArr) {
    if (Array.isArray(c.benchmark_names)) {
      for (const n of c.benchmark_names) distinctBenchmarkNames.add(n)
    }
    if (Array.isArray(c.top_benchmark_scores)) {
      for (const s of c.top_benchmark_scores) {
        if (s.benchmarkKey) distinctTopScoreKeys.add(s.benchmarkKey)
        if (s.benchmark) distinctTopScoreBenchmarks.add(s.benchmark)
      }
    }
  }

  for (const [label, set] of [
    ["card.benchmark_names[]", distinctBenchmarkNames],
    ["card.top_benchmark_scores[].benchmarkKey", distinctTopScoreKeys],
    ["card.top_benchmark_scores[].benchmark (display-name field)", distinctTopScoreBenchmarks],
  ]) {
    const buckets = { mapHit: new Set(), fallback: new Set() }
    const fallbackExamples = []
    for (const v of set) {
      const bucket = classify(v)
      if (bucket === "mapHit") buckets.mapHit.add(v)
      else if (bucket === "fallback") {
        buckets.fallback.add(v)
        if (fallbackExamples.length < 10) {
          fallbackExamples.push({ raw: v, displayed: getBenchmarkDisplayName(v) })
        }
      }
    }
    const totalDistinct = set.size
    const pctMap = totalDistinct > 0 ? ((buckets.mapHit.size / totalDistinct) * 100).toFixed(1) : "0.0"
    const pctFallback = totalDistinct > 0 ? ((buckets.fallback.size / totalDistinct) * 100).toFixed(1) : "0.0"
    console.log(`  --- ${label} ---`)
    console.log(`    ${totalDistinct} distinct; mapHit=${buckets.mapHit.size} (${pctMap}%); fallback=${buckets.fallback.size} (${pctFallback}%)`)
    if (fallbackExamples.length) {
      console.log("    fallback examples:")
      for (const e of fallbackExamples) console.log(`      '${e.raw}' -> '${e.displayed}'`)
    }
  }
  console.log()
}

// ---------------------------------------------------------------------------
// Pass 3 — comparison with pipeline-emitted display_name / canonical_display_name
// (where pipeline already ships a display name, does the TS function agree?)
// ---------------------------------------------------------------------------

console.log(`=== Comparison: TS getBenchmarkDisplayName vs pipeline-emitted display fields ===\n`)
const fieldsWithBoth = [
  { keyField: "benchmark_parent_key", nameField: "benchmark_parent_name", label: "benchmark_parent_key vs benchmark_parent_name" },
  { keyField: "benchmark_family_key", nameField: "benchmark_family_name", label: "benchmark_family_key vs benchmark_family_name" },
  { keyField: "benchmark", nameField: "display_name", label: "benchmark vs display_name" },
  { keyField: "benchmark", nameField: "canonical_display_name", label: "benchmark vs canonical_display_name" },
]

for (const { keyField, nameField, label } of fieldsWithBoth) {
  let agree = 0
  let disagree = 0
  let pipelineMissing = 0
  const examples = []
  for (const e of evals) {
    const key = e[keyField]
    const pipelineName = e[nameField]
    if (!key) continue
    const tsComputed = getBenchmarkDisplayName(key)
    if (pipelineName == null || pipelineName === "") {
      pipelineMissing++
      continue
    }
    if (tsComputed === pipelineName) {
      agree++
    } else {
      disagree++
      if (examples.length < 8) {
        examples.push({ key, pipeline: pipelineName, ts: tsComputed })
      }
    }
  }
  console.log(`  --- ${label} ---`)
  console.log(`    agree=${agree}; disagree=${disagree}; pipelineMissing=${pipelineMissing}`)
  if (examples.length) {
    console.log("    disagreement examples (key | pipeline | TS-computed):")
    for (const e of examples) console.log(`      '${e.key}' | '${e.pipeline}' | '${e.ts}'`)
  }
  console.log()
}

console.log("Done. See notes/transformations/08-benchmark-display-names.md for the full spec.")
