import "server-only"

import type { BenchmarkCard } from "@/lib/benchmark-schema"
import { candidateBenchmarkKeys as candidateKeys, normalizeBenchmarkKey } from "@/lib/benchmark-metadata-utils"
import { fetchBenchmarkMetadataMap } from "@/lib/hf-data"

export { normalizeBenchmarkKey }

let cachedMapPromise: Promise<Map<string, BenchmarkCard>> | null = null

async function readPipelineBenchmarkCards(): Promise<Map<string, BenchmarkCard>> {
  const cards = await fetchBenchmarkMetadataMap()
  const map = new Map<string, BenchmarkCard>()

  for (const card of Object.values(cards)) {
    if (!card?.benchmark_details?.name) {
      continue
    }

    for (const key of candidateKeys(card.benchmark_details.name)) {
      if (!map.has(key)) {
        map.set(key, card)
      }
    }
  }

  return map
}

function getMap(): Promise<Map<string, BenchmarkCard>> {
  if (!cachedMapPromise) {
    cachedMapPromise = readPipelineBenchmarkCards()
  }

  return cachedMapPromise
}

export async function getBenchmarkCard(benchmarkName: string): Promise<BenchmarkCard | null> {
  const map = await getMap()

  for (const key of candidateKeys(benchmarkName)) {
    const card = map.get(key)
    if (card) {
      return card
    }
  }

  return null
}

export async function getAllBenchmarkCards(): Promise<Record<string, BenchmarkCard>> {
  const map = await getMap()
  const seen = new Set<BenchmarkCard>()
  const result: Record<string, BenchmarkCard> = {}

  for (const card of map.values()) {
    if (seen.has(card)) {
      continue
    }

    seen.add(card)
    result[normalizeBenchmarkKey(card.benchmark_details.name)] = card
  }

  return result
}
