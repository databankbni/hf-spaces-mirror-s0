import { cachedGzipJson } from "@/lib/cached-json-response"
import { getEvalHierarchyData } from "@/lib/data-backend"

const TTL_MS = 600_000

export async function GET(request: Request) {
  return cachedGzipJson(request, "eval-hierarchy", TTL_MS, getEvalHierarchyData)
}
