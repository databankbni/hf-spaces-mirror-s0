import "./server-only-shim.mjs"
import fs from "fs"

// === Replicate all three TS implementations verbatim ===

// 1. lib/model-data.ts:76 — uses Number(), multiplies by 1000 if numeric AND no dash
function normalizeEvalTimestamp(value) {
  const numericTimestamp = Number(value)
  return !Number.isNaN(numericTimestamp) && !value.includes("-")
    ? numericTimestamp * 1000
    : new Date(value).getTime()
}

// 2. lib/hf-data.ts:1049 — uses parseFloat, NO multiplier, handles undefined
function toComparableTimestampHfData(timestamp) {
  if (!timestamp) {
    return Number.NEGATIVE_INFINITY
  }
  const numericTimestamp = Number.parseFloat(timestamp)
  if (Number.isFinite(numericTimestamp)) {
    return numericTimestamp
  }
  const parsedTimestamp = new Date(timestamp).getTime()
  return Number.isFinite(parsedTimestamp) ? parsedTimestamp : Number.NEGATIVE_INFINITY
}

// 3. components/benchmark-detail.tsx:1418 — same as hf-data.ts but no undefined handling
function toComparableTimestampBenchmarkDetail(timestamp) {
  const numericTimestamp = Number.parseFloat(timestamp)
  if (Number.isFinite(numericTimestamp)) {
    return numericTimestamp
  }
  const parsedTimestamp = new Date(timestamp).getTime()
  return Number.isFinite(parsedTimestamp) ? parsedTimestamp : Number.NEGATIVE_INFINITY
}

// === Audit: distribution of timestamp formats in production ===

const dir = ".cache/hf-data/models"
const files = fs.readdirSync(dir)
const formats = { isoDateTime: 0, unixSecondsString: 0, unixMsString: 0, empty: 0, other: 0 }
const formatExamples = { isoDateTime: [], unixSecondsString: [], unixMsString: [], other: [] }
let totalChecked = 0

function classify(ts) {
  if (!ts) return "empty"
  // ISO date-time has dashes (YYYY-MM-DD or YYYY-MM-DDTHH:...)
  if (/^\d{4}-\d{2}-\d{2}/.test(ts)) return "isoDateTime"
  // All numeric
  if (/^\d+(\.\d+)?$/.test(ts)) {
    const n = Number.parseFloat(ts)
    // Unix seconds typically ~1.6e9 (year 2020+) up to ~2e9 (2033)
    // Unix ms typically ~1.6e12 (year 2020+) up to ~2e12 (2033)
    if (n < 1e11) return "unixSecondsString"
    return "unixMsString"
  }
  return "other"
}

function walk(node) {
  for (const m of node.metrics ?? []) {
    for (const r of m.model_results ?? []) {
      const ts = r.retrieved_timestamp
      const cat = classify(ts)
      formats[cat] = (formats[cat] ?? 0) + 1
      if (formatExamples[cat] && formatExamples[cat].length < 3) formatExamples[cat].push(ts)
      totalChecked++
    }
  }
  for (const s of node.subtasks ?? []) walk(s)
}
for (const f of files) {
  const data = JSON.parse(fs.readFileSync(`${dir}/${f}`, "utf8"))
  for (const cat of Object.values(data.hierarchy_by_category ?? {})) {
    for (const node of cat) walk(node)
  }
}

console.log(`=== Audit: timestamp format distribution (${totalChecked} model_result rows) ===`)
console.log(formats)
console.log()
for (const [k, exs] of Object.entries(formatExamples)) {
  if (exs.length === 0) continue
  console.log(`--- ${k} examples ---`)
  for (const e of exs) console.log(`  '${e}'`)
}

// === Audit: do the three implementations produce SAME relative ordering? ===
// Pick pairs of distinct-format timestamps and compare under each function.
console.log("\n=== Cross-impl ordering: same input pairs ===")
const pairs = [
  ["1774096306.427425", "2026-04-13T12:34:56Z"],   // unix seconds vs ISO datetime
  ["1774096306427", "2026-04-13T12:34:56Z"],       // unix ms vs ISO
  ["2025-01-01", "2026-01-01"],                    // two ISO dates
  ["1700000000", "1800000000"],                    // two unix seconds
  ["1700000000000", "1800000000000"],              // two unix ms
]
for (const [a, b] of pairs) {
  const m = normalizeEvalTimestamp
  const h = toComparableTimestampHfData
  const c = toComparableTimestampBenchmarkDetail
  console.log(`  pair: '${a}' vs '${b}'`)
  console.log(`    model-data.ts: ${m(a)} vs ${m(b)} (a${m(a) < m(b) ? '<' : m(a) > m(b) ? '>' : '='}b)`)
  console.log(`    hf-data.ts:    ${h(a)} vs ${h(b)} (a${h(a) < h(b) ? '<' : h(a) > h(b) ? '>' : '='}b)`)
  console.log(`    benchmark.tsx: ${c(a)} vs ${c(b)} (a${c(a) < c(b) ? '<' : c(a) > c(b) ? '>' : '='}b)`)
}
