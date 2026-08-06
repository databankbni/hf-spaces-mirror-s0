import { cachedGzipJson } from "@/lib/cached-json-response"
import { fetchComparisonIndex } from "@/lib/hf-data"

// ~20 MB recomputed per pipeline run, previously shipped RAW on every detail page.
// Gzip (~13x smaller) + per-process memoize with an ETag/304; immutable per
// snapshot so the 10-min TTL is safe. Same helper as the /models, /evals index routes.
const TTL_MS = 600_000

export async function GET(request: Request) {
  return cachedGzipJson(request, "comparison-index", TTL_MS, fetchComparisonIndex)
}
