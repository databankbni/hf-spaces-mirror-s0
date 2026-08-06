import { NextResponse } from "next/server"

import { fetchModelDetail } from "@/lib/hf-data"

/**
 * Lightweight lookup that returns the per-(model, benchmark) reproducibility
 * payload — generation_config + sample_size/standard_error/confidence_interval
 * — extracted from the model's full record. Used by the leaderboard's
 * Reproducibility card on row expand so we avoid joining N model files into
 * the eval-detail page on every load.
 */
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const modelId = searchParams.get("model_id")
  const benchmarkKey = (searchParams.get("benchmark_key") || "").toLowerCase()
  const evalName = (searchParams.get("eval_name") || "").toLowerCase()

  if (!modelId) {
    return NextResponse.json({ error: "Missing model_id" }, { status: 400 })
  }

  const slug = modelId.replace(/[\/]/g, "__")
  const detail = await fetchModelDetail(slug)
  if (!detail) {
    return NextResponse.json({ generation_config: null, score_details: null }, { status: 200 })
  }

  let bestGenerationConfig: unknown = null
  let bestScoreDetails: unknown = null

  const candidates = Object.values(detail.evaluations_by_category ?? {}).flat()
  for (const ev of candidates) {
    const evBench = ((ev.benchmark as string | undefined) ?? "").toLowerCase()
    for (const r of ev.evaluation_results ?? []) {
      const rName = (r.evaluation_name ?? "").toLowerCase()
      const rDisplay = (r.display_name ?? "").toLowerCase()
      const matches =
        (benchmarkKey && (evBench === benchmarkKey || evBench.includes(benchmarkKey) || rName.includes(benchmarkKey))) ||
        (evalName && (rName === evalName || rDisplay === evalName))
      if (!matches) continue

      const candidateGen = ev.generation_config ?? r.generation_config
      const argsCount =
        candidateGen && typeof candidateGen === "object" && "generation_args" in candidateGen
          ? Object.keys((candidateGen as { generation_args?: Record<string, unknown> }).generation_args ?? {}).length
          : 0
      const currentCount =
        bestGenerationConfig && typeof bestGenerationConfig === "object" && "generation_args" in bestGenerationConfig
          ? Object.keys((bestGenerationConfig as { generation_args?: Record<string, unknown> }).generation_args ?? {}).length
          : 0
      if (candidateGen && argsCount > currentCount) {
        bestGenerationConfig = candidateGen
      }
      if (!bestScoreDetails && r.score_details) {
        bestScoreDetails = r.score_details
      }
    }
    if (bestGenerationConfig && bestScoreDetails) break
  }

  return NextResponse.json({
    generation_config: bestGenerationConfig,
    score_details: bestScoreDetails,
  })
}
