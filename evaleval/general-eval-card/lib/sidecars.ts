import "server-only"

import { createHash } from "node:crypto"
import {
  accessSync,
  constants as fsConstants,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs"
import { mkdir, readFile, stat, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"

import type {
  BackendManifest,
  ComparisonIndex,
  CorpusAggregates,
  EvalHierarchy,
  OrgMetadata,
  OrgMetadataIndex,
  PeerRanksMap,
  PeerRanksSidecar,
} from "@/lib/backend-artifacts"
import { cleanHierarchy } from "@/lib/clean-hierarchy"

interface CacheSlot<T> {
  value: Promise<T>
  ts: number
  refresh?: Promise<void>
}

let cache: {
  manifest?: CacheSlot<BackendManifest>
  headline?: CacheSlot<CorpusAggregates>
  hierarchy?: CacheSlot<EvalHierarchy>
  comparisonIndex?: CacheSlot<ComparisonIndex>
  peerRanks?: CacheSlot<PeerRanksMap>
  organizations?: CacheSlot<Record<string, OrgMetadata>>
} = {}

function getSnapshotUrl() {
  const snapshotUrl = process.env.SNAPSHOT_URL?.trim()
  if (!snapshotUrl) {
    throw new Error("DATA_BACKEND=v2 requires SNAPSHOT_URL to point at a Stage J snapshot directory")
  }

  return snapshotUrl.replace(/\/+$/, "")
}

function sidecarUrl(name: string) {
  return `${getSnapshotUrl()}/${name}`
}

// Disk cache directory + refresh window for the multi-MB sidecar payloads.
// Next.js' built-in fetch cache rejects items over 2 MB so the 47 MB
// comparison-index / 6 MB peer-ranks / 2.5 MB hierarchy were re-fetched
// from HuggingFace on every cold start. With the disk cache, a warm
// container reads from disk (sub-second) instead of re-downloading.
//
// Once a cached payload is older than the refresh window, we keep serving that
// stale file immediately and trigger exactly one background refresh. That
// avoids putting a real user back onto the slow path just because the daily
// refresh window rolled over.
//
// Resolution order:
//   1. `SIDECAR_CACHE_DIR` env var (explicit override)
//   2. `/data/sidecars` when `/data` is writable — the HF Space mounts a
//      persistent storage bucket there, so the cache survives container
//      rebuilds (not just restarts within one container).
//   3. `<tmpdir>/eval-card-sidecars` as the local-dev / no-bucket fallback.
function resolveDiskCacheDir(): string {
  const explicit = process.env.SIDECAR_CACHE_DIR?.trim()
  if (explicit) return explicit
  try {
    accessSync("/data", fsConstants.W_OK)
    return "/data/sidecars"
  } catch {
    return join(tmpdir(), "eval-card-sidecars")
  }
}

const DISK_CACHE_DIR = resolveDiskCacheDir()
const CACHE_REFRESH_SECONDS = Number.parseInt(
  process.env.SIDECAR_CACHE_REFRESH_SECONDS ??
    process.env.SIDECAR_CACHE_TTL_SECONDS ??
    "86400",
  10,
)
const CACHE_REFRESH_MS = CACHE_REFRESH_SECONDS * 1000
const backgroundRefreshes = new Map<string, Promise<void>>()

// Identifies the deployed build. Next.js writes a fresh random
// `.next/BUILD_ID` per `next build`, so reading it gives us a value
// that changes on every HF Space rebuild but is stable across restarts
// of the same container. `SIDECAR_BUILD_ID` overrides for tests / when
// the build id needs to be forced from outside.
function readBuildId(): string {
  const explicit = process.env.SIDECAR_BUILD_ID?.trim()
  if (explicit) return explicit
  try {
    const id = readFileSync(join(process.cwd(), ".next", "BUILD_ID"), "utf8").trim()
    if (id) return id
  } catch {}
  return "dev"
}

const BUILD_ID = readBuildId()
const BUILD_MARKER_PATH = join(DISK_CACHE_DIR, ".build-id")

// Auto-purge the persistent /data/sidecars bucket whenever BUILD_ID changes.
// The bucket survives container rebuilds, so without this a rebuild would keep
// serving stale sidecars + stale cleaner output until the refresh window
// expired. Wiping on build change means: rebuild the Space -> first request
// after boot refetches everything fresh.
//
// SIDECAR_CACHE_PURGE=1 stays as a manual escape hatch (e.g. wipe without
// rebuilding when SNAPSHOT_URL is bumped at runtime).
function purgeAndStampBuild() {
  const forced = process.env.SIDECAR_CACHE_PURGE === "1"
  let prev = ""
  try {
    prev = readFileSync(BUILD_MARKER_PATH, "utf8").trim()
  } catch {}
  if (!forced && prev === BUILD_ID) return
  try {
    rmSync(DISK_CACHE_DIR, { recursive: true, force: true })
    mkdirSync(DISK_CACHE_DIR, { recursive: true })
    writeFileSync(BUILD_MARKER_PATH, BUILD_ID, "utf8")
    const reason = forced ? "SIDECAR_CACHE_PURGE=1" : `build ${prev || "<none>"} -> ${BUILD_ID}`
    console.warn(`[sidecars] purged ${DISK_CACHE_DIR} (${reason})`)
  } catch (err) {
    console.warn(`[sidecars] purge failed: ${err instanceof Error ? err.message : String(err)}`)
  }
}

purgeAndStampBuild()

function diskCachePath(url: string): string {
  // The path encodes the URL hash so swapping SNAPSHOT_URL doesn't collide
  // with the previous snapshot's cached payloads.
  const hash = createHash("sha1").update(url).digest("hex").slice(0, 16)
  const safeName = url.split("/").slice(-1)[0]?.replace(/[^a-zA-Z0-9._-]/g, "_") ?? "sidecar"
  return join(DISK_CACHE_DIR, `${hash}-${safeName}`)
}

async function readFromDisk(path: string): Promise<{ text: string | null; stale: boolean }> {
  try {
    const info = await stat(path)
    const text = await readFile(path, "utf8")
    return {
      text,
      stale: Date.now() - info.mtimeMs > CACHE_REFRESH_MS,
    }
  } catch {
    return { text: null, stale: false }
  }
}

async function writeToDisk(path: string, payload: string): Promise<void> {
  try {
    await mkdir(DISK_CACHE_DIR, { recursive: true })
    const tmpPath = `${path}.${process.pid}.${Date.now()}.tmp`
    await writeFile(tmpPath, payload, "utf8")
    const fs = await import("node:fs/promises")
    await fs.rename(tmpPath, path)
  } catch (err) {
    console.warn(`[sidecars] failed to write disk cache ${path}: ${err instanceof Error ? err.message : String(err)}`)
  }
}

async function fetchRemoteSidecar(url: string): Promise<string> {
  const response = await fetch(url, { next: { revalidate: CACHE_REFRESH_SECONDS } })
  if (!response.ok) {
    throw new Error(`Snapshot sidecar fetch failed: ${response.status} ${response.statusText} for ${url}`)
  }
  return response.text()
}

function queueRefresh(refreshKey: string, label: string, refresh: () => Promise<void>) {
  if (backgroundRefreshes.has(refreshKey)) {
    return
  }

  const refreshPromise = refresh()
    .catch((err) => {
      console.warn(
        `[sidecars] background refresh failed for ${label}: ${err instanceof Error ? err.message : String(err)}`,
      )
    })
    .finally(() => {
      backgroundRefreshes.delete(refreshKey)
    })

  backgroundRefreshes.set(refreshKey, refreshPromise)
}

async function fetchJson<T>(name: string, preferStale = true): Promise<T> {
  const url = sidecarUrl(name)

  if (url.startsWith("file://")) {
    const text = await readFile(new URL(url), "utf8")
    return JSON.parse(text) as T
  }

  const cachePath = diskCachePath(url)
  const cached = await readFromDisk(cachePath)
  if (cached.text !== null) {
    if (preferStale) {
      if (cached.stale) {
        queueRefresh(cachePath, name, async () => {
          const text = await fetchRemoteSidecar(url)
          await writeToDisk(cachePath, text)
        })
      }
      return JSON.parse(cached.text) as T
    }

    if (!cached.stale) {
      return JSON.parse(cached.text) as T
    }
  }

  const text = await fetchRemoteSidecar(url)
  void writeToDisk(cachePath, text)
  return JSON.parse(text) as T
}

function getCachedValue<K extends keyof typeof cache>(
  key: K,
  label: string,
  loader: (preferStale?: boolean) => Promise<NonNullable<(typeof cache)[K]> extends CacheSlot<infer T> ? T : never>,
): NonNullable<(typeof cache)[K]> extends CacheSlot<infer T> ? Promise<T> : never {
  type Value = NonNullable<(typeof cache)[K]> extends CacheSlot<infer T> ? T : never

  const existing = cache[key] as CacheSlot<Value> | undefined
  if (!existing) {
    const slot = {} as CacheSlot<Value>
    slot.ts = Date.now()
    slot.value = loader(true).catch((err) => {
      if (cache[key] === slot) {
        delete cache[key]
      }
      throw err
    })
    cache[key] = slot as (typeof cache)[K]
    return slot.value as NonNullable<(typeof cache)[K]> extends CacheSlot<infer T> ? Promise<T> : never
  }

  if (Date.now() - existing.ts >= CACHE_REFRESH_MS && !existing.refresh) {
    existing.refresh = (async () => {
      try {
        const freshValue = await loader(false)
        existing.value = Promise.resolve(freshValue)
        existing.ts = Date.now()
      } catch (err) {
        console.warn(
          `[sidecars] in-memory refresh failed for ${label}: ${err instanceof Error ? err.message : String(err)}`,
        )
      } finally {
        existing.refresh = undefined
      }
    })()
  }

  return existing.value as NonNullable<(typeof cache)[K]> extends CacheSlot<infer T> ? Promise<T> : never
}

async function fetchFreshComparisonIndexForCleaner(): Promise<ComparisonIndex | null> {
  try {
    const index = await fetchJson<ComparisonIndex>("comparison-index.json", false)
    assertComparisonIndexShape(index)
    return index
  } catch (err) {
    console.warn(
      `[sidecars] comparison-index unavailable; cleaner will skip aggregator dedup. ${err instanceof Error ? err.message : String(err)}`,
    )
    return null
  }
}

async function buildCleanedHierarchy(): Promise<EvalHierarchy> {
  const [raw, comparisonIndex] = await Promise.all([
    fetchJson<EvalHierarchy>("hierarchy.json", false),
    fetchFreshComparisonIndexForCleaner(),
  ])
  return cleanHierarchy(raw, comparisonIndex)
}

async function fetchCleanedHierarchy(preferStale = true): Promise<EvalHierarchy> {
  const snapshotUrl = getSnapshotUrl()
  const cleanCachePath = diskCachePath(`${snapshotUrl}/clean-hierarchy.json`)
  const cached = await readFromDisk(cleanCachePath)

  if (cached.text !== null) {
    try {
      const parsed = JSON.parse(cached.text) as EvalHierarchy
      if (preferStale && cached.stale) {
        queueRefresh(cleanCachePath, "clean-hierarchy.json", async () => {
          const cleaned = await buildCleanedHierarchy()
          await writeToDisk(cleanCachePath, JSON.stringify(cleaned))
        })
      }
      if (preferStale || !cached.stale) {
        return parsed
      }
    } catch (err) {
      console.warn(
        `[sidecars] clean-hierarchy cache corrupt at ${cleanCachePath}; rebuilding. ${err instanceof Error ? err.message : String(err)}`,
      )
    }
  }

  const cleaned = await buildCleanedHierarchy()
  void writeToDisk(cleanCachePath, JSON.stringify(cleaned))
  return cleaned
}

export function fetchManifest(): Promise<BackendManifest> {
  return getCachedValue("manifest", "manifest", (preferStale) => fetchJson<BackendManifest>("manifest.json", preferStale))
}

export function fetchHeadline(): Promise<CorpusAggregates> {
  return getCachedValue("headline", "headline", (preferStale) => fetchJson<CorpusAggregates>("headline.json", preferStale))
}

/**
 * Returns the cleaned hierarchy used by the rest of the app — sanitised
 * display names, populated `derivedTags`, filtered `benchmark_index[]`.
 *
 * Disk cache layout: distinct from the raw `hierarchy.json` cache so the
 * cleaner runs at most once per snapshot. On a cold container we hit the
 * clean cache first; once it is older than the refresh window we keep serving
 * it immediately and rebuild in the background.
 */
export function fetchHierarchy(): Promise<EvalHierarchy> {
  return getCachedValue("hierarchy", "hierarchy", (preferStale) => fetchCleanedHierarchy(preferStale))
}

/** Per-model cleaned benchmark count from the hierarchy payload.
 *  Returns an empty map when the hierarchy was loaded without a
 *  comparison-index (e.g. old cached v10 blobs). */
export async function fetchModelCoverage(): Promise<Record<string, number>> {
  const h = await fetchHierarchy()
  return h._modelCoverageMap ?? {}
}

export function fetchComparisonIndex(): Promise<ComparisonIndex> {
  return getCachedValue("comparisonIndex", "comparison index", (preferStale) =>
    fetchJson<ComparisonIndex>("comparison-index.json", preferStale).then((index) => {
      assertComparisonIndexShape(index)
      return index
    }),
  )
}

/**
 * Per-(eval, model) primary-metric peer ranks from
 * `warehouse/<snapshot>/peer-ranks.json`. Resolves to the bare
 * `eval_summary_id -> model_route_id -> {position, total}` map the
 * model-detail benchmark grid expects, so callers don't have to reach
 * into `.ranks` themselves.
 *
 * Returns an empty map if the snapshot doesn't carry the file yet — the
 * producer started emitting it as a Stage J sidecar in May 2026, so older
 * pinned snapshots may 404. Logs a warning in that case rather than throwing
 * so the rest of the page still renders.
 */
export function fetchPeerRanks(): Promise<PeerRanksMap> {
  return getCachedValue("peerRanks", "peer ranks", (preferStale) =>
    fetchJson<PeerRanksSidecar>("peer-ranks.json", preferStale)
      .then((payload) => payload?.ranks ?? {})
      .catch((err) => {
        console.warn(
          `[sidecars] peer-ranks.json not available on snapshot; ` +
            `falling back to empty map. ${err instanceof Error ? err.message : String(err)}`,
        )
        return {} as PeerRanksMap
      }),
  )
}

/**
 * Per-evaluator-org metadata (homepage URL + logo pointer) from
 * `warehouse/<snapshot>/organizations.json`, sourced from the registry.
 * Resolves to the bare `normalizedName -> OrgMetadata` map the evaluator page
 * looks up by name.
 *
 * Returns an empty map when the snapshot doesn't carry the file (older pinned
 * snapshots predate the Stage J `organizations` sidecar), logging a warning
 * rather than throwing so the page still renders with monograms + no links.
 */
export function fetchOrganizations(): Promise<Record<string, OrgMetadata>> {
  return getCachedValue("organizations", "organizations", (preferStale) =>
    fetchJson<OrgMetadataIndex>("organizations.json", preferStale)
      .then((payload) => payload?.orgs ?? {})
      .catch((err) => {
        console.warn(
          `[sidecars] organizations.json not available on snapshot; ` +
            `falling back to empty map. ${err instanceof Error ? err.message : String(err)}`,
        )
        return {} as Record<string, OrgMetadata>
      }),
  )
}

/**
 * Fail fast on contract regressions. Comparison-index rows must carry
 * `family_id`; the model-page graph view collapses without it.
 */
export function assertComparisonIndexShape(index: ComparisonIndex): void {
  for (const [evalId, entry] of Object.entries(index.evals ?? {})) {
    if (!Object.prototype.hasOwnProperty.call(entry, "family_id")) {
      throw new Error(
        `comparison-index contract regression: evals[${evalId}] is missing family_id.`,
      )
    }
  }
}

export function resetSidecarCacheForTests() {
  cache = {}
  backgroundRefreshes.clear()
}
