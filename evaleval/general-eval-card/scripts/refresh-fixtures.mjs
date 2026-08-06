#!/usr/bin/env node
// Refresh tests/fixtures/{evals,models,developers}/ from .cache/hf-data/.
// Reads tests/fixtures/manifest.json for the curated ID list, copies each
// referenced file from the live cache, and bumps manifest.snapshot_ts.
//
// Workflow: pnpm refresh-fixtures → git diff tests/fixtures/ → review what
// upstream changed → pnpm test → if snapshots diff, decide intent → commit.
//
// Always re-pin everything (no incremental) so the snapshot is internally
// consistent. If the cache lacks a referenced file, fail loudly — most likely
// the manifest references a stale ID and either it should be updated or the
// cache is incomplete.

import { promises as fs } from "fs"
import path from "path"

const ROOT = path.resolve(import.meta.dirname, "..")
const CACHE = path.join(ROOT, ".cache", "hf-data")
const FIXTURES = path.join(ROOT, "tests", "fixtures")
const MANIFEST = path.join(FIXTURES, "manifest.json")

const manifest = JSON.parse(await fs.readFile(MANIFEST, "utf8"))
const sourceDir = path.resolve(ROOT, manifest.snapshot_source ?? ".cache/hf-data")
if (sourceDir !== CACHE) {
  console.warn(`Note: manifest.snapshot_source = ${manifest.snapshot_source}, resolving to ${sourceDir}`)
}

await fs.access(sourceDir).catch(() => {
  throw new Error(`Cache directory ${sourceDir} not found. Run \`pnpm cache-hf-data\` first.`)
})

let copied = 0
let removed = 0
const errors = []

// Detail files: copy whole file from cache subdirectory.
for (const [groupName, dirName] of [["evals", "evals"], ["models", "models"], ["developers", "developers"]]) {
  const entries = manifest[groupName] ?? []
  const targetDir = path.join(FIXTURES, dirName)
  await fs.mkdir(targetDir, { recursive: true })

  // Pin: only files in the manifest survive in tests/fixtures/<dir>/
  const wanted = new Set(entries.map((entry) => `${entry.id}.json`))
  const existing = await fs.readdir(targetDir).catch(() => [])
  for (const file of existing) {
    if (!wanted.has(file)) {
      await fs.unlink(path.join(targetDir, file))
      removed += 1
    }
  }

  for (const entry of entries) {
    const fileName = `${entry.id}.json`
    const src = path.join(sourceDir, dirName, fileName)
    const dst = path.join(targetDir, fileName)
    try {
      await fs.copyFile(src, dst)
      copied += 1
    } catch (err) {
      errors.push({ group: groupName, id: entry.id, error: err instanceof Error ? err.message : String(err) })
    }
  }
}

// model_cards: extract individual entries from model-cards.json (the flat list).
const modelCardsManifest = manifest.model_cards ?? []
if (modelCardsManifest.length > 0) {
  const targetDir = path.join(FIXTURES, "model-cards")
  await fs.mkdir(targetDir, { recursive: true })
  const wanted = new Set(modelCardsManifest.map((entry) => `${entry.id}.json`))
  const existing = await fs.readdir(targetDir).catch(() => [])
  for (const file of existing) {
    if (!wanted.has(file)) {
      await fs.unlink(path.join(targetDir, file))
      removed += 1
    }
  }

  const allCards = JSON.parse(await fs.readFile(path.join(sourceDir, "model-cards.json"), "utf8"))
  const byRouteId = new Map(allCards.map((card) => [card.model_route_id, card]))

  for (const entry of modelCardsManifest) {
    const card = byRouteId.get(entry.id)
    if (!card) {
      errors.push({ group: "model_cards", id: entry.id, error: "model_route_id not found in model-cards.json" })
      continue
    }
    const dst = path.join(targetDir, `${entry.id}.json`)
    await fs.writeFile(dst, `${JSON.stringify(card, null, 2)}\n`)
    copied += 1
  }
}

if (errors.length > 0) {
  console.error("Failed to copy the following fixtures (likely missing from local cache):")
  for (const { group, id, error } of errors) {
    console.error(`  ${group}/${id}: ${error}`)
  }
  process.exit(1)
}

const updatedManifest = {
  ...manifest,
  snapshot_ts: new Date().toISOString(),
}
await fs.writeFile(MANIFEST, `${JSON.stringify(updatedManifest, null, 2)}\n`)

console.log(`Refreshed ${copied} fixture(s) from ${sourceDir} (removed ${removed} stale).`)
console.log(`snapshot_ts → ${updatedManifest.snapshot_ts}`)
console.log("\nNext: review `git diff tests/fixtures/`, run `pnpm test`, update snapshots with `pnpm test -- -u` if intentional.")
