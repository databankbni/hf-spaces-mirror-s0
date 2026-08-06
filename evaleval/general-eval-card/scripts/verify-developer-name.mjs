import "./server-only-shim.mjs"
import fs from "fs"

// Replicate normalizeDeveloperName from lib/model-data.ts:217-244 verbatim.
const KNOWN_DEVELOPER_NAMES = {
  openai: "OpenAI",
  google: "Google",
  anthropic: "Anthropic",
  meta: "Meta",
  microsoft: "Microsoft",
  mistralai: "Mistral AI",
  deepseek: "DeepSeek",
  "deepseek-ai": "DeepSeek",
  cohere: "Cohere",
  nvidia: "NVIDIA",
  alibaba: "Alibaba",
  amazon: "Amazon",
  apple: "Apple",
  ibm: "IBM",
  xai: "xAI",
  "x-ai": "xAI",
}

function normalizeDeveloperName(name) {
  const key = name.trim().toLowerCase()
  if (KNOWN_DEVELOPER_NAMES[key]) return KNOWN_DEVELOPER_NAMES[key]
  if (name === name.toLowerCase() && /^[a-z]/.test(name)) {
    return name.charAt(0).toUpperCase() + name.slice(1)
  }
  return name
}

const devs = JSON.parse(fs.readFileSync(".cache/hf-data/developers.json", "utf8"))

console.log(`=== Audit: normalizeDeveloperName across ${devs.length} developers ===`)
const buckets = { mapHit: 0, titleCase: 0, passthrough: 0 }
const examples = { mapHit: [], titleCase: [], passthrough: [] }
for (const d of devs) {
  const raw = d.developer
  const normalized = normalizeDeveloperName(raw)
  const key = raw.trim().toLowerCase()
  let bucket
  if (KNOWN_DEVELOPER_NAMES[key]) bucket = "mapHit"
  else if (raw === raw.toLowerCase() && /^[a-z]/.test(raw)) bucket = "titleCase"
  else bucket = "passthrough"
  buckets[bucket]++
  if (examples[bucket].length < 5) examples[bucket].push({ raw, normalized })
}
console.log(buckets)
console.log()
for (const [bucket, exs] of Object.entries(examples)) {
  console.log(`--- ${bucket} ---`)
  for (const e of exs) console.log(`  '${e.raw}' → '${e.normalized}'`)
}

// Also check model-cards.json — `developer` field there
console.log("\n=== Audit: across 5830 model-cards.json entries ===")
const cards = JSON.parse(fs.readFileSync(".cache/hf-data/model-cards.json", "utf8"))
const cardBuckets = { mapHit: 0, titleCase: 0, passthrough: 0 }
for (const c of cards) {
  const raw = c.developer
  const key = raw.trim().toLowerCase()
  let bucket
  if (KNOWN_DEVELOPER_NAMES[key]) bucket = "mapHit"
  else if (raw === raw.toLowerCase() && /^[a-z]/.test(raw)) bucket = "titleCase"
  else bucket = "passthrough"
  cardBuckets[bucket]++
}
console.log(cardBuckets)

// Distinct developer names
const distinctDevs = new Set(devs.map(d => d.developer))
console.log("\n=== Distinct developer name strings:", distinctDevs.size, "===")
