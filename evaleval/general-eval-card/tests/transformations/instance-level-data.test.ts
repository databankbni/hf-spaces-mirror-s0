import { describe, expect, it } from "vitest"

// Executable spec for the instance-level-data transformation.
//
// Replicates `parseInstanceLevelData` from `lib/hf-data.ts` verbatim.
// `fetchInstanceLevelData` (lib/hf-data.ts) is currently orphaned;
// not tested here (it just wraps fetch + JSON.parse + re-uses the parser).

interface SampleResult {
  sample_id: string
  input: string
  ground_truth?: string
  response: string
  choices?: unknown
  is_correct?: boolean
  metadata?: Record<string, unknown>
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function parseInstanceLevelData(data: unknown): SampleResult[] {
  if (!data || typeof data !== "object") return []

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const obj = data as Record<string, any>
  const examples: unknown[] = Array.isArray(obj.instance_examples)
    ? obj.instance_examples
    : Array.isArray(data)
      ? (data as unknown[])
      : []

  if (examples.length === 0) return []

  return examples
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    .map((raw: any, i: number) => {
      if (!raw || typeof raw !== "object") return null

      let input = ""
      if (typeof raw.input === "string") {
        input = raw.input
      } else if (raw.input?.raw) {
        input = String(raw.input.raw)
      } else if (raw.prompt) {
        input = raw.prompt
      } else if (raw.question) {
        input = raw.question
      } else if (raw.doc?.question) {
        input = raw.doc.question
      } else if (raw.doc) {
        input = JSON.stringify(raw.doc).slice(0, 500)
      }

      let groundTruth: string | undefined
      if (raw.input?.reference) {
        groundTruth = Array.isArray(raw.input.reference)
          ? raw.input.reference.join(", ")
          : String(raw.input.reference)
      } else if (raw.ground_truth != null) {
        groundTruth = String(raw.ground_truth)
      } else if (raw.target != null) {
        groundTruth = String(raw.target)
      } else if (raw.gold != null) {
        groundTruth = String(raw.gold)
      } else if (raw.doc?.answer != null) {
        groundTruth = String(raw.doc.answer)
      }

      let response = ""
      if (raw.output != null) {
        response = typeof raw.output === "string" ? raw.output : JSON.stringify(raw.output)
      } else if (raw.response) {
        response = raw.response
      } else if (raw.model_output) {
        response = raw.model_output
      } else if (Array.isArray(raw.answer_attribution) && raw.answer_attribution.length > 0) {
        const attr = raw.answer_attribution[raw.answer_attribution.length - 1]
        response = attr.extracted_value ?? ""
      } else if (Array.isArray(raw.messages) && raw.messages.length > 0) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const lastAssistant = [...raw.messages].reverse().find((m: any) => m.role === "assistant")
        if (lastAssistant) {
          response = typeof lastAssistant.content === "string"
            ? lastAssistant.content
            : JSON.stringify(lastAssistant.content)
        }
      } else if (raw.filtered_resps?.[0]?.[0]) {
        response = raw.filtered_resps[0][0]
      } else if (raw.resps?.[0]?.[0]) {
        response = raw.resps[0][0]
      }

      const isCorrect =
        raw.evaluation?.is_correct ??
        raw.is_correct ??
        (raw.metrics?.exact_match === 1 ? true :
         raw.metrics?.exact_match === 0 ? false : undefined)

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const metadata: Record<string, any> = {}
      if (raw.evaluation && typeof raw.evaluation === "object") {
        Object.assign(metadata, raw.evaluation)
      }
      if (raw.performance && typeof raw.performance === "object") {
        Object.assign(metadata, raw.performance)
      }
      if (raw.metadata && typeof raw.metadata === "object") {
        Object.assign(metadata, raw.metadata)
      }
      if (raw.metrics && typeof raw.metrics === "object") {
        Object.assign(metadata, raw.metrics)
      }

      return {
        sample_id: raw.sample_id ?? raw.doc_id ?? raw.id ?? String(i),
        input,
        ground_truth: groundTruth,
        response,
        choices: raw.choices ?? raw.doc?.choices ?? undefined,
        is_correct: isCorrect,
        metadata: Object.keys(metadata).length > 0 ? metadata : undefined,
      } as SampleResult
    })
    .filter((s): s is SampleResult => s !== null)
}

// ---------------------------------------------------------------------------
// Group A — top-level shape guards
// ---------------------------------------------------------------------------

describe("Group A — top-level shape guards", () => {
  it("returns [] for null", () => {
    expect(parseInstanceLevelData(null)).toEqual([])
  })

  it("returns [] for undefined", () => {
    expect(parseInstanceLevelData(undefined)).toEqual([])
  })

  it("returns [] for non-object (string)", () => {
    expect(parseInstanceLevelData("hello")).toEqual([])
  })

  it("returns [] for non-object (number)", () => {
    expect(parseInstanceLevelData(42)).toEqual([])
  })

  it("returns [] when instance_examples is missing AND data is not an array", () => {
    expect(parseInstanceLevelData({ foo: "bar" })).toEqual([])
  })

  it("returns [] when instance_examples is empty array", () => {
    expect(parseInstanceLevelData({ instance_examples: [] })).toEqual([])
  })

  it("uses data array directly when instance_examples is missing AND data is an array", () => {
    const result = parseInstanceLevelData([{ sample_id: "s1", input: "hello" }])
    expect(result).toHaveLength(1)
    expect(result[0].sample_id).toBe("s1")
    expect(result[0].input).toBe("hello")
  })

  it("filters out null/non-object examples but keeps valid ones", () => {
    const result = parseInstanceLevelData({
      instance_examples: [
        { sample_id: "s1", input: "ok" },
        null,
        "string-not-object",
        { sample_id: "s2", input: "ok2" },
      ],
    })
    expect(result).toHaveLength(2)
    expect(result.map((r) => r.sample_id)).toEqual(["s1", "s2"])
  })
})

// ---------------------------------------------------------------------------
// Group B — input field fallback chain
// ---------------------------------------------------------------------------

describe("Group B — input fallback chain (in priority order)", () => {
  const inputCases = [
    {
      label: "raw.input as string (branch #1)",
      example: { input: "direct string" },
      expected: "direct string",
    },
    {
      label: "raw.input.raw (branch #2; the production-canonical path, 100% of rows)",
      example: { input: { raw: "from input.raw" } },
      expected: "from input.raw",
    },
    {
      label: "raw.input.raw with non-string value gets stringified",
      example: { input: { raw: 42 } },
      expected: "42",
    },
    {
      label: "raw.prompt (branch #3; defensive — 0% in current production)",
      example: { prompt: "the prompt" },
      expected: "the prompt",
    },
    {
      label: "raw.question (branch #4; defensive)",
      example: { question: "the question" },
      expected: "the question",
    },
    {
      label: "raw.doc.question (branch #5; HELM-style, defensive)",
      example: { doc: { question: "doc question" } },
      expected: "doc question",
    },
    {
      label: "raw.doc fallback to JSON.stringify (branch #6; truncated to 500)",
      example: { doc: { question: null, foo: "bar" } },
      // ?.question is null which is falsy, so falls through to JSON.stringify(raw.doc)
      expected: JSON.stringify({ question: null, foo: "bar" }).slice(0, 500),
    },
    {
      label: "no input fields → empty string",
      example: { sample_id: "s1" },
      expected: "",
    },
    {
      label: "input.raw takes precedence over prompt",
      example: { input: { raw: "winner" }, prompt: "loser" },
      expected: "winner",
    },
    {
      label: "raw.input is empty string → falls through to next branches (because falsy)",
      example: { input: "", prompt: "fallback" },
      // typeof "" === "string" so branch #1 fires → input = ""... wait, let me trace
      // Actually: typeof raw.input === "string" is TRUE for "", so branch #1 fires and assigns input = ""
      // No fallthrough.
      expected: "",
    },
  ]

  it.each(inputCases)("$label", ({ example, expected }) => {
    const result = parseInstanceLevelData({ instance_examples: [example] })
    expect(result[0]?.input).toBe(expected)
  })
})

// ---------------------------------------------------------------------------
// Group C — ground_truth fallback chain
// ---------------------------------------------------------------------------

describe("Group C — ground_truth fallback chain (in priority order)", () => {
  const cases = [
    {
      label: "raw.input.reference as string (branch #1; the production-canonical path)",
      example: { input: { reference: "the answer" } },
      expected: "the answer",
    },
    {
      label: "raw.input.reference as array → joined with ', '",
      example: { input: { reference: ["a", "b", "c"] } },
      expected: "a, b, c",
    },
    {
      label: "raw.input.reference as number → String()",
      example: { input: { reference: 42 } },
      expected: "42",
    },
    {
      label: "raw.ground_truth (branch #2; defensive)",
      example: { ground_truth: "gt" },
      expected: "gt",
    },
    {
      label: "raw.target (branch #3; defensive)",
      example: { target: "the target" },
      expected: "the target",
    },
    {
      label: "raw.gold (branch #4; defensive)",
      example: { gold: "the gold" },
      expected: "the gold",
    },
    {
      label: "raw.doc.answer (branch #5; HELM-style, defensive)",
      example: { doc: { answer: "doc answer" } },
      expected: "doc answer",
    },
    {
      label: "no ground_truth fields → undefined",
      example: { sample_id: "s1" },
      expected: undefined,
    },
    {
      label: "raw.input.reference takes precedence over raw.target",
      example: { input: { reference: "winner" }, target: "loser" },
      expected: "winner",
    },
  ]

  it.each(cases)("$label", ({ example, expected }) => {
    const result = parseInstanceLevelData({ instance_examples: [example] })
    expect(result[0]?.ground_truth).toBe(expected)
  })
})

// ---------------------------------------------------------------------------
// Group D — response fallback chain
// ---------------------------------------------------------------------------

describe("Group D — response fallback chain (in priority order)", () => {
  it("raw.output as string (branch #1)", () => {
    const r = parseInstanceLevelData({ instance_examples: [{ output: "the output" }] })
    expect(r[0]?.response).toBe("the output")
  })

  it("raw.output as object → JSON.stringify (branch #1)", () => {
    const r = parseInstanceLevelData({ instance_examples: [{ output: { foo: "bar" } }] })
    expect(r[0]?.response).toBe('{"foo":"bar"}')
  })

  it("raw.response (branch #2; defensive — 0% in current production)", () => {
    const r = parseInstanceLevelData({ instance_examples: [{ response: "hello" }] })
    expect(r[0]?.response).toBe("hello")
  })

  it("raw.model_output (branch #3; defensive)", () => {
    const r = parseInstanceLevelData({ instance_examples: [{ model_output: "model said" }] })
    expect(r[0]?.response).toBe("model said")
  })

  it("raw.answer_attribution (branch #4; the production majority path, 97.31%)", () => {
    const r = parseInstanceLevelData({
      instance_examples: [{ answer_attribution: [{ extracted_value: "first" }, { extracted_value: "last wins" }] }],
    })
    expect(r[0]?.response).toBe("last wins")
  })

  it("raw.answer_attribution last-element with no extracted_value → empty string", () => {
    const r = parseInstanceLevelData({
      instance_examples: [{ answer_attribution: [{ foo: "bar" }] }],
    })
    expect(r[0]?.response).toBe("")
  })

  it("raw.answer_attribution as empty array → falls through (length check)", () => {
    const r = parseInstanceLevelData({
      instance_examples: [{ answer_attribution: [], messages: [{ role: "assistant", content: "via messages" }] }],
    })
    expect(r[0]?.response).toBe("via messages")
  })

  it("raw.messages reversed-find last assistant (branch #5; production minority 2.49%)", () => {
    const r = parseInstanceLevelData({
      instance_examples: [{
        messages: [
          { role: "user", content: "hi" },
          { role: "assistant", content: "first reply" },
          { role: "user", content: "more" },
          { role: "assistant", content: "last reply" },
        ],
      }],
    })
    expect(r[0]?.response).toBe("last reply")
  })

  it("raw.messages with no assistant role → empty string (no last-assistant found)", () => {
    const r = parseInstanceLevelData({
      instance_examples: [{ messages: [{ role: "user", content: "hi" }] }],
    })
    expect(r[0]?.response).toBe("")
  })

  it("raw.messages assistant content as object → JSON.stringify", () => {
    const r = parseInstanceLevelData({
      instance_examples: [{ messages: [{ role: "assistant", content: { tool: "x" } }] }],
    })
    expect(r[0]?.response).toBe('{"tool":"x"}')
  })

  it("raw.filtered_resps[0][0] (branch #6; lm-eval-harness, defensive)", () => {
    const r = parseInstanceLevelData({
      instance_examples: [{ filtered_resps: [["filtered answer"]] }],
    })
    expect(r[0]?.response).toBe("filtered answer")
  })

  it("raw.resps[0][0] (branch #7; lm-eval-harness, defensive)", () => {
    const r = parseInstanceLevelData({
      instance_examples: [{ resps: [["resps answer"]] }],
    })
    expect(r[0]?.response).toBe("resps answer")
  })

  it("no response fields → empty string", () => {
    const r = parseInstanceLevelData({ instance_examples: [{ sample_id: "s1" }] })
    expect(r[0]?.response).toBe("")
  })

  it("raw.output takes precedence over answer_attribution", () => {
    const r = parseInstanceLevelData({
      instance_examples: [{ output: "winner", answer_attribution: [{ extracted_value: "loser" }] }],
    })
    expect(r[0]?.response).toBe("winner")
  })
})

// ---------------------------------------------------------------------------
// Group E — is_correct fallback chain
// ---------------------------------------------------------------------------

describe("Group E — is_correct fallback chain", () => {
  it("raw.evaluation.is_correct true (branch #1; production-canonical, 100%)", () => {
    const r = parseInstanceLevelData({ instance_examples: [{ evaluation: { is_correct: true } }] })
    expect(r[0]?.is_correct).toBe(true)
  })

  it("raw.evaluation.is_correct false", () => {
    const r = parseInstanceLevelData({ instance_examples: [{ evaluation: { is_correct: false } }] })
    expect(r[0]?.is_correct).toBe(false)
  })

  it("raw.is_correct (branch #2; defensive)", () => {
    const r = parseInstanceLevelData({ instance_examples: [{ is_correct: true }] })
    expect(r[0]?.is_correct).toBe(true)
  })

  it("raw.metrics.exact_match === 1 → true (branch #3; defensive)", () => {
    const r = parseInstanceLevelData({ instance_examples: [{ metrics: { exact_match: 1 } }] })
    expect(r[0]?.is_correct).toBe(true)
  })

  it("raw.metrics.exact_match === 0 → false", () => {
    const r = parseInstanceLevelData({ instance_examples: [{ metrics: { exact_match: 0 } }] })
    expect(r[0]?.is_correct).toBe(false)
  })

  it("raw.metrics.exact_match === 0.5 (between) → undefined (only literal 0/1 register)", () => {
    const r = parseInstanceLevelData({ instance_examples: [{ metrics: { exact_match: 0.5 } }] })
    expect(r[0]?.is_correct).toBeUndefined()
  })

  it("no is_correct fields → undefined", () => {
    const r = parseInstanceLevelData({ instance_examples: [{ sample_id: "s1" }] })
    expect(r[0]?.is_correct).toBeUndefined()
  })
})

// ---------------------------------------------------------------------------
// Group F — sample_id fallback chain
// ---------------------------------------------------------------------------

describe("Group F — sample_id fallback chain", () => {
  it("raw.sample_id (branch #1; production-canonical, 100%)", () => {
    const r = parseInstanceLevelData({ instance_examples: [{ sample_id: "s-direct" }] })
    expect(r[0]?.sample_id).toBe("s-direct")
  })

  it("raw.doc_id (branch #2; defensive)", () => {
    const r = parseInstanceLevelData({ instance_examples: [{ doc_id: "d-1" }] })
    expect(r[0]?.sample_id).toBe("d-1")
  })

  it("raw.id (branch #3; defensive)", () => {
    const r = parseInstanceLevelData({ instance_examples: [{ id: "id-1" }] })
    expect(r[0]?.sample_id).toBe("id-1")
  })

  it("none of the above → array index (branch #4)", () => {
    const r = parseInstanceLevelData({ instance_examples: [{ foo: "bar" }, { baz: "qux" }] })
    expect(r[0]?.sample_id).toBe("0")
    expect(r[1]?.sample_id).toBe("1")
  })

  it("raw.sample_id takes precedence over doc_id and id", () => {
    const r = parseInstanceLevelData({
      instance_examples: [{ sample_id: "winner", doc_id: "loser1", id: "loser2" }],
    })
    expect(r[0]?.sample_id).toBe("winner")
  })

  it("numeric sample_id (e.g. 0) → preserved as-is via ?? (NOT falsy-rejected)", () => {
    const r = parseInstanceLevelData({ instance_examples: [{ sample_id: 0 }] })
    // sample_id ?? doc_id ?? id ?? String(i) — `??` only triggers on null/undefined.
    // 0 is preserved as a number; the type assertion forces it through.
    expect(r[0]?.sample_id).toBe(0 as unknown as string)
  })
})

// ---------------------------------------------------------------------------
// Group G — choices fallback chain
// ---------------------------------------------------------------------------

describe("Group G — choices fallback chain (0% in current production)", () => {
  it("raw.choices (branch #1)", () => {
    const r = parseInstanceLevelData({ instance_examples: [{ choices: ["A", "B", "C"] }] })
    expect(r[0]?.choices).toEqual(["A", "B", "C"])
  })

  it("raw.doc.choices (branch #2; HELM-style)", () => {
    const r = parseInstanceLevelData({ instance_examples: [{ doc: { choices: ["X", "Y"] } }] })
    expect(r[0]?.choices).toEqual(["X", "Y"])
  })

  it("none → undefined", () => {
    const r = parseInstanceLevelData({ instance_examples: [{ sample_id: "s1" }] })
    expect(r[0]?.choices).toBeUndefined()
  })
})

// ---------------------------------------------------------------------------
// Group H — metadata merge
// ---------------------------------------------------------------------------

describe("Group H — metadata merge (in order: evaluation, performance, metadata, metrics)", () => {
  it("merges all four sources", () => {
    const r = parseInstanceLevelData({
      instance_examples: [{
        evaluation: { is_correct: true, eval_field: "e" },
        performance: { latency_ms: 100 },
        metadata: { tag: "x" },
        metrics: { exact_match: 1 },
      }],
    })
    expect(r[0]?.metadata).toEqual({
      is_correct: true,
      eval_field: "e",
      latency_ms: 100,
      tag: "x",
      exact_match: 1,
    })
  })

  it("later sources overwrite earlier on key collision (metadata wins over evaluation)", () => {
    const r = parseInstanceLevelData({
      instance_examples: [{
        evaluation: { common: "from-eval" },
        metadata: { common: "from-metadata" },
      }],
    })
    expect(r[0]?.metadata?.common).toBe("from-metadata")
  })

  it("returns undefined when all four sources absent", () => {
    const r = parseInstanceLevelData({ instance_examples: [{ sample_id: "s1" }] })
    expect(r[0]?.metadata).toBeUndefined()
  })

  it("returns undefined when all four sources are empty objects", () => {
    const r = parseInstanceLevelData({
      instance_examples: [{ evaluation: {}, performance: {}, metadata: {}, metrics: {} }],
    })
    expect(r[0]?.metadata).toBeUndefined()
  })

  it("ignores non-object sources (e.g. evaluation as string)", () => {
    const r = parseInstanceLevelData({
      instance_examples: [{
        evaluation: "not an object",
        metadata: { ok: 1 },
      }],
    })
    expect(r[0]?.metadata).toEqual({ ok: 1 })
  })
})

// ---------------------------------------------------------------------------
// Group I — production-canonical full example (end-to-end)
// ---------------------------------------------------------------------------

describe("Group I — production-canonical full example", () => {
  // Models the exact shape audited 2026-04-28 across all 712 production rows.
  const productionExample = {
    schema_version: "1.0",
    evaluation_id: "swe_bench_verified_mini::abc123",
    model_id: "anthropic__anthropic-claude-3-7-sonnet",
    evaluation_name: "swe_bench_verified_mini",
    sample_id: "instance_42",
    sample_hash: "abc123def456",
    interaction_type: "multi_turn",
    input: { raw: "Fix this bug in this Python file" },
    output: null,
    messages: [
      { role: "user", content: "Fix this bug" },
      { role: "assistant", content: "Here's the fix..." },
    ],
    answer_attribution: [
      { extracted_value: "diff --git a/foo.py b/foo.py..." },
    ],
    evaluation: { is_correct: true, score: 1.0 },
    performance: { latency_ms: 5421 },
    metadata: { difficulty: "medium" },
    token_usage: { input: 1000, output: 500 },
  }

  it("extracts fields per the canonical-shape branches", () => {
    const r = parseInstanceLevelData({ instance_examples: [productionExample] })
    expect(r).toHaveLength(1)
    const sample = r[0]
    expect(sample.sample_id).toBe("instance_42")
    expect(sample.input).toBe("Fix this bug in this Python file")  // from input.raw
    // ground_truth is undefined because input.reference is unset (this example doesn't have it)
    expect(sample.ground_truth).toBeUndefined()
    expect(sample.response).toBe("diff --git a/foo.py b/foo.py...")  // answer_attribution wins (output is null)
    expect(sample.is_correct).toBe(true)
    expect(sample.choices).toBeUndefined()
    expect(sample.metadata).toEqual({
      is_correct: true,
      score: 1.0,
      latency_ms: 5421,
      difficulty: "medium",
    })
  })

  it("with input.reference present → ground_truth is set", () => {
    const r = parseInstanceLevelData({
      instance_examples: [{ ...productionExample, input: { raw: "Q?", reference: "expected answer" } }],
    })
    expect(r[0].ground_truth).toBe("expected answer")
  })
})
