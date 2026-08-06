// Resolve the latest published warehouse snapshot URL for the v2 reader.
//
// The frontend has no built-in "latest" resolution — it consumes whatever
// SNAPSHOT_URL points at. This script provides the default: it lists the
// warehouse/ directory of the HF dataset and returns the newest snapshot.
// Snapshot dirs are named with ISO-8601 timestamps (2026-06-07T08-25-54Z), so a
// lexical sort is chronological.
//
// Usage:
//   node scripts/resolve-latest-snapshot.mjs            # prints the latest SNAPSHOT_URL
//   CARD_BACKEND_REPO=evaleval/card_backend SNAPSHOT_BRANCH=main node scripts/resolve-latest-snapshot.mjs
//
// Override the snapshot entirely by setting SNAPSHOT_URL yourself and not calling
// this — every consumer (gate, build, redirects-gen) reads SNAPSHOT_URL.
//
// Exit codes: 0 + URL on stdout; 1 on any failure (no network, empty listing).

const REPO = process.env.CARD_BACKEND_REPO || "evaleval/card_backend"
const BRANCH = process.env.SNAPSHOT_BRANCH || "main"
const ISO_DIR = /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}Z$/

const treeUrl = `https://huggingface.co/api/datasets/${REPO}/tree/${BRANCH}/warehouse`

let entries
try {
  const res = await fetch(treeUrl)
  if (!res.ok) throw new Error(`HTTP ${res.status} from ${treeUrl}`)
  entries = await res.json()
} catch (e) {
  console.error(`resolve-latest-snapshot: failed to list warehouse/ — ${e?.message ?? e}`)
  process.exit(1)
}

const snapshots = (Array.isArray(entries) ? entries : [])
  .filter((e) => e?.type === "directory")
  .map((e) => String(e.path).replace(/^warehouse\//, ""))
  .filter((name) => ISO_DIR.test(name))
  .sort()

const latest = snapshots[snapshots.length - 1]
if (!latest) {
  console.error(`resolve-latest-snapshot: no ISO-timestamped snapshot dirs under warehouse/ in ${REPO}@${BRANCH}`)
  process.exit(1)
}

process.stdout.write(`https://huggingface.co/datasets/${REPO}/resolve/${BRANCH}/warehouse/${latest}\n`)
