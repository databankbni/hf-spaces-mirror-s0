"use client"

import { useEffect, useMemo, useState } from "react"
import { useParams, useSearchParams } from "next/navigation"
import { ScoreDistribution } from "@/components/score-distribution"
import { fetchEvalSummary } from "@/lib/dashboard-data-client"
import {
  buildDistributionSeries,
  buildDistributionSliceAxis,
} from "@/lib/distribution-series"
import { routeIdFromSegments } from "@/lib/utils"
import type { BenchmarkEvalSummary } from "@/lib/eval-processing"

/**
 * Embed-only render of the score-distribution histogram for one eval.
 * Designed for iframes: no nav, no audience bar, no surrounding chrome.
 *
 * Slice-aware: when the eval has subtask slices (e.g. Global MMLU's
 * per-language splits), this page renders a SPLIT dropdown above the
 * plot so the embedded viewer can switch slices the same way the parent
 * eval page does. When there's no slice axis, falls back to building
 * one series per metric (e.g. agentharm's per-category histogram).
 *
 * Query params:
 *   ?view=distribution (default) — lock to distribution, hide toggle
 *   ?view=frontier              — lock to frontier, hide toggle
 *   ?view=both                  — show the Distribution/Frontier toggle
 *   ?slice=<subtask_key>        — start with this slice selected
 */
export default function EmbedEvalDistribution() {
  const params = useParams()
  const searchParams = useSearchParams()
  const evalId = routeIdFromSegments(params.id)
  const viewParam = (searchParams.get("view") || "distribution").toLowerCase()
  const sliceParam = searchParams.get("slice")
  const showToggle = viewParam === "both"
  const defaultView: "distribution" | "frontier" =
    viewParam === "frontier" ? "frontier" : "distribution"

  const [summary, setSummary] = useState<BenchmarkEvalSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchEvalSummary(evalId)
      .then((s) => {
        if (!cancelled) setSummary(s)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      })
    return () => {
      cancelled = true
    }
  }, [evalId])

  // Slice axis — present when the eval has multiple subtask-scope metrics
  // sharing a primary root metric (e.g. Global MMLU's 24 language splits).
  const sliceAxis = useMemo(
    () => (summary ? buildDistributionSliceAxis(summary) : null),
    [summary],
  )

  const ALL_SLICE_KEY = "__all__"
  const [activeSlice, setActiveSlice] = useState<string>(() => {
    if (sliceParam && sliceParam.trim()) return sliceParam.trim()
    return ALL_SLICE_KEY
  })
  // If the URL named a slice the eval doesn't carry, fall back to Overall
  // once the summary loads.
  useEffect(() => {
    if (!sliceAxis) return
    if (activeSlice === ALL_SLICE_KEY) return
    if (!sliceAxis.slices.some((s) => s.key === activeSlice)) {
      setActiveSlice(ALL_SLICE_KEY)
    }
  }, [activeSlice, sliceAxis])

  const series = useMemo(
    () => (summary ? buildDistributionSeries(summary, sliceAxis, activeSlice, ALL_SLICE_KEY) : null),
    [summary, sliceAxis, activeSlice],
  )

  if (error) {
    return (
      <div className="font-mono" style={{ fontSize: 12, color: "var(--fg-muted)" }}>
        Failed to load: {error}
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
  if (!series) {
    return (
      <div className="font-mono" style={{ fontSize: 12, color: "var(--fg-muted)" }}>
        No score data available for this evaluation yet.
      </div>
    )
  }

  return (
    <div>
      <div className="mb-3">
        <div
          className="font-mono uppercase"
          style={{ fontSize: 10, letterSpacing: "0.14em", color: "var(--fg-subtle)" }}
        >
          {defaultView === "frontier" ? "Pareto frontier" : "Score distribution"}
        </div>
        <div
          style={{
            fontSize: 19,
            fontWeight: 700,
            letterSpacing: "-0.02em",
            lineHeight: 1.2,
            color: "var(--fg)",
            marginTop: 2,
          }}
        >
          {summary.evaluation_name}
        </div>
      </div>
      {sliceAxis && (
        <div className="mb-3 flex items-center gap-3">
          <span
            className="font-mono uppercase shrink-0"
            style={{ fontSize: 10, letterSpacing: "0.14em", color: "var(--fg-subtle)" }}
          >
            Split
          </span>
          <select
            className="ec-select"
            value={activeSlice}
            onChange={(e) => setActiveSlice(e.target.value)}
          >
            <option value={ALL_SLICE_KEY}>Overall</option>
            {sliceAxis.slices.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
      )}
      <ScoreDistribution
        series={series}
        defaultView={defaultView}
        showViewToggle={showToggle}
      />
    </div>
  )
}
