import { NextResponse } from "next/server"

import { getEvalHierarchyData } from "@/lib/data-backend"
import { fetchCorpusAggregates } from "@/lib/hf-data"

export async function GET() {
  const [aggregates, hierarchy] = await Promise.all([
    fetchCorpusAggregates(),
    getEvalHierarchyData().catch(() => null),
  ])

  if (!aggregates) {
    return NextResponse.json(
      { error: "Corpus aggregates not available" },
      { status: 404 }
    )
  }

  // Overlay `total_benchmarks` with the cleaned hierarchy's benchmark
  // count so the /models denominator matches the per-row numerator
  // (which the model-cards endpoint already serves cleaned). The landing
  // page reads `stats.benchmark_count` directly off the hierarchy and
  // gets the right number; this brings corpus-aggregates consumers onto
  // the same surface. Falls back to the producer's raw value if the
  // cleaner couldn't run (e.g. v1 backend).
  const cleanedTotal = hierarchy?.stats?.benchmark_count
  const merged =
    typeof cleanedTotal === "number" && cleanedTotal > 0
      ? { ...aggregates, total_benchmarks: cleanedTotal }
      : aggregates

  return NextResponse.json(merged, {
    headers: {
      "Cache-Control": "public, max-age=600, stale-while-revalidate=3600",
    },
  })
}
