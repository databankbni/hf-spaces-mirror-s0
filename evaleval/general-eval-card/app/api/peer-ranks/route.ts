import { cachedGzipJson } from "@/lib/cached-json-response"
import { fetchPeerRanks } from "@/lib/hf-data"

const TTL_MS = 600_000

export async function GET(request: Request) {
  return cachedGzipJson(request, "peer-ranks", TTL_MS, fetchPeerRanks)
}
