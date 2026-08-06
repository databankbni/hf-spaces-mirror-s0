import { describe, expect, it } from "vitest"

import type {
  BenchmarkIndexEntry,
  ComparisonEvalEntry,
  ComparisonIndex,
  ComparisonMetricEntry,
  ComparisonScoreEntry,
  RowAnnotations,
} from "../lib/backend-artifacts"
import {
  buildOverlapRows,
  countMultiSourceRows,
  type BuildOverlapRowsInput,
  type OverlapSummaryCandidate,
  type OverlapSummaryJoinRow,
} from "../lib/overlaps"

const MODEL_ROUTE = "acme%2Fmodel-1"
const IDENTITY = new Set([MODEL_ROUTE, "acme/model-1"])

const FAMILY_NAMES = new Map([
  ["fam-a", "Family A"],
  ["fam-b", "Family B"],
  ["llm-stats", "LLM Stats"],
])

const ANNOTATIONS: RowAnnotations = {
  reproducibility_gap: {
    has_reproducibility_gap: true,
    missing_fields: ["temperature"],
    required_field_count: 5,
    populated_field_count: 4,
    signal_version: "1.0",
  },
  provenance: null,
  variant_divergence: null,
  cross_party_divergence: null,
}

function scoreRow(overrides: Partial<ComparisonScoreEntry> = {}): ComparisonScoreEntry {
  return {
    model_route_id: "other%2Fpeer",
    model_family_id: "",
    model_group_id: "",
    model_family_name: "",
    developer: "",
    variant_key: "",
    score: 0,
    rank: 1,
    total: 2,
    submission_count: 1,
    submission_axis: "default",
    ...overrides,
  } as ComparisonScoreEntry
}

function ownRow(score: number, overrides: Partial<ComparisonScoreEntry> = {}) {
  return scoreRow({ model_route_id: MODEL_ROUTE, score, ...overrides })
}

function metricEntry(overrides: Partial<ComparisonMetricEntry> = {}): ComparisonMetricEntry {
  return {
    metric_summary_id: "m%3Aaccuracy",
    metric_name: "accuracy",
    metric_id: null,
    metric_key: null,
    group: "capability",
    group_order: 0,
    lower_is_better: false,
    unit: null,
    scores: [],
    ...overrides,
  }
}

function evalEntry(evaluationId: string, metrics: ComparisonMetricEntry[]): ComparisonEvalEntry {
  return {
    evaluation_id: evaluationId,
    benchmark_id: null,
    family_id: null,
    family_display_name: null,
    composite_slug: null,
    composite_display_name: null,
    parent_benchmark_id: null,
    display_name: null,
    category: "Knowledge",
    is_slice: false,
    is_summary_score: false,
    summary_score_for: null,
    metrics,
  }
}

function indexEntry(
  key: string,
  displayName: string,
  appearances: Array<{ family: string; evalIds: string[] }>,
): BenchmarkIndexEntry {
  return {
    key,
    display_name: displayName,
    appearances: appearances.map((a) => ({
      family_key: a.family,
      benchmark_key: key,
      constituent_evaluation_ids: a.evalIds,
      is_canonical_home: a.family === key,
    })),
  }
}

function comparisonIndexOf(
  evals: Record<string, ComparisonEvalEntry>,
  byModel?: NonNullable<ComparisonIndex["by_model"]>,
): ComparisonIndex {
  return {
    generated_at: "2026-06-10T00:00:00Z",
    config_version: 3,
    metric_group_order: ["capability", "robustness", "efficiency", "cost", "latency", "rank", "other"],
    evals,
    ...(byModel ? { by_model: byModel } : {}),
  }
}

function candidate(overrides: Partial<OverlapSummaryCandidate> = {}): OverlapSummaryCandidate {
  return {
    groupKey: "acme%2Fbench-x",
    displayName: "Bench X",
    evalSummaryIds: ["acme%2Fbench-x"],
    familyKey: "acme-org",
    familyName: "Acme Org",
    score: 0.42,
    unit: null,
    metricSummaryId: "m%3Aaccuracy",
    metricName: "accuracy",
    temperature: null,
    maxTokens: null,
    annotations: null,
    ...overrides,
  }
}

function build(overrides: Partial<BuildOverlapRowsInput> = {}) {
  return buildOverlapRows({
    benchmarkIndex: [],
    comparisonIndex: undefined,
    currentModelRouteId: MODEL_ROUTE,
    currentModelIdentityKeys: IDENTITY,
    familyDisplayByKey: FAMILY_NAMES,
    ...overrides,
  })
}

const MMLU_INDEX = indexEntry("mmlu", "MMLU", [
  { family: "fam-a", evalIds: ["fam-a%2Fmmlu"] },
  { family: "fam-b", evalIds: ["fam-b%2Fmmlu"] },
])

function mmluEvals(scoresA: ComparisonScoreEntry[], scoresB: ComparisonScoreEntry[]) {
  return {
    "fam-a%2Fmmlu": evalEntry("fam-a%2Fmmlu", [metricEntry({ scores: scoresA })]),
    "fam-b%2Fmmlu": evalEntry("fam-b%2Fmmlu", [metricEntry({ scores: scoresB })]),
  }
}

describe("buildOverlapRows: multi-source rows", () => {
  it("aggregates a two-family benchmark with Student's-t CI (scores[] lookup, no by_model)", () => {
    const rows = build({
      benchmarkIndex: [MMLU_INDEX],
      comparisonIndex: comparisonIndexOf(
        mmluEvals([ownRow(80), scoreRow({ score: 91 })], [ownRow(70)]),
      ),
    })
    expect(rows).toHaveLength(1)
    const row = rows[0]
    expect(row.canonicalKey).toBe("mmlu")
    expect(row.appearances.map((a) => a.score)).toEqual([80, 70])
    expect(row.appearances.map((a) => a.familyName)).toEqual(["Family A", "Family B"])
    expect(row.appearances.every((a) => a.sourceKind === "comparison-index")).toBe(true)
    expect(row.appearances[0].displayScore).toBe("80.0%")
    expect(row.mean).toBeCloseTo(75, 10)
    expect(row.stddev).toBeCloseTo(Math.sqrt(50), 10)
    expect(row.min).toBe(70)
    expect(row.max).toBe(80)
    expect(row.isPercentScale).toBe(true)
    // n=2, df=1 → t=12.706; half-width = 12.706 * sqrt(50)/sqrt(2) = 63.53
    expect(row.ci95?.low).toBeCloseTo(75 - 63.53, 6)
    expect(row.ci95?.high).toBeCloseTo(75 + 63.53, 6)
  })

  it("resolves scores through by_model when present", () => {
    const rows = build({
      benchmarkIndex: [MMLU_INDEX],
      comparisonIndex: comparisonIndexOf(mmluEvals([], []), {
        [MODEL_ROUTE]: {
          "fam-a%2Fmmlu": {
            "m%3Aaccuracy": { score: 80, rank: 1, total: 4, submission_count: 1, submission_axis: "default" },
          },
          "fam-b%2Fmmlu": {
            "m%3Aaccuracy": { score: 70, rank: 2, total: 4, submission_count: 1, submission_axis: "default" },
          },
        },
      }),
    })
    expect(rows).toHaveLength(1)
    expect(rows[0].appearances.map((a) => a.score)).toEqual([80, 70])
    expect(rows[0].mean).toBeCloseTo(75, 10)
  })

  it("rescales mixed proportion/percent appearances to the majority scale", () => {
    const rows = build({
      benchmarkIndex: [MMLU_INDEX],
      comparisonIndex: comparisonIndexOf(mmluEvals([ownRow(0.7)], [ownRow(80)])),
    })
    expect(rows[0].appearances.map((a) => a.score)).toEqual([80, 70])
    expect(rows[0].isPercentScale).toBe(true)
  })

  it("drops the aggregator copy of an independent score, keeps independent ties", () => {
    const entry = indexEntry("mmlu", "MMLU", [
      { family: "fam-a", evalIds: ["fam-a%2Fmmlu"] },
      { family: "fam-b", evalIds: ["fam-b%2Fmmlu"] },
      { family: "llm-stats", evalIds: ["llm-stats%2Fmmlu"] },
    ])
    const rows = build({
      benchmarkIndex: [entry],
      comparisonIndex: comparisonIndexOf({
        ...mmluEvals([ownRow(80)], [ownRow(80)]),
        "llm-stats%2Fmmlu": evalEntry("llm-stats%2Fmmlu", [metricEntry({ scores: [ownRow(80)] })]),
      }),
    })
    expect(rows).toHaveLength(1)
    expect(rows[0].appearances.map((a) => a.familyKey).sort()).toEqual(["fam-a", "fam-b"])
  })
})

describe("buildOverlapRows: single-source rows", () => {
  it("keeps benchmarks where the model has only one deduped appearance, with degenerate stats", () => {
    const rows = build({
      benchmarkIndex: [MMLU_INDEX],
      comparisonIndex: comparisonIndexOf(mmluEvals([ownRow(80)], [])),
    })
    expect(rows).toHaveLength(1)
    const row = rows[0]
    expect(row.appearances).toHaveLength(1)
    expect(row.mean).toBe(80)
    expect(row.stddev).toBe(0)
    expect(row.min).toBe(80)
    expect(row.max).toBe(80)
    expect(row.ci95).toBeNull()
    expect(row.isPercentScale).toBe(true)
  })

  it("tags a lone proportion-scale score as such", () => {
    const rows = build({
      benchmarkIndex: [MMLU_INDEX],
      comparisonIndex: comparisonIndexOf(mmluEvals([ownRow(0.42)], [])),
    })
    expect(rows[0].appearances[0].score).toBe(0.42)
    expect(rows[0].isPercentScale).toBe(false)
  })

  it("trusts a percent unit on a lone low score instead of rescaling it", () => {
    const rows = build({
      benchmarkIndex: [MMLU_INDEX],
      comparisonIndex: comparisonIndexOf({
        "fam-a%2Fmmlu": evalEntry("fam-a%2Fmmlu", [
          metricEntry({ unit: "percent", scores: [ownRow(1.2)] }),
        ]),
        "fam-b%2Fmmlu": evalEntry("fam-b%2Fmmlu", [metricEntry({ scores: [] })]),
      }),
    })
    expect(rows).toHaveLength(1)
    expect(rows[0].appearances[0].score).toBe(1.2)
    expect(rows[0].appearances[0].displayScore).toBe("1.2%")
    expect(rows[0].isPercentScale).toBe(true)
  })

  it("trusts a percent unit on a summary candidate's low score", () => {
    const rows = build({
      summaryCandidates: [candidate({ score: 1.2, unit: "percent" })],
    })
    expect(rows).toHaveLength(1)
    expect(rows[0].appearances[0].displayScore).toBe("1.2%")
    expect(rows[0].isPercentScale).toBe(true)
  })

  it("merges summary candidates and dedups them by eval_summary_id across populations", () => {
    const rows = build({
      benchmarkIndex: [MMLU_INDEX],
      comparisonIndex: comparisonIndexOf(mmluEvals([ownRow(80)], [ownRow(70)])),
      summaryCandidates: [
        // Already represented by the fam-a appearance — must be skipped.
        candidate({ groupKey: "fam-a%2Fmmlu", displayName: "MMLU (own)", evalSummaryIds: ["fam-a%2Fmmlu"] }),
        candidate({
          groupKey: "acme%2Fbench-x",
          displayName: "Bench X",
          evalSummaryIds: ["acme%2Fbench-x"],
          score: 0.42,
        }),
        // Shares an id with the previous candidate — must be skipped too.
        candidate({ groupKey: "acme%2Fbench-x-alias", displayName: "Bench X Alias", evalSummaryIds: ["acme%2Fbench-x"] }),
      ],
    })
    expect(rows).toHaveLength(2)
    const summaryRow = rows.find((r) => r.canonicalKey === "acme%2Fbench-x")
    expect(summaryRow).toBeDefined()
    expect(summaryRow?.canonicalDisplayName).toBe("Bench X")
    expect(summaryRow?.appearances).toHaveLength(1)
    expect(summaryRow?.appearances[0].sourceKind).toBe("summary")
    expect(summaryRow?.appearances[0].familyName).toBe("Acme Org")
    expect(summaryRow?.appearances[0].displayScore).toBe("42.0%")
    expect(summaryRow?.mean).toBe(0.42)
    expect(summaryRow?.stddev).toBe(0)
    expect(summaryRow?.ci95).toBeNull()
    expect(summaryRow?.isPercentScale).toBe(false)
  })

  it("builds summary rows even when the comparison index is unavailable", () => {
    const rows = build({
      benchmarkIndex: undefined,
      comparisonIndex: undefined,
      summaryCandidates: [candidate()],
    })
    expect(rows).toHaveLength(1)
    expect(rows[0].appearances[0].sourceKind).toBe("summary")
  })
})

describe("buildOverlapRows: row dedup scoping", () => {
  it("collapses alias index entries with identical (family, score) signatures onto the shorter key", () => {
    const aime = indexEntry("aime", "AIME", [
      { family: "fam-a", evalIds: ["fam-a%2Faime"] },
      { family: "fam-b", evalIds: ["fam-b%2Faime"] },
    ])
    const aime2025 = indexEntry("aime-2025", "AIME 2025", [
      { family: "fam-a", evalIds: ["fam-a%2Faime-2025"] },
      { family: "fam-b", evalIds: ["fam-b%2Faime-2025"] },
    ])
    const rows = build({
      benchmarkIndex: [aime2025, aime],
      comparisonIndex: comparisonIndexOf({
        "fam-a%2Faime": evalEntry("fam-a%2Faime", [metricEntry({ scores: [ownRow(12.9)] })]),
        "fam-b%2Faime": evalEntry("fam-b%2Faime", [metricEntry({ scores: [ownRow(11.7)] })]),
        "fam-a%2Faime-2025": evalEntry("fam-a%2Faime-2025", [metricEntry({ scores: [ownRow(12.9)] })]),
        "fam-b%2Faime-2025": evalEntry("fam-b%2Faime-2025", [metricEntry({ scores: [ownRow(11.7)] })]),
      }),
    })
    expect(rows).toHaveLength(1)
    expect(rows[0].canonicalKey).toBe("aime")
  })

  it("does not collapse unrelated single-source rows with coincidentally equal scores", () => {
    const rows = build({
      summaryCandidates: [
        candidate({ groupKey: "acme%2Fbench-x", displayName: "Bench X", evalSummaryIds: ["acme%2Fbench-x"], score: 0.42 }),
        candidate({ groupKey: "acme%2Fbench-y", displayName: "Bench Y", evalSummaryIds: ["acme%2Fbench-y"], score: 0.42 }),
      ],
    })
    expect(rows.map((r) => r.canonicalDisplayName).sort()).toEqual(["Bench X", "Bench Y"])
  })

  it("drops a single-appearance row whose eval already backs a multi-source row", () => {
    const aime = indexEntry("aime", "AIME", [
      { family: "fam-a", evalIds: ["fam-a%2Faime"] },
      { family: "fam-b", evalIds: ["fam-b%2Faime"] },
    ])
    // Subset-shaped alias: resolves to one of aime's constituent evals.
    const aime2024 = indexEntry("aime-2024", "AIME 2024", [
      { family: "fam-a", evalIds: ["fam-a%2Faime"] },
    ])
    const rows = build({
      benchmarkIndex: [aime2024, aime],
      comparisonIndex: comparisonIndexOf({
        "fam-a%2Faime": evalEntry("fam-a%2Faime", [metricEntry({ scores: [ownRow(12.9)] })]),
        "fam-b%2Faime": evalEntry("fam-b%2Faime", [metricEntry({ scores: [ownRow(11.7)] })]),
      }),
    })
    expect(rows).toHaveLength(1)
    expect(rows[0].canonicalKey).toBe("aime")
    expect(rows[0].appearances).toHaveLength(2)
  })

  it("collapses single-source alias rows that point at the very same eval", () => {
    const a = indexEntry("gsm8k", "GSM8K", [{ family: "fam-a", evalIds: ["fam-a%2Fgsm8k"] }])
    const b = indexEntry("gsm8k-2024", "GSM8K 2024", [{ family: "fam-a", evalIds: ["fam-a%2Fgsm8k"] }])
    const rows = build({
      benchmarkIndex: [b, a],
      comparisonIndex: comparisonIndexOf({
        "fam-a%2Fgsm8k": evalEntry("fam-a%2Fgsm8k", [metricEntry({ scores: [ownRow(55)] })]),
      }),
    })
    expect(rows).toHaveLength(1)
    expect(rows[0].canonicalKey).toBe("gsm8k")
  })
})

describe("buildOverlapRows: appearance enrichment", () => {
  const joinRow = (overrides: Partial<OverlapSummaryJoinRow> = {}): OverlapSummaryJoinRow => ({
    evalSummaryId: "fam-a%2Fmmlu",
    temperature: 0.3,
    maxTokens: 256,
    annotations: ANNOTATIONS,
    ...overrides,
  })

  it("prefers generation params on the comparison-index score cell", () => {
    const rows = build({
      benchmarkIndex: [MMLU_INDEX],
      comparisonIndex: comparisonIndexOf(
        mmluEvals([ownRow(80, { temperature: 0.7, max_tokens: 1024 })], [ownRow(70)]),
      ),
      summaryJoinRows: [joinRow()],
    })
    const app = rows[0].appearances.find((a) => a.familyKey === "fam-a")
    expect(app?.temperature).toBe(0.7)
    expect(app?.maxTokens).toBe(1024)
    // Annotations only live on the model's own rows — joined regardless.
    expect(app?.annotations).toBe(ANNOTATIONS)
  })

  it("treats a null score-cell param as reported (no join fallback)", () => {
    const rows = build({
      benchmarkIndex: [MMLU_INDEX],
      comparisonIndex: comparisonIndexOf(
        mmluEvals([ownRow(80, { temperature: null, max_tokens: null })], [ownRow(70)]),
      ),
      summaryJoinRows: [joinRow()],
    })
    const app = rows[0].appearances.find((a) => a.familyKey === "fam-a")
    expect(app?.temperature).toBeNull()
    expect(app?.maxTokens).toBeNull()
  })

  it("falls back to the summary join only when exactly one result row matches", () => {
    const index = comparisonIndexOf(mmluEvals([ownRow(80)], [ownRow(70)]))
    const unique = build({
      benchmarkIndex: [MMLU_INDEX],
      comparisonIndex: index,
      summaryJoinRows: [joinRow()],
    })
    const uniqueApp = unique[0].appearances.find((a) => a.familyKey === "fam-a")
    expect(uniqueApp?.temperature).toBe(0.3)
    expect(uniqueApp?.maxTokens).toBe(256)
    expect(uniqueApp?.annotations).toBe(ANNOTATIONS)

    const ambiguous = build({
      benchmarkIndex: [MMLU_INDEX],
      comparisonIndex: index,
      summaryJoinRows: [joinRow(), joinRow({ temperature: 0.9 })],
    })
    const ambiguousApp = ambiguous[0].appearances.find((a) => a.familyKey === "fam-a")
    expect(ambiguousApp?.temperature).toBeNull()
    expect(ambiguousApp?.maxTokens).toBeNull()
    expect(ambiguousApp?.annotations).toBeNull()
  })

  it("backfills from the join when the score came from by_model only", () => {
    const rows = build({
      benchmarkIndex: [MMLU_INDEX],
      comparisonIndex: comparisonIndexOf(mmluEvals([], []), {
        [MODEL_ROUTE]: {
          "fam-a%2Fmmlu": {
            "m%3Aaccuracy": { score: 80, rank: 1, total: 4, submission_count: 1, submission_axis: "default" },
          },
        },
      }),
      summaryJoinRows: [joinRow()],
    })
    const app = rows[0].appearances[0]
    expect(app.temperature).toBe(0.3)
    expect(app.maxTokens).toBe(256)
  })

  it("carries the candidate's own params on summary appearances", () => {
    const rows = build({
      summaryCandidates: [candidate({ temperature: 1, maxTokens: 2048, annotations: ANNOTATIONS })],
    })
    const app = rows[0].appearances[0]
    expect(app.temperature).toBe(1)
    expect(app.maxTokens).toBe(2048)
    expect(app.annotations).toBe(ANNOTATIONS)
  })
})

describe("countMultiSourceRows", () => {
  it("counts only rows with at least two appearances (drives the tab default)", () => {
    const rows = build({
      benchmarkIndex: [
        MMLU_INDEX,
        indexEntry("gsm8k", "GSM8K", [{ family: "fam-a", evalIds: ["fam-a%2Fgsm8k"] }]),
      ],
      comparisonIndex: comparisonIndexOf({
        ...mmluEvals([ownRow(80)], [ownRow(70)]),
        "fam-a%2Fgsm8k": evalEntry("fam-a%2Fgsm8k", [metricEntry({ scores: [ownRow(55)] })]),
      }),
      summaryCandidates: [candidate()],
    })
    expect(rows).toHaveLength(3)
    expect(countMultiSourceRows(rows)).toBe(1)
    expect(countMultiSourceRows([])).toBe(0)
  })
})
