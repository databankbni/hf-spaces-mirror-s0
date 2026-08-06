"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import { BenchmarkDetail } from "@/components/benchmark-detail"
import {
  fetchBenchmarkMetadata,
  fetchComparisonIndex,
  fetchEvalHierarchy,
  fetchModelSummary,
} from "@/lib/dashboard-data-client"
import { routeIdFromSegments } from "@/lib/utils"
import type { BenchmarkCard } from "@/lib/benchmark-schema"
import type { ComparisonIndex, EvalHierarchy } from "@/lib/backend-artifacts"

/**
 * Embed-only render of a model's Summary §4 reported-metrics list.
 * Reuses <BenchmarkDetail> with embedSurface="reported-metrics" so the
 * whole grouping / category-filter / rank-badge pipeline stays in one
 * place — the embed just hides everything else.
 */
export default function EmbedModelReportedMetrics() {
  const params = useParams()
  const routeId = routeIdFromSegments(params.id)
  const [summary, setSummary] = useState<Awaited<ReturnType<typeof fetchModelSummary>> | null>(null)
  const [benchmarkCards, setBenchmarkCards] = useState<Record<string, BenchmarkCard>>({})
  const [evalHierarchy, setEvalHierarchy] = useState<EvalHierarchy | null>(null)
  const [comparisonIndex, setComparisonIndex] = useState<ComparisonIndex | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([
      fetchModelSummary(routeId),
      fetchBenchmarkMetadata(),
      fetchEvalHierarchy().catch(() => null),
    ])
      .then(([modelSummary, cards, hierarchy]) => {
        if (cancelled) return
        setSummary(modelSummary)
        setBenchmarkCards(cards)
        setEvalHierarchy(hierarchy)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      })

    fetchComparisonIndex()
      .then((idx) => {
        if (!cancelled) setComparisonIndex(idx)
      })
      .catch(() => {})

    return () => {
      cancelled = true
    }
  }, [routeId])

  if (error) {
    return (
      <div className="font-mono" style={{ fontSize: 12, color: "var(--fg-muted)" }}>
        Failed to load model: {error}
      </div>
    )
  }
  if (!summary) {
    return (
      <div
        className="font-mono uppercase"
        style={{ fontSize: 10, letterSpacing: "0.18em", color: "var(--fg-subtle)" }}
      >
        Loading…
      </div>
    )
  }

  return (
    <BenchmarkDetail
      summary={summary}
      benchmarkCards={benchmarkCards}
      evalHierarchy={evalHierarchy}
      comparisonIndex={comparisonIndex}
      embedSurface="reported-metrics"
    />
  )
}
