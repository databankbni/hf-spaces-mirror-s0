import { describe, expect, it } from "vitest"

import {
  buildDistributionSeries,
  buildDistributionSliceAxis,
} from "@/lib/distribution-series"
import type { BenchmarkEvalSummary } from "@/lib/eval-processing"
import fixtures from "./fixtures/distribution-eval-summaries.json"

// Fixtures are trimmed real payloads captured from the live
// /api/eval-summary route (evalcards.evalevalai.com), so these assertions
// exercise the actual deployed data shape, not a hand-built mock.
const ALL = "__all__"
const summaryOf = (k: keyof typeof fixtures) =>
  fixtures[k] as unknown as BenchmarkEvalSummary

describe("buildDistributionSeries — metric chip selection", () => {
  it("vals-ai/math-500: collapses the redundant self-slice subtask to a single Accuracy chip", () => {
    const summary = summaryOf("math500")
    // The live payload carries two metrics with the same metric_summary_id:
    // root `accuracy` + subtask `accuracy::vals ai math500`. The subtask is a
    // self-slice (its key is just the slugified eval), so it must NOT become a
    // second chip.
    expect((summary.leaderboard_metrics ?? []).map((m) => m.scope).sort()).toEqual([
      "root",
      "subtask",
    ])
    const sliceAxis = buildDistributionSliceAxis(summary)
    // A lone self-slice is not a real slice axis.
    expect(sliceAxis).toBeNull()
    const series = buildDistributionSeries(summary, sliceAxis, ALL, ALL)
    expect(series).not.toBeNull()
    expect(series!.length).toBe(1)
    expect(series![0].label).toBe("Accuracy")
  })

  it("agentharm: keeps every distinct root metric (multi-metric embed unbroken)", () => {
    const summary = summaryOf("agentharm")
    const rootCount = (summary.leaderboard_metrics ?? []).filter(
      (m) => m.scope !== "subtask",
    ).length
    expect(rootCount).toBeGreaterThan(1)
    const sliceAxis = buildDistributionSliceAxis(summary)
    const series = buildDistributionSeries(summary, sliceAxis, ALL, ALL)
    expect(series).not.toBeNull()
    expect(series!.length).toBe(rootCount)
    // No two chips share a label (the duplication the fix targets).
    const labels = series!.map((s) => s.label)
    expect(new Set(labels).size).toBe(labels.length)
  })
})
