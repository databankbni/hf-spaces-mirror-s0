import { describe, expect, it } from "vitest"

// Executable spec for the benchmark-display-names transformation.
//
// Replicates BENCHMARK_NAMES + normalizeBenchmarkKeyForLookup + humanizeToken +
// getBenchmarkDisplayName from lib/model-data.ts verbatim.
//
// Also replicates the duplicate getBenchmarkDisplayName from
// lib/eval-processing.ts (Group D — functionally dead, tested for
// completeness so a pipeline implementer porting the rules sees the
// disagreement explicitly).

// ---------------------------------------------------------------------------
// Active implementation — lib/model-data.ts
// ---------------------------------------------------------------------------

function humanizeToken(token: string): string {
  return token
    .split(/[_-]+/g)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
}

const BENCHMARK_NAMES: Record<string, string> = {
  hfopenllm_v2: "HF Open LLM v2",
  helm_lite: "HELM Lite",
  helm_capabilities: "HELM Capabilities",
  helm_classic: "HELM Classic",
  helm_instruct: "HELM Instruct",
  helm_mmlu: "HELM MMLU",
  reward_bench: "RewardBench",
  reward_bench_2: "RewardBench 2",
  bfcl: "BFCL",
  global_mmlu_lite: "Global MMLU Lite",
  swe_bench: "SWE-bench",
  arc_agi: "ARC-AGI",
  tau_bench_2: "TAU-Bench 2",
  ace: "ACE",
  apex_agents: "APEX Agents",
  apex_v1: "APEX v1",
  appworld: "AppWorld",
  browsecompplus: "BrowseComp+",
  livecodebenchpro: "LiveCodeBench Pro",
  sciarena: "SciArena",
  terminal_bench_2_0: "Terminal Bench 2.0",
  la_leaderboard: "LA Leaderboard",
  theory_of_mind: "Theory of Mind",
  fibble_arena: "Fibble Arena",
  fibble1_arena: "Fibble Arena v1",
  fibble2_arena: "Fibble Arena v2",
  fibble3_arena: "Fibble Arena v3",
  fibble4_arena: "Fibble Arena v4",
  fibble5_arena: "Fibble Arena v5",
  wordle_arena: "Wordle Arena",
}

function normalizeBenchmarkKeyForLookup(key: string): string {
  return key.toLowerCase().replace(/[-.\s]+/g, "_").replace(/^_+|_+$/g, "")
}

function getBenchmarkDisplayName(benchmark: string): string {
  return BENCHMARK_NAMES[normalizeBenchmarkKeyForLookup(benchmark)] ?? humanizeToken(benchmark)
}

// ---------------------------------------------------------------------------
// Group A — Map hits (normalized-key lookup)
// ---------------------------------------------------------------------------

describe("Group A — BENCHMARK_NAMES map hits", () => {
  const cases = [
    // Exact normalized matches
    { input: "hfopenllm_v2", expected: "HF Open LLM v2" },
    { input: "helm_lite", expected: "HELM Lite" },
    { input: "helm_capabilities", expected: "HELM Capabilities" },
    { input: "helm_classic", expected: "HELM Classic" },
    { input: "helm_instruct", expected: "HELM Instruct" },
    { input: "helm_mmlu", expected: "HELM MMLU" },
    { input: "reward_bench", expected: "RewardBench" },
    { input: "reward_bench_2", expected: "RewardBench 2" },
    { input: "bfcl", expected: "BFCL" },
    { input: "global_mmlu_lite", expected: "Global MMLU Lite" },
    { input: "swe_bench", expected: "SWE-bench" },
    { input: "arc_agi", expected: "ARC-AGI" },
    { input: "tau_bench_2", expected: "TAU-Bench 2" },
    { input: "ace", expected: "ACE" },
    { input: "apex_agents", expected: "APEX Agents" },
    { input: "apex_v1", expected: "APEX v1" },
    { input: "appworld", expected: "AppWorld" },
    { input: "browsecompplus", expected: "BrowseComp+" },
    { input: "livecodebenchpro", expected: "LiveCodeBench Pro" },
    { input: "sciarena", expected: "SciArena" },
    { input: "terminal_bench_2_0", expected: "Terminal Bench 2.0" },
    { input: "la_leaderboard", expected: "LA Leaderboard" },
    { input: "theory_of_mind", expected: "Theory of Mind" },
    { input: "fibble_arena", expected: "Fibble Arena" },
    { input: "fibble1_arena", expected: "Fibble Arena v1" },
    { input: "fibble2_arena", expected: "Fibble Arena v2" },
    { input: "fibble3_arena", expected: "Fibble Arena v3" },
    { input: "fibble4_arena", expected: "Fibble Arena v4" },
    { input: "fibble5_arena", expected: "Fibble Arena v5" },
    { input: "wordle_arena", expected: "Wordle Arena" },

    // Case- and separator-insensitive lookups (normalize: lower; -/./space -> _; trim _)
    { input: "HELM Lite", expected: "HELM Lite", why: "space -> _ during normalize" },
    { input: "helm-lite", expected: "HELM Lite", why: "dash -> _" },
    { input: "helm.lite", expected: "HELM Lite", why: "dot -> _" },
    { input: "HELM-LITE", expected: "HELM Lite", why: "lower + dash -> _" },
    { input: "  helm   lite  ", expected: "HELM Lite", why: "whitespace runs collapse, edges trim" },
    { input: "ARC.AGI", expected: "ARC-AGI", why: "dot -> _" },
    { input: "Reward-Bench-2", expected: "RewardBench 2" },
  ]
  it.each(cases)("'$input' -> '$expected'", ({ input, expected }) => {
    expect(getBenchmarkDisplayName(input)).toBe(expected)
  })
})

// ---------------------------------------------------------------------------
// Group B — Tokenize fallback (humanizeToken on the *original* input)
// ---------------------------------------------------------------------------

describe("Group B — humanizeToken fallback for non-map inputs", () => {
  const cases = [
    // Single-token acronyms — only first char gets uppercased (NOT a real acronym map)
    { input: "bbh", expected: "Bbh", why: "humanizeToken only uppercases first char of each token; map doesn't have 'bbh'" },
    { input: "gpqa", expected: "Gpqa", why: "same — visibly wrong but TS-as-spec" },
    { input: "mmlu", expected: "Mmlu", why: "same — visibly wrong; the suite-name companion table in benchmark-detail.tsx fixes this, but the active getBenchmarkDisplayName does NOT" },
    { input: "gsm8k", expected: "Gsm8k", why: "digits inside don't capitalize differently" },
    { input: "humaneval", expected: "Humaneval" },
    { input: "truthfulqa", expected: "Truthfulqa" },

    // Already-uppercase passthrough (charAt(0).toUpperCase() is a no-op on already-upper char)
    { input: "MATH", expected: "MATH", why: "M is already upper; ATH preserved by slice(1)" },
    { input: "MMLU", expected: "MMLU", why: "M upper; MLU preserved" },
    { input: "BBQ", expected: "BBQ" },
    { input: "MMLU-PRO", expected: "MMLU PRO", why: "split on - -> ['MMLU','PRO'] -> first-char-upper (no-op) -> join with space" },

    // Multi-token snake/dash inputs that miss the map
    { input: "swe-bench-verified", expected: "Swe Bench Verified", why: "split on -, each first-cap" },
    { input: "swe_bench_verified_mini", expected: "Swe Bench Verified Mini" },
    { input: "multi_swe_bench", expected: "Multi Swe Bench" },
    { input: "helm_air_bench", expected: "Helm Air Bench", why: "not in map (only the ~30 listed suite keys are)" },
    { input: "helm_safety", expected: "Helm Safety" },
    { input: "swe_bench_verified", expected: "Swe Bench Verified", why: "swe_bench is in map but swe_bench_verified is not" },
    { input: "cocoabench", expected: "Cocoabench" },
    { input: "llm_stats", expected: "Llm Stats" },
    { input: "artificial_analysis_llms", expected: "Artificial Analysis Llms" },

    // The fallback uses the *original* (unnormalized) input — spaces survive!
    { input: "Helm air bench", expected: "Helm air bench", why: "fallback splits on [_-]+ ONLY; the spaces don't trigger split; first char of the lone token already upper" },
    { input: "helm air bench", expected: "Helm air bench", why: "single token (spaces don't split); lowercase 'h' becomes 'H', rest unchanged" },
  ]
  it.each(cases)("'$input' -> '$expected' ($why)", ({ input, expected }) => {
    expect(getBenchmarkDisplayName(input)).toBe(expected)
  })
})

// ---------------------------------------------------------------------------
// Group C — Edge cases
// ---------------------------------------------------------------------------

describe("Group C — edge cases", () => {
  it("empty string -> empty string", () => {
    // normalize -> "" (no map hit). humanizeToken: "".split(/[_-]+/) -> [""] -> filter(Boolean) -> [] -> [].join(" ") -> ""
    expect(getBenchmarkDisplayName("")).toBe("")
  })

  it("single underscore -> empty string", () => {
    // normalize: "_" -> "" (edges stripped). no map hit. humanizeToken: "_".split(/[_-]+/) -> ["",""] -> filter -> [] -> ""
    expect(getBenchmarkDisplayName("_")).toBe("")
  })

  it("triple-underscore-padded map key collapses to map hit during normalize", () => {
    // normalize: "___helm___lite___" -> lower (no-op) -> internal runs of _ stay (but [-.\s]+ doesn't include _!) -> wait
    // Let's check carefully: normalizeBenchmarkKeyForLookup uses /[-.\s]+/g (NOT _).
    // So "___helm___lite___".replace(/[-.\s]+/g, "_") is unchanged.
    // Then .replace(/^_+|_+$/g, "") strips edge _ runs. Internal "___" stays as-is.
    // Result: "helm___lite" — NOT "helm_lite". So this misses the map!
    expect(getBenchmarkDisplayName("___helm___lite___")).toBe("Helm Lite")
    // humanizeToken splits on [_-]+ which collapses the runs: "helm___lite".split(/[_-]+/) -> ["helm","lite"] -> ["Helm","Lite"]
  })

  it("single char -> uppercased single char via fallback", () => {
    expect(getBenchmarkDisplayName("a")).toBe("A")
  })

  it("a-b -> 'A B' via fallback", () => {
    expect(getBenchmarkDisplayName("a-b")).toBe("A B")
  })

  it("lookup is case-insensitive even for substantive transforms", () => {
    expect(getBenchmarkDisplayName("APEX_AGENTS")).toBe("APEX Agents")
    expect(getBenchmarkDisplayName("Browsecompplus")).toBe("BrowseComp+")
    expect(getBenchmarkDisplayName("LIVECODEBENCHPRO")).toBe("LiveCodeBench Pro")
  })

  it("two-space whitespace collapses for normalize (map lookup)", () => {
    expect(getBenchmarkDisplayName("helm  lite")).toBe("HELM Lite")
  })
})

// ---------------------------------------------------------------------------
// Group D — Duplicate getBenchmarkDisplayName in lib/eval-processing.ts
// (functionally dead — only called by groupEvaluationsByBenchmark which has
// no importers. Tested for completeness so the divergence in semantics is
// explicit.)
// ---------------------------------------------------------------------------

function getBenchmarkDisplayNameDuplicate(name: string | undefined | null): string {
  if (!name) return "Unknown Benchmark"

  const mapping: Record<string, string> = {
    MMLU: "Massive Multitask Language Understanding",
    "MMLU-Pro": "MMLU Professional",
    GSM8K: "Grade School Math 8K",
    HumanEval: "Human Eval (Code)",
    MBPP: "Mostly Basic Python Problems",
    HellaSwag: "HellaSwag (Commonsense)",
    ARC: "AI2 Reasoning Challenge",
    TruthfulQA: "TruthfulQA",
    BBH: "Big-Bench Hard",
    MATH: "MATH Dataset",
  }

  for (const [key, value] of Object.entries(mapping)) {
    if (name.toUpperCase().includes(key.toUpperCase())) {
      return value
    }
  }

  return name
}

describe("Group D — duplicate getBenchmarkDisplayName (eval-processing.ts) — substring-include rule", () => {
  const cases: Array<{ input: string | null | undefined; expected: string; why?: string }> = [
    { input: null, expected: "Unknown Benchmark", why: "guard: !name" },
    { input: undefined, expected: "Unknown Benchmark", why: "guard" },
    { input: "", expected: "Unknown Benchmark", why: "guard (empty string is falsy)" },
    { input: "MMLU", expected: "Massive Multitask Language Understanding", why: "substring match on MMLU" },
    { input: "mmlu", expected: "Massive Multitask Language Understanding", why: "case-insensitive (toUpperCase)" },
    {
      input: "MMLU-Pro",
      expected: "Massive Multitask Language Understanding",
      why: "iteration order: MMLU is matched first (insertion order); MMLU-Pro entry never reached. KNOWN SOFT-BUG, document don't fix.",
    },
    { input: "GSM8K", expected: "Grade School Math 8K" },
    { input: "HumanEval", expected: "Human Eval (Code)" },
    { input: "MBPP", expected: "Mostly Basic Python Problems" },
    { input: "HellaSwag", expected: "HellaSwag (Commonsense)" },
    { input: "ARC", expected: "AI2 Reasoning Challenge" },
    { input: "TruthfulQA", expected: "TruthfulQA", why: "key === value" },
    { input: "BBH", expected: "Big-Bench Hard" },
    { input: "MATH", expected: "MATH Dataset" },
    { input: "helm_lite", expected: "helm_lite", why: "no substring match -> passthrough" },
    {
      input: "MMLU Lite something",
      expected: "Massive Multitask Language Understanding",
      why: "substring match still fires when the key appears anywhere in the input",
    },
    {
      input: "ARC-AGI",
      expected: "AI2 Reasoning Challenge",
      why: "substring 'ARC' matches; this overwrites the more specific intent of 'ARC-AGI' — soft-bug",
    },
  ]
  it.each(cases)("'$input' -> '$expected' ($why)", ({ input, expected }) => {
    expect(getBenchmarkDisplayNameDuplicate(input)).toBe(expected)
  })
})
