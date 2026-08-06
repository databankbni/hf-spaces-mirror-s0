import "./server-only-shim.mjs"
import fs from "fs"

// Replicate the slug-candidate generators from lib/model-data.ts:150-211 verbatim.
function pipelineSlugify(text) {
  return (
    text
      .replace(/[\x00-\x1f\x7f]/g, "")
      .replace(/[^a-zA-Z0-9._-]/g, "_")
      .replace(/^_+|_+$/g, "") || "unknown"
  )
}

function getModelDetailSlugCandidates(modelId) {
  const normalized = modelId.trim()
  const candidates = new Set()
  const withSlash = normalized.replace(/\//g, "__")
  const withDots = withSlash.replace(/\./g, "-")
  candidates.add(pipelineSlugify(withSlash))
  candidates.add(pipelineSlugify(withSlash.toLowerCase()))
  candidates.add(pipelineSlugify(withDots))
  candidates.add(pipelineSlugify(withDots.toLowerCase()))
  candidates.add(pipelineSlugify(normalized))
  candidates.add(pipelineSlugify(normalized.toLowerCase()))
  return Array.from(candidates)
}

function getDeveloperSlugCandidates(developerOrRouteId) {
  const normalized = developerOrRouteId.trim()
  const candidates = new Set()
  const lowercase = normalized.toLowerCase()
  const underscoreSlug = pipelineSlugify(normalized)
  const lowercaseUnderscoreSlug = pipelineSlugify(lowercase)
  const hyphenSlug = lowercase
    .replace(/[\x00-\x1f\x7f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
  const compactSlug = lowercase.replace(/[^a-z0-9]+/g, "")
  candidates.add(underscoreSlug)
  candidates.add(lowercaseUnderscoreSlug)
  candidates.add(underscoreSlug.replace(/_/g, "-"))
  candidates.add(lowercaseUnderscoreSlug.replace(/_/g, "-"))
  if (hyphenSlug) candidates.add(hyphenSlug)
  if (compactSlug) candidates.add(compactSlug)
  return Array.from(candidates)
}

// === Audit: for each model card, which candidate position resolves? ===
const cards = JSON.parse(fs.readFileSync(".cache/hf-data/model-cards.json", "utf8"))
const modelFiles = new Set(fs.readdirSync(".cache/hf-data/models"))

console.log(`=== Model lookups (${cards.length} cards) ===`)
const modelHitPositions = new Map()
let modelMisses = 0
const modelMissExamples = []

for (const c of cards) {
  // Try the family_id (with slash) since that's what getModelSummaryById uses
  const candidates = getModelDetailSlugCandidates(c.model_family_id)
  let hitPos = -1
  for (let i = 0; i < candidates.length; i++) {
    if (modelFiles.has(`${candidates[i]}.json`)) {
      hitPos = i
      break
    }
  }
  if (hitPos === -1) {
    modelMisses++
    if (modelMissExamples.length < 5) modelMissExamples.push({ family: c.model_family_id, route: c.model_route_id, candidates })
  } else {
    modelHitPositions.set(hitPos, (modelHitPositions.get(hitPos) ?? 0) + 1)
  }
}
for (const [pos, n] of [...modelHitPositions.entries()].sort((a, b) => a[0] - b[0])) {
  console.log(`  position ${pos}: ${n} hits`)
}
console.log(`  misses (none of 6 candidates worked): ${modelMisses}`)
if (modelMissExamples.length) console.log("  miss examples:", modelMissExamples)

// === Audit: for each developer, which candidate position resolves? ===
const devs = JSON.parse(fs.readFileSync(".cache/hf-data/developers.json", "utf8"))
const developerFiles = new Set(fs.readdirSync(".cache/hf-data/developers"))

console.log(`\n=== Developer lookups (${devs.length} developers) ===`)
const devHitPositions = new Map()
let devMisses = 0
const devMissExamples = []

for (const d of devs) {
  const candidates = getDeveloperSlugCandidates(d.developer ?? d.route_id ?? "")
  let hitPos = -1
  for (let i = 0; i < candidates.length; i++) {
    if (developerFiles.has(`${candidates[i]}.json`)) {
      hitPos = i
      break
    }
  }
  if (hitPos === -1) {
    devMisses++
    if (devMissExamples.length < 5) devMissExamples.push({ dev: d.developer, candidates })
  } else {
    devHitPositions.set(hitPos, (devHitPositions.get(hitPos) ?? 0) + 1)
  }
}
for (const [pos, n] of [...devHitPositions.entries()].sort((a, b) => a[0] - b[0])) {
  console.log(`  position ${pos}: ${n} hits`)
}
console.log(`  misses (none of 6 candidates worked): ${devMisses}`)
if (devMissExamples.length) console.log("  miss examples:", devMissExamples)

// === Show example candidates for a dotted-name model ===
console.log("\n=== Example: openai/gpt-5.2 candidates ===")
const exCandidates = getModelDetailSlugCandidates("openai/gpt-5.2")
for (let i = 0; i < exCandidates.length; i++) {
  const exists = modelFiles.has(`${exCandidates[i]}.json`)
  console.log(`  [${i}] '${exCandidates[i]}.json' ${exists ? "← HIT" : "(miss)"}`)
}
