import { readdirSync } from "fs"
import path from "path"
import { fileURLToPath } from "url"

import { describe, expect, it } from "vitest"

import type { HFEvalDetail, HFEvalModelResult, HFModelDetail } from "../lib/hf-data"

import { fixtureEntries, loadAllFixtures, walkHierarchyResults } from "./fixtures/loader"

const FIXTURES_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures")

// Tier A — pipeline contract tests.
//
// These tests assert that the pipeline-emitted artifacts in tests/fixtures/
// carry every field the TS code depends on. They run against PINNED fixtures,
// not the live cache, so an upstream data refresh doesn't make these flap.
//
// To check the live cache for drift instead, see tests/upstream-drift.test.ts.
//
// When adding a deletion that depends on a new pipeline guarantee, add a
// contract here first. Each contract should fail loudly with the offending
// file path + key path so violations are easy to fix.

const KNOWN_PIPELINE_CATEGORY_KEYS = new Set([
  "agentic",
  "reasoning",
  "general",
  "safety",
  "knowledge",
  "other",
  "coding",
  "instruction_following",
  "language_understanding",
])

const VALID_EVALUATOR_RELATIONSHIPS = new Set(["first_party", "third_party", "other"])

interface Violation {
  fixture: string
  path: string
  detail: string
}

describe("Tier A — pipeline contracts (model files)", () => {
  const models = loadAllFixtures<HFModelDetail>("models")

  it("every model_result carries source_metadata", () => {
    const violations: Violation[] = []
    for (const { id, data } of models) {
      for (const { result, path } of walkHierarchyResults<HFEvalModelResult>(data, id)) {
        if (!result.source_metadata) {
          violations.push({ fixture: id, path, detail: "missing source_metadata" })
        }
      }
    }
    expect(violations, formatViolations(violations)).toEqual([])
  })

  it("every source_metadata.evaluator_relationship is in the known set", () => {
    const violations: Violation[] = []
    for (const { id, data } of models) {
      for (const { result, path } of walkHierarchyResults<HFEvalModelResult>(data, id)) {
        const rel = result.source_metadata?.evaluator_relationship
        if (rel != null && !VALID_EVALUATOR_RELATIONSHIPS.has(rel)) {
          violations.push({ fixture: id, path, detail: `unknown evaluator_relationship=${rel}` })
        }
      }
    }
    expect(violations, formatViolations(violations)).toEqual([])
  })

  it("every hierarchy_by_category key is in PIPELINE_CATEGORY_MAP", () => {
    const violations: Violation[] = []
    for (const { id, data } of models) {
      for (const key of Object.keys(data.hierarchy_by_category ?? {})) {
        if (!KNOWN_PIPELINE_CATEGORY_KEYS.has(key.toLowerCase())) {
          violations.push({ fixture: id, path: `hierarchy_by_category.${key}`, detail: "unknown category key" })
        }
      }
    }
    expect(violations, formatViolations(violations)).toEqual([])
  })

  it("every model_result.retrieved_timestamp parses as a valid Date", () => {
    const violations: Violation[] = []
    for (const { id, data } of models) {
      for (const { result, path } of walkHierarchyResults<HFEvalModelResult>(data, id)) {
        const ts = result.retrieved_timestamp
        if (ts == null) continue
        // Pipeline emits either ISO strings or unix-seconds-as-string.
        const numeric = Number.parseFloat(ts)
        const isNumeric = Number.isFinite(numeric) && !ts.includes("-")
        const dateValue = isNumeric ? new Date(numeric * 1000) : new Date(ts)
        if (Number.isNaN(dateValue.getTime())) {
          violations.push({ fixture: id, path: `${path}.retrieved_timestamp`, detail: `unparseable: ${ts}` })
        }
      }
    }
    expect(violations, formatViolations(violations)).toEqual([])
  })

  it("model card has model_group_id matching pipelineSlugify(model_group_id) → model_route_id", () => {
    const violations: Violation[] = []
    for (const { id, data } of models) {
      if (!data.model_group_id) {
        violations.push({ fixture: id, path: "model_group_id", detail: "missing" })
        continue
      }
      const expected = data.model_group_id.replace(/\//g, "__")
      if (data.model_route_id !== expected) {
        violations.push({
          fixture: id,
          path: "model_route_id",
          detail: `${data.model_route_id} !== ${expected} (derived from ${data.model_group_id})`,
        })
      }
    }
    expect(violations, formatViolations(violations)).toEqual([])
  })

})

describe("Tier A — pipeline contracts (eval-detail files)", () => {
  const evals = loadAllFixtures<HFEvalDetail>("evals")

  it("every eval-detail has eval_summary_id, benchmark, benchmark_leaf_name", () => {
    const violations: Violation[] = []
    for (const { id, data } of evals) {
      for (const field of ["eval_summary_id", "benchmark", "benchmark_leaf_name"] as const) {
        if (!data[field]) {
          violations.push({ fixture: id, path: field, detail: "missing or empty" })
        }
      }
    }
    expect(violations, formatViolations(violations)).toEqual([])
  })

  it("every eval-detail has category as a non-empty string", () => {
    const violations: Violation[] = []
    for (const { id, data } of evals) {
      if (typeof data.category !== "string" || data.category.length === 0) {
        violations.push({ fixture: id, path: "category", detail: `not a non-empty string: ${data.category}` })
      }
    }
    expect(violations, formatViolations(violations)).toEqual([])
  })

  it("every model_result in eval-detail metrics carries source_metadata", () => {
    const violations: Violation[] = []
    for (const { id, data } of evals) {
      for (const [metricIdx, metric] of (data.metrics ?? []).entries()) {
        for (const [resultIdx, mr] of (metric.model_results ?? []).entries()) {
          if (!mr.source_metadata) {
            violations.push({
              fixture: id,
              path: `metrics[${metricIdx}].model_results[${resultIdx}]`,
              detail: "missing source_metadata",
            })
          }
        }
      }
    }
    expect(violations, formatViolations(violations)).toEqual([])
  })

  it("every metric has metric_summary_id and metric_name", () => {
    const violations: Violation[] = []
    for (const { id, data } of evals) {
      for (const [metricIdx, metric] of (data.metrics ?? []).entries()) {
        if (!metric.metric_summary_id) {
          violations.push({ fixture: id, path: `metrics[${metricIdx}].metric_summary_id`, detail: "missing" })
        }
        if (!metric.metric_name) {
          violations.push({ fixture: id, path: `metrics[${metricIdx}].metric_name`, detail: "missing" })
        }
      }
    }
    expect(violations, formatViolations(violations)).toEqual([])
  })

  // Guards against the eval-list emitting display strings in a
  // "<generic-metric> on <benchmark>" / "for scorer" / "model_graded" shape.
  // If the pipeline starts emitting those shapes, this test fails loudly.
  // The four fields below mirror the eval-list resolution order
  // (`evaluation_name || display_name || benchmark_leaf_name || eval_summary_id`).
  it("eval-list display strings don't match generic-metric-on-benchmark patterns", () => {
    const violations: Violation[] = []
    for (const { id, data } of evals) {
      // Pipeline emits `evaluation_name` and `display_name` on eval entries
      // even though they're not on HFEvalDetail (TS type is a subset of the
      // actual cache shape). Cast to access them.
      const extras = data as unknown as { evaluation_name?: string; display_name?: string }
      const raw =
        extras.evaluation_name ||
        extras.display_name ||
        data.benchmark_leaf_name ||
        data.eval_summary_id ||
        ""
      const normalized = raw.trim().toLowerCase()
      const reasons: string[] = []
      if (normalized.startsWith("accuracy on ")) reasons.push("startsWith('accuracy on ')")
      if (normalized.startsWith("score on ")) reasons.push("startsWith('score on ')")
      if (normalized.includes("for scorer")) reasons.push("includes('for scorer')")
      if (normalized.includes("model_graded")) reasons.push("includes('model_graded')")
      if (reasons.length > 0) {
        violations.push({
          fixture: id,
          path: "evaluation_name|display_name|benchmark_leaf_name|eval_summary_id",
          detail: `${JSON.stringify(raw)} matches: ${reasons.join(", ")}`,
        })
      }
    }
    expect(violations, formatViolations(violations)).toEqual([])
  })
})

describe("Tier A — fixture inventory", () => {
  // Catches both directions: (a) a fixture file exists that isn't in the
  // manifest (stale/unreferenced and won't be exercised by snapshot tests),
  // (b) a manifest entry references a missing file. The "manifest entry
  // resolves to a readable file" check from earlier was redundant with the
  // 14 contract tests above (which all call loadAllFixtures at module
  // scope), but the file→manifest direction was uncovered.
  it("fixture files match the manifest exactly (no orphans, no missing)", () => {
    const groupsAndDirs = [
      ["evals", "evals"],
      ["models", "models"],
      ["developers", "developers"],
      ["model_cards", "model-cards"],
    ] as const
    const orphans: string[] = []
    const missing: string[] = []
    for (const [group, dirName] of groupsAndDirs) {
      const dir = path.join(FIXTURES_DIR, dirName)
      const onDisk = new Set(readdirSync(dir).filter((f) => f.endsWith(".json")))
      const inManifest = new Set(fixtureEntries(group).map((e) => `${e.id}.json`))
      for (const f of onDisk) if (!inManifest.has(f)) orphans.push(`${group}/${f}`)
      for (const f of inManifest) if (!onDisk.has(f)) missing.push(`${group}/${f}`)
    }
    expect({ orphans, missing }).toEqual({ orphans: [], missing: [] })
  })
})

function formatViolations(violations: Violation[]): string {
  if (violations.length === 0) return ""
  const sample = violations.slice(0, 10)
  const more = violations.length > 10 ? `\n  …and ${violations.length - 10} more` : ""
  return [
    `\n${violations.length} contract violation(s):`,
    ...sample.map((v) => `  ${v.fixture} :: ${v.path} — ${v.detail}`),
    more,
  ].join("\n")
}
