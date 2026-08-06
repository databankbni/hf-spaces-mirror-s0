import fs from "fs"
import path from "path"

import { describe, expect, it } from "vitest"

import type { HFEvalDetail, HFEvalModelResult, HFModelDetail } from "../lib/hf-data"

import { listLiveCacheFiles, loadLiveCacheFile, walkHierarchyResults } from "./fixtures/loader"

// Tier A — drift detection variant. Runs the same shape of contracts as
// pipeline-contract.test.ts but against the LIVE .cache/hf-data/ directory
// rather than pinned fixtures. Opt-in via `pnpm test:drift`. NOT included in
// the default `pnpm test` run because (a) it requires the cache to be primed
// and (b) flapping on every upstream refresh defeats the purpose of the pin.
//
// Use this when:
// - You suspect upstream has changed (the existing JSON path behaves oddly).
// - Before a `pnpm refresh-fixtures` you want to know what the pin will see.
// - As a periodic sanity check (CI nightly, manual).

const KNOWN_PIPELINE_CATEGORY_KEYS = new Set([
  "agentic", "reasoning", "general", "safety", "knowledge", "other",
  "coding", "instruction_following", "language_understanding",
])
const VALID_EVALUATOR_RELATIONSHIPS = new Set(["first_party", "third_party", "other"])

const modelFiles = listLiveCacheFiles("models")
const evalFiles = listLiveCacheFiles("evals")
// Drift checks are gated by RUN_DRIFT=1 (set by `pnpm test:drift`) so they
// stay out of the default `pnpm test` run. They additionally need a populated
// cache.
const shouldRun = process.env.RUN_DRIFT === "1" && modelFiles.length > 0 && evalFiles.length > 0

describe.skipIf(!shouldRun)(`Tier A drift — live cache contracts (${modelFiles.length} models, ${evalFiles.length} evals)`, () => {
  it("every model_result in every model file carries source_metadata", () => {
    let scanned = 0
    let violations = 0
    const examples: string[] = []
    for (const file of modelFiles) {
      const data = loadLiveCacheFile<HFModelDetail>("models", file)
      for (const { result, path } of walkHierarchyResults<HFEvalModelResult>(data, file)) {
        scanned += 1
        if (!result.source_metadata) {
          violations += 1
          if (examples.length < 5) examples.push(path)
        }
      }
    }
    expect(violations, `${violations}/${scanned} rows lack source_metadata. Examples:\n  ${examples.join("\n  ")}`).toBe(0)
  })

  it("every hierarchy_by_category key across all models is in PIPELINE_CATEGORY_MAP", () => {
    const unknown = new Map<string, number>()
    for (const file of modelFiles) {
      const data = loadLiveCacheFile<HFModelDetail>("models", file)
      for (const key of Object.keys(data.hierarchy_by_category ?? {})) {
        if (!KNOWN_PIPELINE_CATEGORY_KEYS.has(key.toLowerCase())) {
          unknown.set(key, (unknown.get(key) ?? 0) + 1)
        }
      }
    }
    const summary = Array.from(unknown.entries()).map(([k, n]) => `${k}=${n}`).join(", ")
    expect(unknown.size, `Unknown keys (key=count): ${summary}`).toBe(0)
  })

  it("every model_result in every eval-detail carries source_metadata", () => {
    let scanned = 0
    let violations = 0
    const examples: string[] = []
    for (const file of evalFiles) {
      const data = loadLiveCacheFile<HFEvalDetail>("evals", file)
      for (const [metricIdx, metric] of (data.metrics ?? []).entries()) {
        for (const [resultIdx, mr] of (metric.model_results ?? []).entries()) {
          scanned += 1
          if (!mr.source_metadata) {
            violations += 1
            if (examples.length < 5) examples.push(`${file} metrics[${metricIdx}].model_results[${resultIdx}]`)
          }
        }
      }
    }
    expect(violations, `${violations}/${scanned} eval-detail rows lack source_metadata. Examples:\n  ${examples.join("\n  ")}`).toBe(0)
  })

  it("every eval-detail has a non-empty category", () => {
    let violations = 0
    const examples: string[] = []
    for (const file of evalFiles) {
      const data = loadLiveCacheFile<HFEvalDetail>("evals", file)
      if (typeof data.category !== "string" || data.category.length === 0) {
        violations += 1
        if (examples.length < 5) examples.push(file)
      }
    }
    expect(violations, `${violations} eval-details without category. Examples: ${examples.join(", ")}`).toBe(0)
  })

  it("every model card has model_route_id === pipelineSlugify(model_group_id)", () => {
    let violations = 0
    const examples: string[] = []
    const cardsPath = path.resolve(import.meta.dirname, "..", ".cache", "hf-data", "model-cards.json")
    const cards = JSON.parse(fs.readFileSync(cardsPath, "utf8"))
    for (const card of cards) {
      const expected = (card.model_group_id || "").replace(/\//g, "__")
      if (card.model_route_id !== expected) {
        violations += 1
        if (examples.length < 5) examples.push(`${card.model_route_id} (expected ${expected})`)
      }
    }
    expect(violations, `${violations}/${cards.length} mismatches. Examples: ${examples.join(", ")}`).toBe(0)
  })

  it("every source_metadata.evaluator_relationship is in {first_party, third_party, other}", () => {
    const counts = new Map<string, number>()
    for (const file of evalFiles) {
      const data = loadLiveCacheFile<HFEvalDetail>("evals", file)
      for (const metric of data.metrics ?? []) {
        for (const mr of metric.model_results ?? []) {
          const rel = mr.source_metadata?.evaluator_relationship
          if (rel != null && !VALID_EVALUATOR_RELATIONSHIPS.has(rel)) {
            counts.set(rel, (counts.get(rel) ?? 0) + 1)
          }
        }
      }
    }
    const summary = Array.from(counts.entries()).map(([k, n]) => `${k}=${n}`).join(", ")
    expect(counts.size, `Unknown evaluator_relationship values: ${summary}`).toBe(0)
  })

  // Drift check mirroring the contract in pipeline-contract.test.ts: fails
  // loudly if the pipeline starts emitting eval-list display strings in a
  // "<generic-metric> on <benchmark>" / "for scorer" / "model_graded" shape.
  it("eval-list display strings don't match generic-metric-on-benchmark patterns", () => {
    const cachePath = path.resolve(import.meta.dirname, "..", ".cache", "hf-data", "eval-list.json")
    if (!fs.existsSync(cachePath)) {
      throw new Error(`eval-list.json missing from live cache (expected at ${cachePath}); run pnpm cache-hf-data`)
    }
    const data = JSON.parse(fs.readFileSync(cachePath, "utf8")) as { evals?: Array<Record<string, unknown>> }
    const entries = data.evals ?? []
    let violations = 0
    const examples: string[] = []
    for (const entry of entries) {
      const raw =
        ((entry.evaluation_name as string | undefined) ||
          (entry.display_name as string | undefined) ||
          (entry.benchmark_leaf_name as string | undefined) ||
          (entry.eval_summary_id as string | undefined) ||
          ""
        ).trim().toLowerCase()
      if (
        raw.startsWith("accuracy on ") ||
        raw.startsWith("score on ") ||
        raw.includes("for scorer") ||
        raw.includes("model_graded")
      ) {
        violations += 1
        if (examples.length < 5) examples.push(`${entry.eval_summary_id}: ${JSON.stringify(raw)}`)
      }
    }
    expect(violations, `${violations}/${entries.length} eval-list entries match deleted heuristic patterns. Examples: ${examples.join(", ")}`).toBe(0)
  })
})
