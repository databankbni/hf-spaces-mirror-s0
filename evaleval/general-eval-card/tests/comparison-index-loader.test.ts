import { mkdir, mkdtemp, rm, writeFile } from "fs/promises"
import os from "os"
import path from "path"

import { describe, expect, it } from "vitest"

import type { ComparisonIndex } from "../lib/backend-artifacts"
import { assertComparisonIndexShape } from "../lib/sidecars"

// Shared fixture: a comparison-index in the current (v3) shape. Tests
// mutate copies of this to exercise contract assertions.
const validFixture: ComparisonIndex = {
  generated_at: "2026-05-04T00:00:00Z",
  config_version: 2,
  metric_group_order: ["capability", "robustness", "efficiency", "cost", "latency", "rank", "other"],
  evals: {
    "helm-classic%2Fmmlu": {
      evaluation_id: "helm-classic%2Fmmlu",
      benchmark_id: "mmlu",
      family_id: "helm",
      family_display_name: "HELM",
      composite_slug: "helm-classic",
      composite_display_name: "HELM Classic",
      parent_benchmark_id: null,
      display_name: "MMLU",
      category: "Knowledge",
      is_slice: false,
      is_summary_score: false,
      summary_score_for: null,
      metrics: [],
    },
    "helm-classic%2Fmmlu%2Fanatomy": {
      evaluation_id: "helm-classic%2Fmmlu%2Fanatomy",
      benchmark_id: "mmlu",
      family_id: "helm",
      family_display_name: "HELM",
      composite_slug: "helm-classic",
      composite_display_name: "HELM Classic",
      parent_benchmark_id: "mmlu",
      display_name: "MMLU Anatomy",
      category: "Knowledge",
      is_slice: true,
      is_summary_score: false,
      summary_score_for: null,
      metrics: [],
    },
  },
  by_model: {},
}

describe("assertComparisonIndexShape", () => {
  it("accepts entries with family_id present", () => {
    expect(() => assertComparisonIndexShape(validFixture)).not.toThrow()
  })

  it("accepts the new parent_benchmark_id field on slice entries", () => {
    const sliceEntry = validFixture.evals["helm-classic%2Fmmlu%2Fanatomy"]
    expect(sliceEntry.parent_benchmark_id).toBe("mmlu")
    expect(sliceEntry.is_slice).toBe(true)
  })

  it("rejects entries that are missing family_id", () => {
    const broken = JSON.parse(JSON.stringify(validFixture)) as ComparisonIndex
    delete (broken.evals["helm-classic%2Fmmlu"] as unknown as Record<string, unknown>).family_id

    expect(() => assertComparisonIndexShape(broken)).toThrow(
      /missing family_id/,
    )
  })
})

describe("fetchComparisonIndex (v2 sidecar)", () => {
  it("validates the loaded sidecar against the contract", async () => {
    const snapshotDir = await mkdtemp(path.join(os.tmpdir(), "eval-card-cmp-"))
    const previousBackend = process.env.DATA_BACKEND
    const previousSnapshotUrl = process.env.SNAPSHOT_URL

    try {
      await mkdir(snapshotDir, { recursive: true })
      const broken = JSON.parse(JSON.stringify(validFixture)) as ComparisonIndex
      delete (broken.evals["helm-classic%2Fmmlu"] as unknown as Record<string, unknown>).family_id
      await writeFile(
        path.join(snapshotDir, "comparison-index.json"),
        JSON.stringify(broken),
      )

      process.env.DATA_BACKEND = "v2"
      process.env.SNAPSHOT_URL = `file://${snapshotDir}`

      const sidecars = await import("../lib/sidecars")
      sidecars.resetSidecarCacheForTests()

      await expect(sidecars.fetchComparisonIndex()).rejects.toThrow(
        /missing family_id/,
      )
    } finally {
      const sidecars = await import("../lib/sidecars")
      sidecars.resetSidecarCacheForTests()
      if (previousBackend == null) {
        delete process.env.DATA_BACKEND
      } else {
        process.env.DATA_BACKEND = previousBackend
      }
      if (previousSnapshotUrl == null) {
        delete process.env.SNAPSHOT_URL
      } else {
        process.env.SNAPSHOT_URL = previousSnapshotUrl
      }
      await rm(snapshotDir, { recursive: true, force: true })
    }
  })
})
