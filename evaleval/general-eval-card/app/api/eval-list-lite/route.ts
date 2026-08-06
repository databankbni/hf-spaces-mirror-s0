import { getEvalListLiteData } from "@/lib/data-backend"
import { cachedGzipJson } from "@/lib/cached-json-response"

// 10-minute in-process TTL; warm-startup-cache primes this at boot so the
// first real visit to /evals gets the cached, gzipped payload.
const TTL_MS = 600_000

export async function GET(request: Request) {
  return cachedGzipJson(request, "eval-list-lite", TTL_MS, getEvalListLiteData)
}
