import "./server-only-shim.mjs"
import fs from "fs"
import path from "path"

// Audit script for `notes/transformations/12-instance-level-data.md`.
//
// Walks .cache/hf-data/models/*.json, finds every result row that has
// `instance_level_data.instance_examples`, replicates the parser's branch
// logic, and reports:
//   - Prevalence (% of rows / files with sample data)
//   - ild-level shape uniformity (which top-level keys appear)
//   - interaction_type distribution
//   - Per-output-field branch firing rates (which fallback path wins for each)
//   - Distinct example top-level key signatures (top 5)
//
// Output is the raw distribution; the spec's "Pipeline status" section quotes
// these numbers. Run after `pnpm cache-hf-data` to refresh.

const CACHE_DIR = ".cache/hf-data"
const MODELS_DIR = path.join(CACHE_DIR, "models")

if (!fs.existsSync(MODELS_DIR)) {
  console.error("=== ERROR: HF data cache missing ===")
  console.error(`  Expected: ${MODELS_DIR}`)
  console.error("  Prime it first:  pnpm cache-hf-data")
  process.exit(1)
}

const files = fs.readdirSync(MODELS_DIR).filter((f) => f.endsWith(".json"))

// Tally trackers
const branchHits = {
  input: { string: 0, "input.raw": 0, prompt: 0, question: 0, "doc.question": 0, "doc.JSON": 0, EMPTY: 0 },
  ground_truth: { "input.reference": 0, ground_truth: 0, target: 0, gold: 0, "doc.answer": 0, NONE: 0 },
  response: { output: 0, response: 0, model_output: 0, answer_attribution: 0, messages: 0, filtered_resps: 0, resps: 0, EMPTY: 0 },
  is_correct: { "evaluation.is_correct": 0, is_correct: 0, "metrics.exact_match": 0, NONE: 0 },
  sample_id: { sample_id: 0, doc_id: 0, id: 0, index_fallback: 0 },
  choices: { choices: 0, "doc.choices": 0, NONE: 0 },
}

let totalFiles = 0
let filesWithAnyIld = 0
let totalEvals = 0
let evalsWithIld = 0
let totalResults = 0
let resultsWithIld = 0
let totalExamples = 0
let totalInstanceCountSum = 0  // sum of full-set sizes (i.e. URL JSONL totals)

const ildKeysSeen = new Map()
const interactionTypes = new Map()
const exampleKeysHistogram = new Map()

function classifyExample(raw) {
  if (!raw || typeof raw !== "object") return
  totalExamples++

  // Track first-level keys present
  const sig = Object.keys(raw).sort().join(",")
  exampleKeysHistogram.set(sig, (exampleKeysHistogram.get(sig) ?? 0) + 1)

  // input
  if (typeof raw.input === "string") branchHits.input.string++
  else if (raw.input?.raw != null) branchHits.input["input.raw"]++
  else if (raw.prompt) branchHits.input.prompt++
  else if (raw.question) branchHits.input.question++
  else if (raw.doc?.question) branchHits.input["doc.question"]++
  else if (raw.doc) branchHits.input["doc.JSON"]++
  else branchHits.input.EMPTY++

  // ground_truth
  if (raw.input?.reference != null) branchHits.ground_truth["input.reference"]++
  else if (raw.ground_truth != null) branchHits.ground_truth.ground_truth++
  else if (raw.target != null) branchHits.ground_truth.target++
  else if (raw.gold != null) branchHits.ground_truth.gold++
  else if (raw.doc?.answer != null) branchHits.ground_truth["doc.answer"]++
  else branchHits.ground_truth.NONE++

  // response
  if (raw.output != null) branchHits.response.output++
  else if (raw.response) branchHits.response.response++
  else if (raw.model_output) branchHits.response.model_output++
  else if (Array.isArray(raw.answer_attribution) && raw.answer_attribution.length > 0) branchHits.response.answer_attribution++
  else if (Array.isArray(raw.messages) && raw.messages.length > 0) branchHits.response.messages++
  else if (raw.filtered_resps?.[0]?.[0]) branchHits.response.filtered_resps++
  else if (raw.resps?.[0]?.[0]) branchHits.response.resps++
  else branchHits.response.EMPTY++

  // is_correct
  if (raw.evaluation?.is_correct !== undefined) branchHits.is_correct["evaluation.is_correct"]++
  else if (raw.is_correct !== undefined) branchHits.is_correct.is_correct++
  else if (raw.metrics?.exact_match === 1 || raw.metrics?.exact_match === 0) branchHits.is_correct["metrics.exact_match"]++
  else branchHits.is_correct.NONE++

  // sample_id
  if (raw.sample_id != null) branchHits.sample_id.sample_id++
  else if (raw.doc_id != null) branchHits.sample_id.doc_id++
  else if (raw.id != null) branchHits.sample_id.id++
  else branchHits.sample_id.index_fallback++

  // choices
  if (raw.choices != null) branchHits.choices.choices++
  else if (raw.doc?.choices != null) branchHits.choices["doc.choices"]++
  else branchHits.choices.NONE++
}

function walk(node) {
  let nodeHasIld = false
  for (const m of node.metrics ?? []) {
    totalEvals++
    let evalHasIld = false
    for (const r of m.model_results ?? []) {
      totalResults++
      const ild = r.instance_level_data
      if (ild != null && typeof ild === "object" && Array.isArray(ild.instance_examples) && ild.instance_examples.length > 0) {
        resultsWithIld++
        evalHasIld = true
        nodeHasIld = true

        const ildSig = Object.keys(ild).sort().join(",")
        ildKeysSeen.set(ildSig, (ildKeysSeen.get(ildSig) ?? 0) + 1)
        if (typeof ild.interaction_type === "string") {
          interactionTypes.set(ild.interaction_type, (interactionTypes.get(ild.interaction_type) ?? 0) + 1)
        }
        if (typeof ild.instance_count === "number") {
          totalInstanceCountSum += ild.instance_count
        }
        for (const ex of ild.instance_examples) {
          classifyExample(ex)
        }
      }
    }
    if (evalHasIld) evalsWithIld++
  }
  for (const s of node.subtasks ?? []) walk(s)
  return nodeHasIld
}

for (const f of files) {
  totalFiles++
  let fileHasIld = false
  let data
  try {
    data = JSON.parse(fs.readFileSync(path.join(MODELS_DIR, f), "utf-8"))
  } catch {
    continue
  }
  for (const cat of Object.values(data.hierarchy_by_category ?? {})) {
    for (const node of cat) {
      if (walk(node)) fileHasIld = true
    }
  }
  if (fileHasIld) filesWithAnyIld++
}

const pct = (n, total = totalExamples) => (total ? ((100 * n) / total).toFixed(2) + "%" : "-")

console.log("=== Audit: instance_level_data prevalence ===")
console.log(`  Total model files:       ${totalFiles}`)
console.log(`  Files with any ild:      ${filesWithAnyIld}  (${pct(filesWithAnyIld, totalFiles)})`)
console.log(`  Total (metric × result) rows: ${totalResults}`)
console.log(`  Result rows with ild:    ${resultsWithIld}  (${pct(resultsWithIld, totalResults)})`)
console.log(`  Total inline preview examples (≤5 per row): ${totalExamples}`)
console.log(`  Total full samples (sum of instance_count, accessible via source_url):  ${totalInstanceCountSum}`)

console.log("\n=== ild-level top-level key signatures ===")
for (const [k, v] of [...ildKeysSeen.entries()].sort((a, b) => b[1] - a[1])) {
  console.log(`  ${v}x: ${k}`)
}

console.log("\n=== interaction_type distribution ===")
for (const [k, v] of [...interactionTypes.entries()].sort((a, b) => b[1] - a[1])) {
  console.log(`  ${v}x: ${k}`)
}

console.log("\n=== Per-field branch firing rates ===\n")
for (const [field, branches] of Object.entries(branchHits)) {
  console.log(`--- ${field} ---`)
  for (const [b, n] of Object.entries(branches)) {
    console.log(`  ${b}: ${n}  (${pct(n)})`)
  }
  console.log()
}

console.log("=== Distinct example top-level key signatures (top 5) ===")
const sorted = [...exampleKeysHistogram.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5)
for (const [sig, count] of sorted) {
  console.log(`  ${count}x: ${sig.substring(0, 200)}${sig.length > 200 ? "…" : ""}`)
}

console.log("\n=== Summary for spec ===")
console.log(`Inline preview prevalence: ${resultsWithIld}/${totalResults} rows (${pct(resultsWithIld, totalResults)})`)
console.log(`Full-corpus samples behind source_url: ~${totalInstanceCountSum} (vs ${totalExamples} loaded inline)`)
console.log(`Defensive scaffolding firing rate: see per-field breakdown above. Most branches are 0.00%.`)
