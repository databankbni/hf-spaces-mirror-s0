import "./server-only-shim.mjs"
import fs from "fs"
import path from "path"

// === Replicate all five TS implementations verbatim ===

// Variant A: lib/model-data.ts:312-354 (parseParamsBillions)
function parseParamsBillions(value) {
  if (typeof value === "number") {
    return Number.isFinite(value) && value > 0 ? value : null
  }
  if (typeof value !== "string") return null

  const normalized = value.trim().toLowerCase()
  if (!normalized) return null

  const compact = normalized.replace(/,/g, "")
  const tokenMatch = compact.match(
    /(\d+(?:\.\d+)?)\s*(trillion|tn|t|billion|bn|b|million|mn|m|thousand|k)\b/
  )
  if (tokenMatch) {
    const amount = Number.parseFloat(tokenMatch[1])
    if (!Number.isFinite(amount) || amount <= 0) return null
    const unit = tokenMatch[2]
    if (unit === "trillion" || unit === "tn" || unit === "t") return amount * 1000
    if (unit === "billion" || unit === "bn" || unit === "b") return amount
    if (unit === "million" || unit === "mn" || unit === "m") return amount / 1000
    if (unit === "thousand" || unit === "k") return amount / 1_000_000
  }
  const numeric = Number.parseFloat(compact)
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null
}

// Variant B: components/eval-detail.tsx:81-119 (parseParamsBillionsFromText)
function parseParamsBillionsFromText(value) {
  if (!value) return null
  const normalized = value.trim().toLowerCase()
  if (!normalized) return null
  const compact = normalized.replace(/,/g, "")
  const tokenMatch = compact.match(
    /(\d+(?:\.\d+)?)\s*(trillion|tn|t|billion|bn|b|million|mn|m|thousand|k)\b/
  )
  if (tokenMatch) {
    const amount = Number.parseFloat(tokenMatch[1])
    if (!Number.isFinite(amount)) return null
    const unit = tokenMatch[2]
    if (unit === "trillion" || unit === "tn" || unit === "t") return amount * 1000
    if (unit === "billion" || unit === "bn" || unit === "b") return amount
    if (unit === "million" || unit === "mn" || unit === "m") return amount / 1000
    if (unit === "thousand" || unit === "k") return amount / 1_000_000
  }
  const numeric = Number.parseFloat(compact)
  return Number.isFinite(numeric) ? numeric : null
}

// Variant C: components/eval-detail.tsx:121-155 (parseParamsBillionsFromModelName)
function parseParamsBillionsFromModelNameC(modelName) {
  if (!modelName) return null
  const sizeTokens = Array.from(modelName.matchAll(/\b(\d+(?:\.\d+)?)\s*([tmbk])\b/gi))
  if (sizeTokens.length === 0) return null
  const lastToken = sizeTokens[sizeTokens.length - 1]
  const numericValue = Number.parseFloat(lastToken[1])
  if (!Number.isFinite(numericValue)) return null
  const unit = lastToken[2].toLowerCase()
  if (unit === "t") return numericValue * 1000
  if (unit === "b") return numericValue
  if (unit === "m") return numericValue / 1000
  if (unit === "k") return numericValue / 1_000_000
  return null
}

// Variant E: components/model-compare-dialog.tsx:44-60 (parseParamsBillionsFromModelName)
function parseParamsBillionsFromModelNameE(modelName) {
  if (!modelName) return null
  const sizeTokens = Array.from(modelName.matchAll(/\b(\d+(?:\.\d+)?)\s*([bm])\b/gi))
  if (sizeTokens.length === 0) return null
  const lastToken = sizeTokens[sizeTokens.length - 1]
  const numericValue = Number(lastToken[1])
  if (!Number.isFinite(numericValue)) return null
  const unit = lastToken[2].toLowerCase()
  if (unit === "b") return numericValue
  if (unit === "m") return numericValue / 1000
  return null
}

// Variant F: app/evals/[id]/page.tsx:434-437 (inline)
function parseParamsBillionsInline(name, id) {
  const sizeMatch = (String(name ?? "") + " " + String(id ?? "")).match(
    /\b(\d+(?:\.\d+)?)\s*[bB]\b/
  )
  if (sizeMatch) return parseFloat(sizeMatch[1])
  return null
}

// === Audit ===

const cacheDir = ".cache/hf-data"
if (!fs.existsSync(cacheDir)) {
  console.error(`No cache at ${cacheDir}. Run \`pnpm cache-hf-data\` first.`)
  process.exit(1)
}

// ---- 1) Distribution of `model-cards.json.params_billions` (Variant A's input)
const cardsPath = path.join(cacheDir, "model-cards.json")
let modelCardsTypeDist = { number: 0, string: 0, null: 0, other: 0 }
let modelCardsAOutputs = { positive: 0, zero: 0, negative: 0, nan: 0, null: 0 }
let modelCardsCount = 0
if (fs.existsSync(cardsPath)) {
  const cards = JSON.parse(fs.readFileSync(cardsPath, "utf8"))
  modelCardsCount = cards.length
  for (const card of cards) {
    const v = card.params_billions
    const t = v === null ? "null" : typeof v
    modelCardsTypeDist[t] = (modelCardsTypeDist[t] ?? 0) + 1
    const out = parseParamsBillions(v)
    if (out === null) modelCardsAOutputs.null++
    else if (Number.isNaN(out)) modelCardsAOutputs.nan++
    else if (out > 0) modelCardsAOutputs.positive++
    else if (out === 0) modelCardsAOutputs.zero++
    else modelCardsAOutputs.negative++
  }
}

// ---- 2) Per-model-result audit
const modelsDir = path.join(cacheDir, "models")
const files = fs.existsSync(modelsDir) ? fs.readdirSync(modelsDir) : []

// Buckets:
//  - 'add.params_billions': string|number|undefined per row
//  - format distribution of strings (clean decimal? unit-suffixed?)
//  - model name format distribution (b-suffix? K-suffix? T-suffix? MoE 8x7B? bare like GPT-4?)
//  - per-row Variant D resolution: which fallback fires
const addPbTypeDist = { undefined: 0, null: 0, number: 0, string: 0, other: 0 }
const stringPbFormatDist = { cleanDecimal: 0, unitSuffix: 0, other: 0 }
const stringPbExamples = { cleanDecimal: [], unitSuffix: [], other: [] }
const nameFormatDist = {
  hasBOnly: 0,           // "Llama-3-70B-Instruct"
  hasBAndContextWindow: 0, // "Llama-3-70B-Instruct-8K" (contains B and K)
  hasBAndT: 0,           // contains both B and T
  hasMOnly: 0,           // "560M"
  hasMoEPattern: 0,      // "Mixtral-8x7B" (\dx\d before B)
  noUnitToken: 0,        // "GPT-4", no unit suffix
  empty: 0,
}
const nameExamples = {
  hasBOnly: [],
  hasBAndContextWindow: [],
  hasBAndT: [],
  hasMOnly: [],
  hasMoEPattern: [],
  noUnitToken: [],
}
const variantDFallback = {
  addPbNumber: 0,        // additional_details.params_billions is number → returned as-is
  addPbString: 0,        // additional_details.params_billions is string → Variant B
  addParameterCount: 0,  // additional_details.parameter_count fallback
  addNumParameters: 0,
  addParams: 0,
  miParameterCount: 0,
  modelNameFallback: 0,  // last fallback: parseParamsBillionsFromModelName(name) — Variant C
  noResolution: 0,       // all paths return null/undefined
}

// Cross-variant disagreement on names (where parsers agree on B/None but C diverges)
let nameAgreementCounts = {
  allConverge: 0,          // A,B,C,E,F all return same value (or all null)
  cTSQuirkContextWindow: 0, // C returns context-window (≪ 1), F/E/A/B return param count
  fOnlyMissing: 0,         // F returns null because no B, but others find something
  someDisagreement: 0,
}
const disagreementExamples = []

let totalRows = 0
let count = 0
const FILE_CAP = 100000

function classifyName(name) {
  if (!name) return "empty"
  // Detect MoE pattern: digit + 'x' + digit + B (no \b between x and digit)
  if (/\dx\d+\s*[bB]\b/.test(name)) return "hasMoEPattern"
  const hasB = /\b\d+(\.\d+)?\s*[bB]\b/.test(name)
  const hasContextWindow = /\b\d+\s*[kK]\b/.test(name)
  const hasT = /\b\d+(\.\d+)?\s*[tT]\b/.test(name)
  const hasM = /\b\d+(\.\d+)?\s*[mM]\b/.test(name)
  if (hasB && hasContextWindow) return "hasBAndContextWindow"
  if (hasB && hasT) return "hasBAndT"
  if (hasB) return "hasBOnly"
  if (hasM) return "hasMOnly"
  return "noUnitToken"
}

function classifyStringPb(s) {
  if (/^\d+(\.\d+)?$/.test(s.trim())) return "cleanDecimal"
  if (
    /(\d+(\.\d+)?)\s*(trillion|tn|t|billion|bn|b|million|mn|m|thousand|k)\b/i.test(s)
  )
    return "unitSuffix"
  return "other"
}

function processModelInfo(mi) {
  totalRows++
  const ad = mi.additional_details || {}
  const v = ad.params_billions
  const t = v === undefined ? "undefined" : v === null ? "null" : typeof v
  addPbTypeDist[t] = (addPbTypeDist[t] ?? 0) + 1

  if (typeof v === "string") {
    const fmt = classifyStringPb(v)
    stringPbFormatDist[fmt]++
    if (stringPbExamples[fmt].length < 5) stringPbExamples[fmt].push(v)
  }

  // Variant D fallback resolution
  let resolved = false
  const rawPb =
    ad.params_billions ?? ad.parameter_count ?? ad.num_parameters ?? ad.params
  if (typeof rawPb === "number") {
    if (ad.params_billions != null) variantDFallback.addPbNumber++
    else if (ad.parameter_count != null) variantDFallback.addParameterCount++
    else if (ad.num_parameters != null) variantDFallback.addNumParameters++
    else variantDFallback.addParams++
    resolved = true
  } else if (typeof rawPb === "string") {
    const parsed = parseParamsBillionsFromText(rawPb)
    if (Number.isFinite(parsed)) {
      if (ad.params_billions != null) variantDFallback.addPbString++
      else if (ad.parameter_count != null) variantDFallback.addParameterCount++
      else if (ad.num_parameters != null) variantDFallback.addNumParameters++
      else variantDFallback.addParams++
      resolved = true
    }
  }
  if (!resolved && typeof mi.parameter_count === "string") {
    const parsed = parseParamsBillionsFromText(mi.parameter_count)
    if (Number.isFinite(parsed)) {
      variantDFallback.miParameterCount++
      resolved = true
    }
  }
  if (!resolved) {
    const parsed = parseParamsBillionsFromModelNameC(mi.name)
    if (parsed != null) {
      variantDFallback.modelNameFallback++
      resolved = true
    }
  }
  if (!resolved) variantDFallback.noResolution++

  // Name format
  const cls = classifyName(mi.name)
  nameFormatDist[cls] = (nameFormatDist[cls] ?? 0) + 1
  if (nameExamples[cls] && nameExamples[cls].length < 5 && mi.name) {
    nameExamples[cls].push(mi.name)
  }

  // Cross-variant on the name
  if (mi.name) {
    const a = parseParamsBillions(mi.name)
    const b = parseParamsBillionsFromText(mi.name)
    const c = parseParamsBillionsFromModelNameC(mi.name)
    const e = parseParamsBillionsFromModelNameE(mi.name)
    const f = parseParamsBillionsInline(mi.name, mi.id ?? "")

    const vals = [a, b, c, e, f]
    const allEq = vals.every((x) => x === vals[0] || (x == null && vals[0] == null))
    if (allEq) nameAgreementCounts.allConverge++
    else {
      // C-specific TS quirk: c is much smaller (< 0.001) while a/e/f match
      if (c != null && c < 0.001 && a != null && e === a && f === a) {
        nameAgreementCounts.cTSQuirkContextWindow++
        if (disagreementExamples.length < 10) {
          disagreementExamples.push({
            name: mi.name,
            id: mi.id,
            type: "C TS-quirk: context-window beats param count",
            values: { A: a, B: b, C: c, E: e, F: f },
          })
        }
      } else if (f == null && (a != null || c != null || e != null)) {
        nameAgreementCounts.fOnlyMissing++
      } else {
        nameAgreementCounts.someDisagreement++
        if (disagreementExamples.length < 10) {
          disagreementExamples.push({
            name: mi.name,
            id: mi.id,
            type: "other disagreement",
            values: { A: a, B: b, C: c, E: e, F: f },
          })
        }
      }
    }
  }
}

function walk(node, topModelInfo) {
  for (const m of node.metrics ?? []) {
    for (const r of m.model_results ?? []) {
      // Per-row model_info doesn't exist in the cache; the runtime
      // buildModelInfoForVariant in lib/hf-data.ts:1133 spreads
      // detail.model_info onto each row. So for audit purposes we treat the
      // top-level model_info as the per-row model_info.
      const mi = {
        ...topModelInfo,
        id: r.raw_model_id ?? r.model_id ?? topModelInfo.id,
        name: r.model_name || topModelInfo.name,
        developer: r.developer || topModelInfo.developer,
        additional_details: {
          ...(topModelInfo.additional_details || {}),
          raw_model_id: r.raw_model_id ?? r.model_id,
        },
      }
      processModelInfo(mi)
    }
  }
  for (const s of node.subtasks ?? []) walk(s, topModelInfo)
}

for (const fn of files) {
  if (count++ > FILE_CAP) break
  let data
  try {
    data = JSON.parse(fs.readFileSync(path.join(modelsDir, fn), "utf8"))
  } catch (err) {
    continue
  }
  const mi = data.model_info || {}
  for (const cat of Object.values(data.hierarchy_by_category ?? {})) {
    for (const node of cat) walk(node, mi)
  }
}

// === Print results ===

console.log(`=== Audit: params parsing ===`)
console.log(`Cache: ${cacheDir} (model-cards.json: ${modelCardsCount} cards; models/: ${files.length} files; ${totalRows} model_result rows scanned)`)
console.log()

console.log(`--- 1) Variant A input: model-cards.json.params_billions type distribution ---`)
console.log(modelCardsTypeDist)
console.log(`Variant A outputs:`, modelCardsAOutputs)
console.log()

console.log(`--- 2) Per-row model_info.additional_details.params_billions type distribution ---`)
console.log(addPbTypeDist)
console.log(`Of ${addPbTypeDist.string ?? 0} string-typed values, format distribution:`)
console.log(stringPbFormatDist)
for (const [k, exs] of Object.entries(stringPbExamples)) {
  if (exs.length === 0) continue
  console.log(`  ${k} examples: ${exs.map((e) => `'${e}'`).join(", ")}`)
}
console.log()

console.log(`--- 3) Variant D (orchestrator) fallback resolution counts ---`)
console.log(variantDFallback)
const totalResolved = Object.entries(variantDFallback)
  .filter(([k]) => k !== "noResolution")
  .reduce((s, [, v]) => s + v, 0)
const pctByPath = Object.fromEntries(
  Object.entries(variantDFallback).map(([k, v]) => [
    k,
    totalRows > 0 ? `${((v / totalRows) * 100).toFixed(1)}%` : "0%",
  ])
)
console.log(`(% of rows by path)`, pctByPath)
console.log(`Total resolved: ${totalResolved} of ${totalRows} (${((totalResolved / totalRows) * 100).toFixed(1)}%)`)
console.log()

console.log(`--- 4) Model name format distribution (drives Variant C/E/F) ---`)
console.log(nameFormatDist)
for (const [k, exs] of Object.entries(nameExamples)) {
  if (exs.length === 0) continue
  console.log(`  ${k} examples: ${exs.map((e) => `'${e}'`).join(", ")}`)
}
console.log()

console.log(`--- 5) Cross-variant agreement on model names (A/B/C/E/F applied to the name string) ---`)
console.log(nameAgreementCounts)
const totalNames = Object.values(nameAgreementCounts).reduce((s, v) => s + v, 0)
console.log(`Total names checked: ${totalNames}`)
if (totalNames > 0) {
  console.log(
    `  Convergence rate: ${((nameAgreementCounts.allConverge / totalNames) * 100).toFixed(2)}%`
  )
  console.log(
    `  Variant-C TS-quirk hit rate (context-window beats param count): ${nameAgreementCounts.cTSQuirkContextWindow} (${((nameAgreementCounts.cTSQuirkContextWindow / totalNames) * 100).toFixed(2)}%)`
  )
}

if (disagreementExamples.length > 0) {
  console.log()
  console.log(`--- Sample disagreements (up to 10) ---`)
  for (const ex of disagreementExamples) {
    console.log(`  [${ex.type}]`)
    console.log(`    name: '${ex.name}'  id: '${ex.id}'`)
    console.log(`    A=${ex.values.A}  B=${ex.values.B}  C=${ex.values.C}  E=${ex.values.E}  F=${ex.values.F}`)
  }
}

console.log()
console.log(`=== Done ===`)
