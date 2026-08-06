import { cachedGzipJson } from "@/lib/cached-json-response"
import { getAllBenchmarkCards } from "@/lib/benchmark-metadata"

const TTL_MS = 600_000

export async function GET(request: Request) {
  return cachedGzipJson(request, "benchmark-metadata", TTL_MS, getAllBenchmarkCards)
}
