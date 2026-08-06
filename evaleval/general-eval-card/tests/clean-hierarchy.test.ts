import { describe, expect, it } from "vitest"

import type { EvalHierarchy, HierarchyBenchmark, HierarchyFamily } from "@/lib/backend-artifacts"
import { cleanHierarchy, isHierarchyCleaned } from "@/lib/clean-hierarchy"

function family(key: string, displayName: string, extra: Partial<HierarchyFamily> = {}): HierarchyFamily {
  return {
    key,
    display_name: displayName,
    category: "General",
    tags: { domains: [], languages: [], tasks: [] },
    evals_count: 0,
    constituent_evaluation_ids: [],
    ...extra,
  } as HierarchyFamily
}

// Minimal benchmark so a family survives cleanHierarchy's "drop emptied
// families" pruning (a benchmark_index appearance is only honoured when its
// family_key still exists after consolidation).
function bench(key: string, displayName = key): HierarchyBenchmark {
  return {
    key,
    display_name: displayName,
    family_id: "",
    is_slice: false,
    is_overall: false,
    has_card: false,
    tags: { domains: [], languages: [], tasks: [] },
    slices: [],
    metrics: [],
    constituent_evaluation_ids: [],
  } as HierarchyBenchmark
}

describe("cleanHierarchy", () => {
  it("filters family-rollup benchmark_index entries (>2 distinct benchmark_keys)", () => {
    const raw: EvalHierarchy = {
      families: [
        family("artificial-analysis", "Artificial Analysis", {
          standalone_benchmarks: [bench("aa-lcr"), bench("aime"), bench("gpqa"), bench("hle"), bench("math-500")],
        }),
        family("llm-stats", "LLM Stats", { standalone_benchmarks: [bench("aime"), bench("math")] }),
        family("vals-ai", "Vals AI", { standalone_benchmarks: [bench("math-500")] }),
      ],
      benchmark_index: [
        // Real cross-family entry (1 distinct benchmark_key) — should keep.
        {
          key: "aime",
          display_name: "AIME",
          appearances: [
            { family_key: "artificial-analysis", benchmark_key: "aime", constituent_evaluation_ids: ["aa%2Faime"], is_canonical_home: false },
            { family_key: "llm-stats", benchmark_key: "aime", constituent_evaluation_ids: ["llm-stats%2Faime"], is_canonical_home: false },
          ],
        },
        // Real 2-key entry — should keep.
        {
          key: "math-500",
          display_name: "MATH-500",
          appearances: [
            { family_key: "vals-ai", benchmark_key: "math-500", constituent_evaluation_ids: ["vals-ai%2Fmath-500"], is_canonical_home: false },
            { family_key: "llm-stats", benchmark_key: "math", constituent_evaluation_ids: ["llm-stats%2Fmath"], is_canonical_home: false },
          ],
        },
        // Family-rollup with 5 distinct benchmark_keys — should drop.
        {
          key: "artificial analysis",
          display_name: "artificial analysis",
          appearances: [
            { family_key: "artificial-analysis", benchmark_key: "aa-lcr", constituent_evaluation_ids: ["aa%2Faa-lcr"], is_canonical_home: false },
            { family_key: "artificial-analysis", benchmark_key: "aime", constituent_evaluation_ids: ["aa%2Faime"], is_canonical_home: false },
            { family_key: "artificial-analysis", benchmark_key: "gpqa", constituent_evaluation_ids: ["aa%2Fgpqa"], is_canonical_home: false },
            { family_key: "artificial-analysis", benchmark_key: "hle", constituent_evaluation_ids: ["aa%2Fhle"], is_canonical_home: false },
            { family_key: "artificial-analysis", benchmark_key: "math-500", constituent_evaluation_ids: ["aa%2Fmath-500"], is_canonical_home: false },
          ],
        },
      ],
    }

    const cleaned = cleanHierarchy(raw)
    const keys = (cleaned.benchmark_index ?? []).map((e) => e.key)
    expect(keys).toContain("aime")
    expect(keys).toContain("math-500")
    expect(keys).not.toContain("artificial analysis")
  })

  it("dedupes (family_key, eval_summary_id) pairs", () => {
    // math-500 sometimes shows up with the same eval_summary_id under
    // both family=math and family=artificial-analysis pointing at the
    // same row. After cleaning, the appearances should have unique
    // pairs per (family_key, eval_summary_id).
    const raw: EvalHierarchy = {
      families: [
        family("artificial-analysis", "Artificial Analysis", { standalone_benchmarks: [bench("aa-keepalive")] }),
        family("vals-ai", "Vals AI", { standalone_benchmarks: [bench("vals-keepalive")] }),
      ],
      benchmark_index: [
        {
          key: "math-500",
          display_name: "MATH-500",
          appearances: [
            { family_key: "artificial-analysis", benchmark_key: "math-500", constituent_evaluation_ids: ["aa%2Fmath-500", "aa%2Fmath-500"], is_canonical_home: false },
            { family_key: "vals-ai", benchmark_key: "math-500", constituent_evaluation_ids: ["vals-ai%2Fmath-500"], is_canonical_home: false },
          ],
        },
      ],
    }

    const cleaned = cleanHierarchy(raw)
    const entry = cleaned.benchmark_index?.[0]
    expect(entry).toBeDefined()
    const aaApp = entry!.appearances.find((a) => a.family_key === "artificial-analysis")
    expect(aaApp?.constituent_evaluation_ids).toEqual(["aa%2Fmath-500"])
  })

  it("drops degenerate entries with only one distinct family", () => {
    const raw: EvalHierarchy = {
      families: [],
      benchmark_index: [
        {
          key: "lonely",
          display_name: "Lonely",
          appearances: [
            { family_key: "fam-a", benchmark_key: "lonely", constituent_evaluation_ids: ["fam-a%2Flonely"], is_canonical_home: false },
            { family_key: "fam-a", benchmark_key: "lonely", constituent_evaluation_ids: ["fam-a%2Flonely-2"], is_canonical_home: false },
          ],
        },
      ],
    }

    const cleaned = cleanHierarchy(raw)
    expect(cleaned.benchmark_index).toEqual([])
  })

  it("decorates derivedTags top-down + bottom-up union", () => {
    const raw: EvalHierarchy = {
      families: [
        family("math-mc", "MATH-MC", {
          benchmarks: [
            {
              key: "level-1",
              display_name: "Level 1",
              family_id: "math-mc",
              is_slice: false,
              is_overall: false,
              has_card: true,
              tags: { domains: [], languages: [], tasks: [] },
              slices: [],
              metrics: [],
            } as never,
          ],
        }),
      ],
    }

    const cleaned = cleanHierarchy(raw)
    const fam = cleaned.families[0]
    // Family inherits tags from its children's union — the "math" tag
    // should propagate up even though the family name itself doesn't
    // resolve to a math entry in categories.json.
    expect(fam.derivedTags).toBeDefined()
    expect(fam.derivedTags?.length).toBeGreaterThan(0)
  })

  it("flattens split families (Fibble Arena, CapArena, AgentHarm) into a single sliced benchmark", () => {
    const raw: EvalHierarchy = {
      families: [
        // Fibble: each split sits in its own composite.
        family("fibble-arena", "Fibble Arena", {
          composites: [
            {
              key: "fibble1-arena",
              display_name: "Fibble1-Arena",
              category: "General",
              tags: { domains: [], languages: [], tasks: [] },
              benchmarks: [
                {
                  key: "fibble1-arena",
                  display_name: "Fibble1-Arena",
                  family_id: "fibble-arena",
                  is_slice: false,
                  is_overall: false,
                  has_card: false,
                  tags: { domains: [], languages: [], tasks: [] },
                  slices: [],
                  metrics: [],
                  constituent_evaluation_ids: ["fibble1-arena%2Ffibble1-arena"],
                },
              ],
            },
            {
              key: "fibble2-arena",
              display_name: "Fibble2 Arena (2 lies)",
              category: "General",
              tags: { domains: [], languages: [], tasks: [] },
              benchmarks: [
                {
                  key: "fibble2-arena",
                  display_name: "Fibble2-Arena",
                  family_id: "fibble-arena",
                  is_slice: false,
                  is_overall: false,
                  has_card: false,
                  tags: { domains: [], languages: [], tasks: [] },
                  slices: [],
                  metrics: [],
                  constituent_evaluation_ids: ["fibble2-arena%2Ffibble2-arena"],
                },
              ],
            },
          ],
        }),
        // CapArena: all splits sit at family level (no composites).
        family("caparena", "CapArena-Auto", {
          benchmarks: [
            {
              key: "caparena-auto-avg",
              display_name: "Caparena-AUTO-AVG",
              family_id: "caparena",
              is_slice: false,
              is_overall: false,
              has_card: false,
              tags: { domains: [], languages: [], tasks: [] },
              slices: [],
              metrics: [],
              constituent_evaluation_ids: ["caparena-auto%2Fcaparena-auto-avg"],
            },
            {
              key: "caparena-vs-gpt-4o",
              display_name: "Caparena-VS-GPT-4o",
              family_id: "caparena",
              is_slice: false,
              is_overall: false,
              has_card: false,
              tags: { domains: [], languages: [], tasks: [] },
              slices: [],
              metrics: [],
              constituent_evaluation_ids: ["caparena-auto%2Fcaparena-vs-gpt-4o"],
            },
          ],
        }),
        // AgentHarm: same family-level layout as CapArena.
        family("agentharm", "agentharm", {
          benchmarks: [
            {
              key: "copyright",
              display_name: "Copyright",
              family_id: "agentharm",
              is_slice: false,
              is_overall: false,
              has_card: false,
              tags: { domains: [], languages: [], tasks: [] },
              slices: [],
              metrics: [],
              constituent_evaluation_ids: ["agentharm%2Fcopyright"],
            },
            {
              key: "cybercrime",
              display_name: "Cybercrime",
              family_id: "agentharm",
              is_slice: false,
              is_overall: false,
              has_card: false,
              tags: { domains: [], languages: [], tasks: [] },
              slices: [],
              metrics: [],
              constituent_evaluation_ids: ["agentharm%2Fcybercrime"],
            },
          ],
        }),
        // Untouched control: a non-split family stays as-is.
        family("helm", "HELM", {
          composites: [
            {
              key: "helm-classic",
              display_name: "HELM Classic",
              category: "General",
              tags: { domains: [], languages: [], tasks: [] },
              benchmarks: [bench("mmlu")],
            },
            {
              key: "helm-safety",
              display_name: "HELM Safety",
              category: "General",
              tags: { domains: [], languages: [], tasks: [] },
              benchmarks: [bench("harm-bench")],
            },
          ],
        }),
      ],
    }

    const cleaned = cleanHierarchy(raw)
    const fams = Object.fromEntries(cleaned.families.map((f) => [f.key, f]))

    // Fibble: the sibling composites fold into ONE standalone benchmark
    // whose slices carry the siblings (plus a bare-stem slice). "slices"
    // mode — no composite survives.
    const fibble = fams["fibble-arena"].standalone_benchmarks ?? []
    expect(fams["fibble-arena"].composites ?? []).toHaveLength(0)
    expect(fibble).toHaveLength(1)
    expect(fibble[0].key).toBe("fibble-arena")
    expect(fibble[0].slices?.map((s) => s.key)).toEqual(
      ["fibble-arena", "fibble1-arena", "fibble2-arena"],
    )

    // CapArena: family-level siblings fold into one standalone benchmark + slices.
    const caparena = fams.caparena.standalone_benchmarks ?? []
    expect(fams.caparena.benchmarks ?? []).toHaveLength(0)
    expect(fams.caparena.composites ?? []).toHaveLength(0)
    expect(caparena[0].key).toBe("caparena-auto")
    expect(caparena[0].slices?.map((s) => s.key)).toEqual(
      ["caparena-auto", "caparena-auto-avg", "caparena-vs-gpt-4o"],
    )

    // AgentHarm: sibling category benchmarks fold in as slices.
    const agentharm = fams.agentharm.standalone_benchmarks ?? []
    expect(fams.agentharm.benchmarks ?? []).toHaveLength(0)
    expect(fams.agentharm.composites ?? []).toHaveLength(0)
    expect(agentharm[0].key).toBe("agentharm")
    expect(agentharm[0].slices?.map((s) => s.key)).toEqual(
      ["agentharm", "copyright", "cybercrime"],
    )

    // Control: HELM (not a split family) keeps its two composites untouched.
    expect(fams.helm.composites).toHaveLength(2)
  })

  it("consolidates AIR-Bench under HELM > helm-air-bench, dropping the standalone family and stripping it from agentharm", () => {
    const raw: EvalHierarchy = {
      families: [
        family("helm", "HELM", {
          constituent_evaluation_ids: ["helm-air-bench%2Fair-bench-2024"],
          composites: [
            {
              key: "helm-air-bench",
              display_name: "HELM AIR-Bench",
              category: "Safety",
              tags: { domains: [], languages: [], tasks: [] },
              benchmarks: [
                {
                  key: "air-bench-2024",
                  display_name: "AIR-Bench 2024",
                  family_id: "air-bench-2024",
                  is_slice: false,
                  is_overall: true,
                  has_card: false,
                  tags: { domains: [], languages: [], tasks: [] },
                  slices: [],
                  metrics: [],
                  constituent_evaluation_ids: ["helm-air-bench%2Fair-bench-2024"],
                },
              ],
            },
          ],
        }),
        family("agentharm", "agentharm", {
          constituent_evaluation_ids: [
            "agentharm%2FCopyright",
            "agentharm%2Fair-bench-2024-13-harassment",
            "agentharm%2Fair-bench-2024-32-fraud",
          ],
          benchmarks: [
            {
              key: "Copyright",
              display_name: "Copyright",
              family_id: "agentharm",
              is_slice: false,
              is_overall: false,
              has_card: false,
              tags: { domains: [], languages: [], tasks: [] },
              slices: [],
              metrics: [],
              constituent_evaluation_ids: ["agentharm%2FCopyright"],
            },
            {
              key: "air-bench-2024-13-harassment",
              display_name: "AIR-Bench-2024-13-Harassment",
              family_id: "air-bench-2024",
              is_slice: false,
              is_overall: false,
              has_card: false,
              tags: { domains: [], languages: [], tasks: [] },
              slices: [],
              metrics: [],
              constituent_evaluation_ids: ["agentharm%2Fair-bench-2024-13-harassment"],
            },
            {
              key: "air-bench-2024-32-fraud",
              display_name: "AIR-Bench-2024-32-Fraud",
              family_id: "air-bench-2024",
              is_slice: false,
              is_overall: false,
              has_card: false,
              tags: { domains: [], languages: [], tasks: [] },
              slices: [],
              metrics: [],
              constituent_evaluation_ids: ["agentharm%2Fair-bench-2024-32-fraud"],
            },
          ],
        }),
        family("air-bench-2024", "Air Bench 2024", {
          constituent_evaluation_ids: [
            "agentharm%2Fair-bench-2024-13-harassment",
            "agentharm%2Fair-bench-2024-32-fraud",
          ],
        }),
      ],
    }

    const cleaned = cleanHierarchy(raw)
    const fams = Object.fromEntries(cleaned.families.map((f) => [f.key, f]))

    // Standalone air-bench-2024 family is gone.
    expect(fams["air-bench-2024"]).toBeUndefined()

    // agentharm no longer carries AIR-Bench rows; the synthetic
    // composite from flattenSplitFamilies should only have Copyright
    // (the lone non-AIR-Bench leaf in this fixture).
    const agentharm = fams.agentharm
    expect(agentharm.constituent_evaluation_ids).not.toContain(
      "agentharm%2Fair-bench-2024-13-harassment",
    )
    expect(agentharm.constituent_evaluation_ids).not.toContain(
      "agentharm%2Fair-bench-2024-32-fraud",
    )
    // agentharm flattens via "slices" mode: the lone remaining leaf
    // (Copyright) folds into the agentharm standalone benchmark as a slice
    // alongside the bare-stem slice — no composite is produced.
    expect(agentharm.composites ?? []).toHaveLength(0)
    expect(agentharm.standalone_benchmarks?.[0].slices?.map((s) => s.key)).toEqual([
      "agentharm",
      "Copyright",
    ])

    // HELM family now lists every AIR-Bench eval id (rollup + the 2
    // agentharm-sourced ones).
    expect(fams.helm.constituent_evaluation_ids).toEqual(
      expect.arrayContaining([
        "helm-air-bench%2Fair-bench-2024",
        "agentharm%2Fair-bench-2024-13-harassment",
        "agentharm%2Fair-bench-2024-32-fraud",
      ]),
    )

    // The helm-air-bench composite's benchmark covers all three.
    const helmAirBench = fams.helm.composites?.find(
      (c) => c.key === "helm-air-bench",
    )
    const airBenchBench = helmAirBench?.benchmarks?.[0]
    expect(airBenchBench?.constituent_evaluation_ids).toEqual(
      expect.arrayContaining([
        "helm-air-bench%2Fair-bench-2024",
        "agentharm%2Fair-bench-2024-13-harassment",
        "agentharm%2Fair-bench-2024-32-fraud",
      ]),
    )
  })

  it("drops a grouping's own *-leaderboard rollup but keeps real members", () => {
    // HELM's `helm-safety` composite ("HELM Safety", a grouping) ships a
    // `helm-safety-leaderboard` benchmark that is the composite's own
    // aggregate — it makes the group show up as both a family and a
    // benchmark. The rollup leaf is dropped; the real members survive.
    const raw: EvalHierarchy = {
      families: [
        family("helm", "HELM", {
          composites: [
            {
              key: "helm-safety",
              display_name: "HELM Safety",
              category: "Safety",
              tags: { domains: [], languages: [], tasks: [] },
              benchmarks: [
                bench("bbq", "BBQ"),
                bench("harmbench", "HarmBench"),
                bench("helm-safety-leaderboard", "HELM-Safety-Leaderboard"),
              ],
            },
          ],
        }),
      ],
    }

    const cleaned = cleanHierarchy(raw)
    const helm = cleaned.families.find((f) => f.key === "helm")!
    const safety = helm.composites!.find((c) => c.key === "helm-safety")!
    const keys = (safety.benchmarks ?? []).map((b) => b.key)
    expect(keys).not.toContain("helm-safety-leaderboard")
    expect(keys).toEqual(expect.arrayContaining(["bbq", "harmbench"]))
  })

  it("keeps a real sibling whose slug matches the family but lacks the -leaderboard suffix", () => {
    // reward-bench's genuine `rewardbench` benchmark slugifies the same as
    // the `reward-bench` family but is a real member, not a rollup. The
    // -leaderboard-only rule must leave it (and its siblings) alone.
    const raw: EvalHierarchy = {
      families: [
        family("foo-bench", "Foo Bench", {
          benchmarks: [bench("foobench", "Foo Bench"), bench("foobench-2", "Foo Bench 2")],
        }),
      ],
    }

    const cleaned = cleanHierarchy(raw)
    const fam = cleaned.families.find((f) => f.key === "foo-bench")!
    const keys = [...(fam.benchmarks ?? []), ...(fam.standalone_benchmarks ?? [])].map((b) => b.key)
    expect(keys).toEqual(expect.arrayContaining(["foobench", "foobench-2"]))
  })

  it("drops a family-level rollup and preserves its eval ids on the family", () => {
    const raw: EvalHierarchy = {
      families: [
        family("widget-bench", "Widget Bench", {
          constituent_evaluation_ids: [
            "widget-bench%2Fwidget-bench-leaderboard",
            "widget-bench%2Fwidget-a",
          ],
          standalone_benchmarks: [
            bench("widget-bench-leaderboard", "Widget Bench Leaderboard"),
            bench("widget-a", "Widget A"),
          ],
        }),
      ],
    }

    const cleaned = cleanHierarchy(raw)
    const fam = cleaned.families.find((f) => f.key === "widget-bench")!
    const keys = [...(fam.benchmarks ?? []), ...(fam.standalone_benchmarks ?? [])].map((b) => b.key)
    // Rollup leaf gone, real member kept.
    expect(keys).not.toContain("widget-bench-leaderboard")
    expect(keys).toContain("widget-a")
    // …but the rollup's eval id stays on the family so it still resolves.
    expect(fam.constituent_evaluation_ids).toContain(
      "widget-bench%2Fwidget-bench-leaderboard",
    )
  })

  it("never empties a group: a lone *-leaderboard bench is kept", () => {
    const raw: EvalHierarchy = {
      families: [
        family("solo", "Solo", {
          composites: [
            {
              key: "solo-grp",
              display_name: "Solo Grp",
              category: "General",
              tags: { domains: [], languages: [], tasks: [] },
              benchmarks: [bench("solo-grp-leaderboard", "Solo Grp Leaderboard")],
            },
          ],
        }),
      ],
    }

    const cleaned = cleanHierarchy(raw)
    const grp = cleaned.families
      .find((f) => f.key === "solo")
      ?.composites?.find((c) => c.key === "solo-grp")
    expect(grp?.benchmarks?.map((b) => b.key)).toEqual(["solo-grp-leaderboard"])
  })

  it("is idempotent: re-applying produces identical output", () => {
    const raw: EvalHierarchy = {
      families: [family("aime", "AIME")],
      benchmark_index: [
        {
          key: "aime",
          display_name: "AIME",
          appearances: [
            { family_key: "fam-a", benchmark_key: "aime", constituent_evaluation_ids: ["fam-a%2Faime"], is_canonical_home: false },
            { family_key: "fam-b", benchmark_key: "aime", constituent_evaluation_ids: ["fam-b%2Faime"], is_canonical_home: false },
          ],
        },
      ],
    }

    const once = cleanHierarchy(raw)
    expect(isHierarchyCleaned(once)).toBe(true)
    const twice = cleanHierarchy(once)
    expect(twice).toBe(once)
  })
})
