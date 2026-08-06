#!/usr/bin/env node

const DEFAULT_BASE_URL = "http://localhost:3000"

const args = new Map()
for (let i = 2; i < process.argv.length; i += 2) {
  const key = process.argv[i]
  const value = process.argv[i + 1]
  if (!key?.startsWith("--") || value == null) {
    throw new Error("Usage: node scripts/compare-data-backends.mjs --json-base http://localhost:3000 --duckdb-base http://localhost:3001")
  }
  args.set(key, value)
}

const jsonBase = args.get("--json-base") ?? process.env.JSON_BASE_URL ?? DEFAULT_BASE_URL
const duckdbBase = args.get("--duckdb-base") ?? process.env.DUCKDB_BASE_URL ?? jsonBase

function endpoint(path) {
  return path.startsWith("/") ? path : `/${path}`
}

async function fetchJson(baseUrl, path) {
  const url = new URL(endpoint(path), baseUrl)
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`${url.toString()} returned ${response.status} ${response.statusText}`)
  }
  return response.json()
}

function stableArrayKey(item) {
  if (!item || typeof item !== "object" || Array.isArray(item)) {
    return null
  }

  const record = item
  return (
    record.eval_summary_id ??
    record.evaluation_id ??
    record.model_route_id ??
    record.route_id ??
    record.developer_route_id ??
    record.model_id ??
    record.id ??
    record.column_key ??
    record.metric_summary_id ??
    record.metric_name ??
    record.name ??
    null
  )
}

function normalize(value) {
  if (Array.isArray(value)) {
    const normalized = value.map(normalize)
    if (normalized.every((item) => stableArrayKey(item) != null)) {
      normalized.sort((a, b) => String(stableArrayKey(a)).localeCompare(String(stableArrayKey(b))))
    }
    return normalized
  }

  if (!value || typeof value !== "object") {
    return value
  }

  const entries = Object.entries(value)
    .map(([key, nestedValue]) => [key, normalize(nestedValue)])
    .sort(([a], [b]) => a.localeCompare(b))
  return Object.fromEntries(entries)
}

function diffPaths(left, right, prefix = "") {
  const out = []
  if (left === right) return out
  if (
    left == null || right == null ||
    typeof left !== typeof right ||
    Array.isArray(left) !== Array.isArray(right) ||
    typeof left !== "object"
  ) {
    out.push({ path: prefix || "<root>", left, right })
    return out
  }

  if (Array.isArray(left)) {
    const max = Math.max(left.length, right.length)
    if (left.length !== right.length) {
      out.push({ path: `${prefix}.length`, left: left.length, right: right.length })
    }
    for (let i = 0; i < max && out.length < 20; i++) {
      out.push(...diffPaths(left[i], right[i], `${prefix}[${i}]`))
    }
    return out
  }

  const keys = new Set([...Object.keys(left), ...Object.keys(right)])
  for (const key of keys) {
    if (out.length >= 20) break
    out.push(...diffPaths(left[key], right[key], prefix ? `${prefix}.${key}` : key))
  }
  return out
}

const FAIL_FAST = process.env.PARITY_FAIL_FAST !== "0"
const failures = []

function assertEqual(label, left, right) {
  const normalizedLeft = normalize(left)
  const normalizedRight = normalize(right)
  const leftText = JSON.stringify(normalizedLeft)
  const rightText = JSON.stringify(normalizedRight)

  if (leftText === rightText) {
    console.log(`✓ ${label}`)
    return
  }

  console.log(`✗ ${label}`)
  const diffs = diffPaths(normalizedLeft, normalizedRight)
  for (const diff of diffs.slice(0, 12)) {
    const left = JSON.stringify(diff.left)
    const right = JSON.stringify(diff.right)
    const truncate = (text) => text != null && text.length > 160 ? `${text.slice(0, 160)}…` : text
    console.log(`  ${diff.path}`)
    console.log(`    JSON   : ${truncate(left)}`)
    console.log(`    DuckDB : ${truncate(right)}`)
  }
  if (diffs.length > 12) {
    console.log(`  …(${diffs.length - 12} more)`)
  }

  failures.push(label)
  if (FAIL_FAST) {
    throw new Error(`Mismatch for ${label}`)
  }
}

async function compareEndpoint(path) {
  const [jsonValue, duckdbValue] = await Promise.all([
    fetchJson(jsonBase, path),
    fetchJson(duckdbBase, path),
  ])
  assertEqual(path, jsonValue, duckdbValue)
  return jsonValue
}

const evalListLite = await compareEndpoint("/api/eval-list-lite")
const modelCardsLite = await compareEndpoint("/api/model-cards-lite")
await compareEndpoint("/api/eval-list")
await compareEndpoint("/api/model-cards")

const evalId = evalListLite?.evals?.[0]?.evaluation_id ?? evalListLite?.evals?.[0]?.eval_summary_id
if (evalId) {
  await compareEndpoint(`/api/eval-summary?id=${encodeURIComponent(evalId)}`)
} else {
  console.warn("No eval id found in /api/eval-list-lite; skipping eval summary parity")
}

const modelId = modelCardsLite?.[0]?.route_id ?? modelCardsLite?.[0]?.model_route_id ?? modelCardsLite?.[0]?.id
if (modelId) {
  await compareEndpoint(`/api/model-summary?id=${encodeURIComponent(modelId)}`)
} else {
  console.warn("No model id found in /api/model-cards-lite; skipping model summary parity")
}

try {
  const developers = await compareEndpoint("/api/developers")
  const developerId = developers?.[0]?.route_id
  if (developerId) {
    await compareEndpoint(`/api/developer-summary?id=${encodeURIComponent(developerId)}`)
  } else {
    console.warn("No developer id found in /api/developers; skipping developer summary parity")
  }
} catch (error) {
  console.warn(`Developer parity skipped: ${error instanceof Error ? error.message : String(error)}`)
}

console.log(`Compared JSON backend ${jsonBase} with DuckDB backend ${duckdbBase}`)

if (failures.length > 0) {
  console.error(`\n${failures.length} endpoint(s) failed parity:`)
  for (const label of failures) console.error(`  - ${label}`)
  process.exit(1)
}
