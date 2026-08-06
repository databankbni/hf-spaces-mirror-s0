import { describe, expect, it, vi } from "vitest"

import type { EvalHierarchy } from "../lib/backend-artifacts"
import { adaptEvalHierarchy } from "../lib/hf-data"

// adaptEvalHierarchy is a passthrough validator — the producer's
// write_hierarchy() emits the v3 family-rooted tree directly, so the
// adapter no longer synthesises legacy shapes. These tests confirm the
// passthrough preserves data and that the schema_version warning
// fires for unknown versions.

describe("adaptEvalHierarchy (passthrough)", () => {
  it("returns the v3 hierarchy unchanged", () => {
    const raw: EvalHierarchy = {
      schema_version: "v3.hierarchy.1",
      stats: {
        family_count: 1,
        composite_count: 1,
        benchmark_count: 2,
        slice_count: 0,
        metric_count: 2,
        metric_rows_scanned: 2,
      },
      families: [
        {
          key: "gpqa",
          display_name: "GPQA family",
          category: "knowledge",
          tags: { domains: ["reasoning"], languages: [], tasks: ["qa"] },
          evals_count: 4,
          constituent_evaluation_ids: ["wasp%2Fgpqa", "wasp%2Fgpqa-diamond"],
          benchmarks: [
            {
              key: "gpqa",
              display_name: "GPQA",
              family_id: "gpqa",
              is_slice: false,
              is_overall: true,
              is_primary: true,
              has_card: false,
              tags: { domains: ["reasoning"], languages: [], tasks: ["qa"] },
              metrics: [{ key: "accuracy", display_name: "Accuracy" }],
              slices: [],
              constituent_evaluation_ids: ["wasp%2Fgpqa"],
            },
            {
              key: "gpqa-diamond",
              display_name: "GPQA Diamond",
              family_id: "gpqa",
              is_slice: false,
              is_overall: false,
              is_primary: false,
              has_card: false,
              tags: { domains: ["reasoning"], languages: [], tasks: ["qa"] },
              metrics: [{ key: "accuracy", display_name: "Accuracy" }],
              slices: [],
              constituent_evaluation_ids: ["wasp%2Fgpqa-diamond"],
            },
          ],
        },
      ],
    }

    const adapted = adaptEvalHierarchy(raw)

    expect(adapted).toBe(raw) // passthrough: same reference
    expect(adapted.families).toHaveLength(1)
    expect(adapted.families[0].benchmarks).toHaveLength(2)
    expect(adapted.families[0].benchmarks?.map((b) => b.key)).toEqual([
      "gpqa",
      "gpqa-diamond",
    ])
  })

  it("returns a safe empty shape on null/undefined input", () => {
    expect(adaptEvalHierarchy(null as unknown as EvalHierarchy)).toEqual({
      families: [],
    })
  })

  it("warns on unknown schema_version but still passes through", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const raw: EvalHierarchy = {
      schema_version: "v2.hierarchy.999",
      families: [],
    }
    const adapted = adaptEvalHierarchy(raw)
    expect(adapted).toBe(raw)
    expect(warn).toHaveBeenCalledOnce()
    warn.mockRestore()
  })

  it("does not warn when schema_version matches v3.hierarchy.*", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    adaptEvalHierarchy({
      schema_version: "v3.hierarchy.1",
      families: [],
    })
    expect(warn).not.toHaveBeenCalled()
    warn.mockRestore()
  })
})
