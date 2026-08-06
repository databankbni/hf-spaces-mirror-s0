import "./server-only-shim.mjs"
import fs from "fs"

// Replicate shortenLicense from components/eval-card.tsx:38-48 verbatim.
// Pipeline must produce identical outputs for every license string.
function shortenLicense(license) {
  if (!license || license === "Not specified") return ""
  if (license.toLowerCase().includes("creative commons attribution 4")) return "CC BY 4.0"
  if (license.toLowerCase().includes("creative commons zero")) return "CC0"
  if (license.toLowerCase().includes("apache license 2") || license.toLowerCase().includes("apache 2")) return "Apache 2.0"
  if (license.toLowerCase().includes("mit license")) return "MIT"
  if (license.toLowerCase().includes("cc-by-sa")) return "CC BY-SA"
  if (license.length > 24) return license.slice(0, 22) + "…"
  return license
}

// === Audit 1: distinct license strings + their shortened form ===
const cardsByName = JSON.parse(fs.readFileSync(".cache/hf-data/benchmark-metadata.json", "utf8"))
const cards = Array.isArray(cardsByName) ? cardsByName : Object.values(cardsByName)

const licenseStrings = new Map()
const shortenedDistribution = new Map()
let cardsWithLicense = 0
let cardsTotal = 0

for (const c of cards) {
  cardsTotal++
  const license = c?.ethical_and_legal_considerations?.data_licensing
  if (!license) continue
  cardsWithLicense++
  const lic = String(license)
  licenseStrings.set(lic, (licenseStrings.get(lic) ?? 0) + 1)
  const short = shortenLicense(lic)
  shortenedDistribution.set(short, (shortenedDistribution.get(short) ?? 0) + 1)
}

console.log(`=== Audit 1: distinct license strings (${cardsWithLicense}/${cardsTotal} benchmark cards have a license) ===`)
console.log(`Distinct raw license strings: ${licenseStrings.size}`)
console.log("Top 30 raw → shortened:")
const rows = [...licenseStrings.entries()].sort((a, b) => b[1] - a[1]).slice(0, 30)
for (const [raw, n] of rows) {
  const short = shortenLicense(raw)
  const truncMarker = short.endsWith("…") ? " (truncated)" : ""
  const matchedRule = (() => {
    const l = raw.toLowerCase()
    if (l.includes("creative commons attribution 4")) return "CC BY 4.0 rule"
    if (l.includes("creative commons zero")) return "CC0 rule"
    if (l.includes("apache license 2") || l.includes("apache 2")) return "Apache 2.0 rule"
    if (l.includes("mit license")) return "MIT rule"
    if (l.includes("cc-by-sa")) return "CC BY-SA rule"
    if (raw.length > 24) return "truncate-22 rule"
    return "passthrough"
  })()
  console.log(`  ${n.toString().padStart(3)}× '${raw}' → '${short}' [${matchedRule}]${truncMarker}`)
}

console.log(`\n=== Audit 2: shortened distribution ===`)
for (const [short, n] of [...shortenedDistribution.entries()].sort((a, b) => b[1] - a[1])) {
  console.log(`  ${n.toString().padStart(3)}× '${short}'`)
}

console.log(`\n=== Audit 3: rule-coverage stats ===`)
let counts = { ccby4: 0, cc0: 0, apache2: 0, mit: 0, ccbysa: 0, truncated: 0, passthrough: 0, empty: 0 }
for (const [raw, n] of licenseStrings.entries()) {
  const l = raw.toLowerCase()
  if (!raw || raw === "Not specified") counts.empty += n
  else if (l.includes("creative commons attribution 4")) counts.ccby4 += n
  else if (l.includes("creative commons zero")) counts.cc0 += n
  else if (l.includes("apache license 2") || l.includes("apache 2")) counts.apache2 += n
  else if (l.includes("mit license")) counts.mit += n
  else if (l.includes("cc-by-sa")) counts.ccbysa += n
  else if (raw.length > 24) counts.truncated += n
  else counts.passthrough += n
}
console.log(counts)
