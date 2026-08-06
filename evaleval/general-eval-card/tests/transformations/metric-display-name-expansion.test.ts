import { describe, expect, it } from "vitest"

// Executable spec for the metric-display-name-expansion transformation.
//
// Replicates two TS transformations verbatim:
//   - GENERIC_EVALUATION_NAMES + getEvaluationDisplayName + getBenchmarkName
//     from lib/eval-processing.ts
//   - prefersBenchmarkName (inline) from lib/model-data.ts

// ---------------------------------------------------------------------------
// Replicas
// ---------------------------------------------------------------------------

const GENERIC_EVALUATION_NAMES = new Set([
  "score",
  "accuracy",
  "mean win rate",
  "exact match",
  "f1",
  "pass@1",
])

type SourceObj = { dataset_name?: string; [k: string]: unknown }
type EvalLike = {
  benchmark?: string
  evaluation_id?: string
  source_data?: SourceObj | string[] | undefined
}
type ResultLike = {
  evaluation_name: string
  source_data?: SourceObj | string[] | undefined
}

function getBenchmarkName(evaluation: EvalLike, result?: ResultLike): string {
  const resultSource = result?.source_data
  if (resultSource && !Array.isArray(resultSource) && resultSource.dataset_name) {
    return resultSource.dataset_name
  }
  if (evaluation.benchmark) return evaluation.benchmark
  if (
    evaluation.source_data &&
    !Array.isArray(evaluation.source_data) &&
    evaluation.source_data.dataset_name
  ) {
    return evaluation.source_data.dataset_name
  }
  return result?.evaluation_name ?? evaluation.evaluation_id ?? ""
}

function getEvaluationDisplayName(evaluation: EvalLike, result: ResultLike): string {
  const benchmarkName = getBenchmarkName(evaluation, result)
  const metricName = result.evaluation_name.trim()
  if (metricName === benchmarkName) return metricName
  if (GENERIC_EVALUATION_NAMES.has(metricName.toLowerCase())) {
    return `${benchmarkName} - ${metricName}`
  }
  return metricName
}

type EvalListEntry = {
  evaluation_name?: string
  display_name?: string
  benchmark_leaf_name?: string
  eval_summary_id?: string
  benchmark_parent_name?: string
  benchmark?: string
}

// Replica that returns the entry's final `evaluation_name` after the
// prefersBenchmarkName decision. We pass in the resolved `benchmarkDisplayName`
// directly to keep the test independent of getBenchmarkDisplayName (which is a
// separate transformation, spec'd elsewhere).
function applyPrefersBenchmarkName(
  entry: EvalListEntry,
  benchmarkDisplayName: string,
): { rawDisplayName: string; prefersBenchmarkName: boolean; output: string } {
  const rawDisplayName =
    entry.evaluation_name ||
    entry.display_name ||
    entry.benchmark_leaf_name ||
    entry.eval_summary_id ||
    ""
  const normalizedDisplayName = rawDisplayName.trim().toLowerCase()
  const prefersBenchmarkName =
    Boolean(benchmarkDisplayName) &&
    (normalizedDisplayName.startsWith("accuracy on ") ||
      normalizedDisplayName.startsWith("score on ") ||
      normalizedDisplayName.includes("for scorer") ||
      normalizedDisplayName.includes("model_graded"))
  return {
    rawDisplayName,
    prefersBenchmarkName,
    output: prefersBenchmarkName ? benchmarkDisplayName : rawDisplayName,
  }
}

// ---------------------------------------------------------------------------
// Group A — getEvaluationDisplayName: generic name expansion
// ---------------------------------------------------------------------------

describe("Group A — getEvaluationDisplayName: generic name expansion", () => {
  const cases = [
    { benchmark: "MMLU", metric: "Accuracy", expected: "MMLU - Accuracy" },
    { benchmark: "GSM8K", metric: "accuracy", expected: "GSM8K - accuracy" },
    { benchmark: "MATH", metric: "EXACT MATCH", expected: "MATH - EXACT MATCH" },
    { benchmark: "RewardBench", metric: "Mean Win Rate", expected: "RewardBench - Mean Win Rate" },
    { benchmark: "HumanEval", metric: "pass@1", expected: "HumanEval - pass@1" },
    { benchmark: "SuperGLUE", metric: "f1", expected: "SuperGLUE - f1" },
    { benchmark: "OpenBookQA", metric: "Score", expected: "OpenBookQA - Score" },
  ]
  it.each(cases)("benchmark='$benchmark' metric='$metric' → '$expected'", ({ benchmark, metric, expected }) => {
    const evaluation: EvalLike = { benchmark }
    const result: ResultLike = { evaluation_name: metric }
    expect(getEvaluationDisplayName(evaluation, result)).toBe(expected)
  })
})

// ---------------------------------------------------------------------------
// Group B — getEvaluationDisplayName: passthrough (non-generic)
// ---------------------------------------------------------------------------

describe("Group B — getEvaluationDisplayName: passthrough for non-generic metric names", () => {
  const cases = [
    {
      desc: "metricName === benchmarkName → return metric (early return; expansion never considered)",
      benchmark: "MMLU",
      metric: "MMLU",
      expected: "MMLU",
    },
    { desc: "non-generic metric → passthrough", benchmark: "MMLU", metric: "BLEU", expected: "BLEU" },
    {
      desc: "non-generic distinct from benchmark → passthrough",
      benchmark: "RewardBench",
      metric: "Chat Hard",
      expected: "Chat Hard",
    },
    {
      desc: "substring of generic but not equal → passthrough",
      benchmark: "MMLU",
      metric: "accuracy_strict",
      expected: "accuracy_strict",
    },
    {
      desc: "trailing whitespace on metric is .trim()'d before set lookup → expansion fires",
      benchmark: "MMLU",
      metric: "Accuracy ",
      expected: "MMLU - Accuracy",
    },
    {
      desc: "leading + trailing whitespace trimmed",
      benchmark: "MMLU",
      metric: "   accuracy   ",
      expected: "MMLU - accuracy",
    },
  ]
  it.each(cases)("$desc", ({ benchmark, metric, expected }) => {
    const evaluation: EvalLike = { benchmark }
    const result: ResultLike = { evaluation_name: metric }
    expect(getEvaluationDisplayName(evaluation, result)).toBe(expected)
  })
})

// ---------------------------------------------------------------------------
// Group C — getEvaluationDisplayName: getBenchmarkName precedence chain
// ---------------------------------------------------------------------------

describe("Group C — getBenchmarkName precedence chain (5 steps)", () => {
  it("step 1: result.source_data.dataset_name wins over evaluation.benchmark", () => {
    const evaluation: EvalLike = { benchmark: "reward-bench" }
    const result: ResultLike = {
      evaluation_name: "Score",
      source_data: { dataset_name: "RewardBench" },
    }
    expect(getBenchmarkName(evaluation, result)).toBe("RewardBench")
    expect(getEvaluationDisplayName(evaluation, result)).toBe("RewardBench - Score")
  })

  it("array source_data is skipped → falls to evaluation.benchmark", () => {
    const evaluation: EvalLike = { benchmark: "reward-bench" }
    const result: ResultLike = {
      evaluation_name: "Chat Hard",
      source_data: ["url1", "url2"],
    }
    expect(getBenchmarkName(evaluation, result)).toBe("reward-bench")
  })

  it("step 2: evaluation.benchmark when result.source_data missing", () => {
    const evaluation: EvalLike = { benchmark: "reward-bench" }
    const result: ResultLike = { evaluation_name: "Foo" }
    expect(getBenchmarkName(evaluation, result)).toBe("reward-bench")
  })

  it("step 3: evaluation.source_data.dataset_name when benchmark is empty string (falsy)", () => {
    const evaluation: EvalLike = { benchmark: "", source_data: { dataset_name: "MMLU" } }
    const result: ResultLike = { evaluation_name: "Foo" }
    expect(getBenchmarkName(evaluation, result)).toBe("MMLU")
  })

  it("step 4: result.evaluation_name when nothing else available", () => {
    const evaluation: EvalLike = {}
    const result: ResultLike = { evaluation_name: "Foo" }
    expect(getBenchmarkName(evaluation, result)).toBe("Foo")
  })

  it("step 5: evaluation.evaluation_id final fallback (when no result)", () => {
    const evaluation: EvalLike = { evaluation_id: "id-123" }
    expect(getBenchmarkName(evaluation, undefined)).toBe("id-123")
  })
})

// ---------------------------------------------------------------------------
// Group D — prefersBenchmarkName: heuristic matches
// ---------------------------------------------------------------------------

describe("Group D — prefersBenchmarkName: heuristic matches", () => {
  const benchmarkDisplayName = "MMLU"
  const cases = [
    { evaluation_name: "accuracy on subset_humanities", reason: "startsWith('accuracy on ')" },
    { evaluation_name: "Accuracy On SubsetHumanities", reason: "lowercased before startsWith" },
    { evaluation_name: "score on test_set", reason: "startsWith('score on ')" },
    { evaluation_name: "xyz for scorer judge_v2", reason: "includes('for scorer') (any position)" },
    { evaluation_name: "for scorer xyz at start", reason: "includes('for scorer') matches at start" },
    { evaluation_name: "something model_graded thing", reason: "includes('model_graded')" },
    { evaluation_name: "model_graded", reason: "substring match works on whole string" },
  ]
  it.each(cases)("'$evaluation_name' → 'MMLU' ($reason)", ({ evaluation_name }) => {
    const result = applyPrefersBenchmarkName({ evaluation_name }, benchmarkDisplayName)
    expect(result.prefersBenchmarkName).toBe(true)
    expect(result.output).toBe("MMLU")
  })
})

// ---------------------------------------------------------------------------
// Group E — prefersBenchmarkName: passthrough (non-matching)
// ---------------------------------------------------------------------------

describe("Group E — prefersBenchmarkName: passthrough for non-matching display names", () => {
  const benchmarkDisplayName = "MMLU"
  const cases = [
    { evaluation_name: "MMLU - Accuracy", reason: "no token matches" },
    { evaluation_name: "Accuracy", reason: "bare 'accuracy' fails startsWith('accuracy on ')" },
    {
      evaluation_name: "accuracy onset",
      reason: "'accuracy on ' (trailing space) does not match 'accuracy onset' (no space at pos 11)",
    },
    {
      evaluation_name: "score onyx",
      reason: "'score on ' (trailing space) does not match 'score onyx'",
    },
    {
      evaluation_name: "Model Graded Eval",
      reason: "model_graded uses underscore; 'model graded' (space) lowercased does not contain 'model_graded'",
    },
    {
      evaluation_name: "accuracy_for_scorer",
      reason: "'for scorer' uses space; 'for_scorer' does not match",
    },
    {
      evaluation_name: "Scorer based eval",
      reason: "must contain literal 'for scorer', not just 'scorer'",
    },
    { evaluation_name: "BBH", reason: "none of the four conditions match" },
  ]
  it.each(cases)("'$evaluation_name' passes through unchanged ($reason)", ({ evaluation_name }) => {
    const result = applyPrefersBenchmarkName({ evaluation_name }, benchmarkDisplayName)
    expect(result.prefersBenchmarkName).toBe(false)
    expect(result.output).toBe(evaluation_name)
  })
})

// ---------------------------------------------------------------------------
// Group F — prefersBenchmarkName: empty benchmarkDisplayName short-circuits
// ---------------------------------------------------------------------------

describe("Group F — prefersBenchmarkName: empty benchmarkDisplayName disables the rule", () => {
  it("even with a matching pattern, empty benchmarkDisplayName → return raw", () => {
    const entry: EvalListEntry = { evaluation_name: "accuracy on x" }
    const result = applyPrefersBenchmarkName(entry, "")
    expect(result.prefersBenchmarkName).toBe(false)
    expect(result.output).toBe("accuracy on x")
  })
})

// ---------------------------------------------------------------------------
// Group G — prefersBenchmarkName: rawDisplayName precedence
// ---------------------------------------------------------------------------

describe("Group G — rawDisplayName precedence chain (4 steps)", () => {
  const benchmarkDisplayName = "MMLU"

  it("step 1: evaluation_name wins", () => {
    const entry: EvalListEntry = {
      evaluation_name: "score on x",
      display_name: "fallback_display",
      benchmark_leaf_name: "leaf",
      eval_summary_id: "id_xyz",
    }
    const result = applyPrefersBenchmarkName(entry, benchmarkDisplayName)
    expect(result.rawDisplayName).toBe("score on x")
  })

  it("step 2: empty evaluation_name (falsy) → display_name", () => {
    const entry: EvalListEntry = {
      evaluation_name: "",
      display_name: "MMLU display",
      benchmark_leaf_name: "leaf",
      eval_summary_id: "id_xyz",
    }
    const result = applyPrefersBenchmarkName(entry, benchmarkDisplayName)
    expect(result.rawDisplayName).toBe("MMLU display")
  })

  it("step 3: benchmark_leaf_name when evaluation_name and display_name both empty", () => {
    const entry: EvalListEntry = {
      evaluation_name: "",
      display_name: "",
      benchmark_leaf_name: "leaf_name",
      eval_summary_id: "id_xyz",
    }
    const result = applyPrefersBenchmarkName(entry, benchmarkDisplayName)
    expect(result.rawDisplayName).toBe("leaf_name")
  })

  it("step 4: eval_summary_id final fallback", () => {
    const entry: EvalListEntry = {
      evaluation_name: "",
      display_name: "",
      benchmark_leaf_name: "",
      eval_summary_id: "id_xyz",
    }
    const result = applyPrefersBenchmarkName(entry, benchmarkDisplayName)
    expect(result.rawDisplayName).toBe("id_xyz")
  })
})
