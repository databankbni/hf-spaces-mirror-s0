// Cross-suite overlaps data layer for the model detail page.
//
// Builds one row per canonical benchmark from two populations:
//   (a) `benchmark_index[]` entries (already pre-filtered by `cleanHierarchy`
//       to canonicals appearing in ≥2 distinct families), resolving this
//       model's score in each appearance via `comparisonIndex`;
//   (b) the model's own summary benchmark groups for benchmarks that have no
//       benchmark_index entry (single family globally), merged in as
//       one-appearance rows when not already represented.
// Rows aggregate per canonical with mean, SD, and 95% CI from Student's-t
// (df=N-1). N=2 widths are very wide on purpose: with two samples we
// genuinely don't know the spread, and surfacing that beats fake precision.
// Single-appearance rows carry degenerate stats (stddev 0, no CI).

import type {
  BenchmarkIndexEntry,
  ComparisonIndex,
  ComparisonMetricEntry,
  ComparisonScoreEntry,
  RowAnnotations,
} from "./backend-artifacts"

export type OverlapSourceKind = "comparison-index" | "summary"

export interface OverlapAppearance {
  familyKey: string
  familyName: string
  evalSummaryId: string
  metricSummaryId: string
  metricName: string
  score: number
  displayScore: string
  unit: string | null
  temperature?: number | null
  maxTokens?: number | null
  annotations?: RowAnnotations | null
  /** "comparison-index" appearances have a per-eval leaderboard to link to;
   *  "summary" appearances come from the model's own result rows and don't. */
  sourceKind: OverlapSourceKind
}

export interface OverlapRow {
  canonicalKey: string
  canonicalDisplayName: string
  appearances: OverlapAppearance[]
  mean: number
  stddev: number
  min: number
  max: number
  ci95: { low: number; high: number } | null
  /** Tagged 0-1 (proportion) vs 0-100 (percent) — drives display. */
  isPercentScale: boolean
}

/** One of the current model's own result rows, keyed by eval_summary_id.
 *  Used to backfill generation params / annotations onto comparison-index
 *  appearances whose score cells don't carry them (pre-regen snapshots). */
export interface OverlapSummaryJoinRow {
  evalSummaryId: string
  temperature: number | null
  maxTokens: number | null
  annotations: RowAnnotations | null
}

/** A benchmark group from the model's own summary payload — the merge input
 *  for benchmarks without a benchmark_index entry. Carries the group's
 *  primary-variant display fields plus every variant eval_summary_id so the
 *  merge can skip anything already represented. */
export interface OverlapSummaryCandidate {
  groupKey: string
  displayName: string
  evalSummaryIds: string[]
  familyKey: string
  familyName: string
  score: number
  unit: string | null
  metricSummaryId: string
  metricName: string
  temperature: number | null
  maxTokens: number | null
  annotations: RowAnnotations | null
}

export interface BuildOverlapRowsInput {
  benchmarkIndex: BenchmarkIndexEntry[] | null | undefined
  comparisonIndex: ComparisonIndex | null | undefined
  currentModelRouteId: string
  currentModelIdentityKeys: Set<string>
  familyDisplayByKey: Map<string, string>
  summaryCandidates?: OverlapSummaryCandidate[]
  summaryJoinRows?: OverlapSummaryJoinRow[]
}

const STDERR_SUFFIX_PATTERN = /_(stderr|std_err|standard_error)$/i

function isStderrMetricId(id: string | null | undefined): boolean {
  if (!id) return false
  const local = id.split("%3A").pop() ?? id
  return STDERR_SUFFIX_PATTERN.test(local)
}

const tCrit95: Record<number, number> = {
  1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
  6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
  15: 2.131, 20: 2.086, 29: 2.045,
}

function tFor(df: number): number {
  if (df <= 0) return 12.706
  if (df >= 30) return 2.0
  const known = [29, 20, 15, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
  for (const k of known) if (df >= k) return tCrit95[k]
  return 12.706
}

function isPercentUnit(unit: string | null): boolean {
  return /percent|%|pct/.test((unit ?? "").toLowerCase())
}

function formatHeuristicPercent(score: number, unit: string | null): string {
  return isPercentUnit(unit) || score > 1.5
    ? `${score.toFixed(1)}%`
    : `${(score * 100).toFixed(1)}%`
}

export function buildOverlapRows(input: BuildOverlapRowsInput): OverlapRow[] {
  const {
    benchmarkIndex,
    comparisonIndex,
    currentModelRouteId,
    currentModelIdentityKeys,
    familyDisplayByKey,
    summaryCandidates = [],
    summaryJoinRows = [],
  } = input

  const joinRowsByEvalId = new Map<string, OverlapSummaryJoinRow[]>()
  for (const row of summaryJoinRows) {
    if (!row.evalSummaryId) continue
    const list = joinRowsByEvalId.get(row.evalSummaryId)
    if (list) list.push(row)
    else joinRowsByEvalId.set(row.evalSummaryId, [row])
  }
  // The backfill join is only safe when the eval id maps to exactly one of
  // the model's own result rows — pooled metrics make fuzzier joins
  // mis-attribute, and wrong attribution is worse than "not reported".
  const uniqueJoinRow = (evalSummaryId: string): OverlapSummaryJoinRow | null => {
    const rows = joinRowsByEvalId.get(evalSummaryId)
    return rows && rows.length === 1 ? rows[0] : null
  }

  const out: OverlapRow[] = []

  if (benchmarkIndex && comparisonIndex) {
    // `by_model` is an optional acceleration: lookups must keep working off
    // the per-metric `scores[]` identity scan when the field is absent.
    const byModel = comparisonIndex.by_model?.[currentModelRouteId] ?? {}
    const findOwnScoreRow = (
      metric: ComparisonMetricEntry,
    ): ComparisonScoreEntry | null => {
      for (const row of metric.scores) {
        if (
          (currentModelIdentityKeys.has(row.model_route_id) ||
            currentModelIdentityKeys.has(row.model_group_id)) &&
          Number.isFinite(row.score)
        ) {
          return row
        }
      }
      return null
    }
    const lookupModelScore = (
      evalId: string,
      ownScoreRow: ComparisonScoreEntry | null,
      metric: ComparisonMetricEntry,
    ): number | null => {
      const cell = byModel[evalId]?.[metric.metric_summary_id]
      if (cell != null && Number.isFinite(cell.score)) return cell.score
      return ownScoreRow ? ownScoreRow.score : null
    }

    for (const entry of benchmarkIndex) {
      const bestPerFamily = new Map<string, OverlapAppearance>()
      for (const appearance of entry.appearances ?? []) {
        const familyKey = appearance.family_key
        const familyName = familyDisplayByKey.get(familyKey) ?? familyKey
        for (const evalId of appearance.constituent_evaluation_ids ?? []) {
          const evalEntry = comparisonIndex.evals[evalId]
          if (!evalEntry) continue
          const targetMetric =
            evalEntry.metrics.find(
              (m) =>
                !isStderrMetricId(m.metric_summary_id) &&
                /accuracy|score|exact|pass|win|mean/i.test(m.metric_name ?? ""),
            ) ??
            evalEntry.metrics.find((m) => !isStderrMetricId(m.metric_summary_id)) ??
            evalEntry.metrics[0]
          if (!targetMetric) continue
          const ownScoreRow = findOwnScoreRow(targetMetric)
          const score = lookupModelScore(evalId, ownScoreRow, targetMetric)
          if (score == null || !Number.isFinite(score)) continue
          const unit = targetMetric.unit ?? null
          if (!bestPerFamily.has(familyKey)) {
            // Generation params prefer the score cell; absent fields (old
            // snapshots) fall back to the unique-row summary join. A null on
            // the cell is authoritative ("not reported"), not absence.
            const fallback = uniqueJoinRow(evalId)
            const temperature =
              ownScoreRow && ownScoreRow.temperature !== undefined
                ? ownScoreRow.temperature
                : fallback
                  ? fallback.temperature
                  : null
            const maxTokens =
              ownScoreRow && ownScoreRow.max_tokens !== undefined
                ? ownScoreRow.max_tokens
                : fallback
                  ? fallback.maxTokens
                  : null
            bestPerFamily.set(familyKey, {
              familyKey,
              familyName,
              evalSummaryId: evalId,
              metricSummaryId: targetMetric.metric_summary_id,
              metricName: targetMetric.metric_name ?? "",
              score,
              displayScore: formatHeuristicPercent(score, unit),
              unit,
              temperature,
              maxTokens,
              annotations: fallback ? fallback.annotations : null,
              sourceKind: "comparison-index",
            })
          }
        }
      }
      // Two-stage dedup:
      //   1. Drop duplicate constituent_evaluation_ids — benchmark_index can list
      //      the same eval under multiple family_keys (e.g.
      //      `artificial-analysis-llms/mmlu-pro` is listed under both
      //      `artificial-analysis` and `mmlu`), but that's the same
      //      observation, not two independent reports.
      //   2. Aggregator-only score dedup — llm-stats republishes
      //      canonical sources' numbers, so when its score byte-equals
      //      an independent evaluator's we drop the llm-stats copy. Two
      //      independent evaluators that happen to arrive at the same
      //      number are KEPT — confirming signal, not duplicate data.
      const allRaw = Array.from(bestPerFamily.values())
      const isAggregator = (familyKey: string) => familyKey === "llm-stats"
      const seenEvalIds = new Set<string>()
      const distinctByEvalId: OverlapAppearance[] = []
      for (const c of allRaw) {
        if (seenEvalIds.has(c.evalSummaryId)) continue
        seenEvalIds.add(c.evalSummaryId)
        distinctByEvalId.push(c)
      }
      // Process non-aggregators first so their scores populate the
      // seen-set before any llm-stats appearance gets a chance to claim
      // the score.
      distinctByEvalId.sort((a, b) => {
        const aAgg = isAggregator(a.familyKey) ? 1 : 0
        const bAgg = isAggregator(b.familyKey) ? 1 : 0
        return aAgg - bAgg
      })
      const seenScores = new Set<number>()
      const collected: OverlapAppearance[] = []
      for (const c of distinctByEvalId) {
        if (isAggregator(c.familyKey) && seenScores.has(c.score)) continue
        seenScores.add(c.score)
        collected.push(c)
      }
      if (collected.length < 1) continue

      // Cross-appearance scale harmonisation only makes sense for ≥2
      // appearances. A lone appearance keeps its score as-is and lets the
      // metric unit settle the scale: |score| ≤ 1.5 with a percent unit
      // genuinely means a low percent, not a proportion.
      const single = collected.length === 1 ? collected[0] : null
      const highCount = collected.filter((c) => Math.abs(c.score) > 1.5).length
      const lowCount = collected.length - highCount
      const useHigh = single
        ? isPercentUnit(single.unit) || Math.abs(single.score) > 1.5
        : highCount >= lowCount
      const scaled = single
        ? [...collected]
        : collected.map((c) => {
            const isHigh = Math.abs(c.score) > 1.5
            const score = useHigh
              ? isHigh ? c.score : c.score * 100
              : isHigh ? c.score / 100 : c.score
            return { ...c, score }
          })
      const scores = scaled.map((s) => s.score)
      const mean = scores.reduce((a, b) => a + b, 0) / scores.length
      const variance = scores.length > 1
        ? scores.reduce((a, b) => a + (b - mean) ** 2, 0) / (scores.length - 1)
        : 0
      const stddev = Math.sqrt(variance)
      const ci95 = scores.length >= 2
        ? {
            low: mean - tFor(scores.length - 1) * (stddev / Math.sqrt(scores.length)),
            high: mean + tFor(scores.length - 1) * (stddev / Math.sqrt(scores.length)),
          }
        : null
      out.push({
        canonicalKey: entry.key,
        canonicalDisplayName: entry.display_name,
        appearances: scaled.sort((a, b) => b.score - a.score),
        mean,
        stddev,
        min: Math.min(...scores),
        max: Math.max(...scores),
        ci95,
        isPercentScale: useHigh,
      })
    }
  }

  // Merge population (b): benchmark groups with no benchmark_index entry.
  // Dedup key is eval_summary_id — a candidate is skipped when ANY of its
  // variant ids is already represented (group keys can be synthesized parent
  // ids for slice-folded groups, so they aren't reliable here).
  const representedEvalIds = new Set<string>()
  for (const row of out) {
    for (const a of row.appearances) {
      if (a.evalSummaryId) representedEvalIds.add(a.evalSummaryId)
    }
  }
  for (const c of summaryCandidates) {
    if (!Number.isFinite(c.score)) continue
    const ids = c.evalSummaryIds.filter(Boolean)
    if (ids.some((id) => representedEvalIds.has(id))) continue
    for (const id of ids) representedEvalIds.add(id)
    out.push({
      canonicalKey: c.groupKey,
      canonicalDisplayName: c.displayName,
      appearances: [
        {
          familyKey: c.familyKey,
          familyName: c.familyName,
          evalSummaryId: ids[0] ?? "",
          metricSummaryId: c.metricSummaryId,
          metricName: c.metricName,
          score: c.score,
          displayScore: formatHeuristicPercent(c.score, c.unit),
          unit: c.unit,
          temperature: c.temperature,
          maxTokens: c.maxTokens,
          annotations: c.annotations,
          sourceKind: "summary",
        },
      ],
      mean: c.score,
      stddev: 0,
      min: c.score,
      max: c.score,
      ci95: null,
      isPercentScale: isPercentUnit(c.unit) || Math.abs(c.score) > 1.5,
    })
  }

  // A single-appearance row whose eval already backs a multi-source row is
  // the same observation resurfacing through a subset-shaped benchmark_index
  // entry (e.g. aime-2024 listing one of aime's constituent evals) — keep
  // only the multi-source row.
  const multiRowEvalIds = new Set<string>()
  for (const row of out) {
    if (row.appearances.length < 2) continue
    for (const a of row.appearances) {
      if (a.evalSummaryId) multiRowEvalIds.add(a.evalSummaryId)
    }
  }
  const rows = out.filter(
    (row) =>
      row.appearances.length >= 2 ||
      !multiRowEvalIds.has(row.appearances[0]?.evalSummaryId ?? ""),
  )

  // Row-level dedup: when two benchmark_index entries resolve to the
  // exact same set of (familyKey, score) appearances, they're aliases
  // of the same canonical (e.g. AIME vs aime-2025 both resolving to
  // {Vals.ai 12.9%, Artificial Analysis 11.7%}). Collapse to one row.
  // Tie-break on the shorter / cleaner canonical key — the longer
  // alias is usually the year-suffixed or otherwise-disambiguated
  // variant. Single-appearance rows are exempt from the score
  // signature (two unrelated benchmarks from the same family can land
  // on the same number); they collapse only when they point at the
  // very same eval.
  const dedupSig = (row: OverlapRow) =>
    row.appearances.length >= 2
      ? row.appearances
          .map((a) => `${a.familyKey}::${a.score.toFixed(8)}`)
          .sort()
          .join("|")
      : `single::${row.appearances[0]?.evalSummaryId || row.canonicalKey}`
  const bestBySig = new Map<string, OverlapRow>()
  for (const row of rows) {
    const sig = dedupSig(row)
    const prev = bestBySig.get(sig)
    if (
      !prev ||
      row.canonicalKey.length < prev.canonicalKey.length ||
      (row.canonicalKey.length === prev.canonicalKey.length &&
        row.canonicalDisplayName.localeCompare(prev.canonicalDisplayName) < 0)
    ) {
      bestBySig.set(sig, row)
    }
  }
  const deduped = Array.from(bestBySig.values())
  deduped.sort(
    (a, b) =>
      b.appearances.length - a.appearances.length ||
      a.canonicalDisplayName.localeCompare(b.canonicalDisplayName),
  )
  return deduped
}

/** Rows where the model has ≥2 independent appearances — the population the
 *  view used to be limited to, and what the tab default keys on. */
export function countMultiSourceRows(rows: OverlapRow[]): number {
  let n = 0
  for (const row of rows) if (row.appearances.length >= 2) n += 1
  return n
}
