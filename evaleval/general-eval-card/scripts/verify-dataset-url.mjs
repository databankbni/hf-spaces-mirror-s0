import "./server-only-shim.mjs"
import fs from "fs"

// Replicate the dataset_url fallback chain from components/eval-card.tsx:83-86 verbatim.
// Original uses `??` (nullish), NOT truthiness — empty strings stay; only
// null/undefined fall through. Pipeline must produce identical outputs.
function resolveDatasetUrl(sourceData) {
  const fromDataset = sourceData?.dataset_url
  const fromUrl = Array.isArray(sourceData?.url) ? sourceData?.url?.[0] : sourceData?.url
  const fromHfRepo = sourceData?.hf_repo ? `https://huggingface.co/datasets/${sourceData.hf_repo}` : undefined
  return fromDataset ?? fromUrl ?? fromHfRepo
}

// === Audit: distribution of which fallback branch fires ===
const dir = ".cache/hf-data/evals"
const files = fs.readdirSync(dir)

const branches = { dataset_url: 0, url_array: 0, url_string: 0, hf_repo: 0, undefined: 0 }
const examples = { dataset_url: [], url_array: [], url_string: [], hf_repo: [], undefined: [] }
let total = 0

for (const f of files) {
  const data = JSON.parse(fs.readFileSync(`${dir}/${f}`, "utf8"))
  const sd = data.source_data
  total++
  const url = resolveDatasetUrl(sd)
  let branch
  if (!sd) branch = "undefined"
  else if (sd.dataset_url) branch = "dataset_url"
  else if (Array.isArray(sd.url)) branch = "url_array"
  else if (typeof sd.url === "string") branch = "url_string"
  else if (sd.hf_repo) branch = "hf_repo"
  else branch = "undefined"
  branches[branch]++
  if (examples[branch].length < 3) examples[branch].push({ id: data.eval_summary_id, sourceData: sd, resolved: url })
}

console.log(`=== Audit: dataset_url fallback branch distribution (${total} eval-detail files) ===`)
for (const [b, n] of Object.entries(branches)) {
  console.log(`  ${b}: ${n}`)
}
console.log()
console.log("=== Examples per branch ===")
for (const [b, exs] of Object.entries(examples)) {
  if (exs.length === 0) continue
  console.log(`\n--- ${b} ---`)
  for (const ex of exs) {
    console.log(`  ${ex.id}: source_data=${JSON.stringify(ex.sourceData)}`)
    console.log(`    → resolved: ${ex.resolved}`)
  }
}
