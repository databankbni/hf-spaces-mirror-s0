import { describe, expect, it } from "vitest"

// Executable spec for the benchmark-card-attachment transformation.
//
// Replicates the four transformation pieces from
//   lib/benchmark-metadata.ts
//   lib/benchmark-metadata-utils.ts
//   lib/model-data.ts
//   lib/duckdb-data.ts
// verbatim. Pipeline must produce identical attach behaviour for every case
// below — and the migration target is "always inline benchmark_card so this
// retry loop becomes dead code."

// ---------------------------------------------------------------------------
// Verbatim copies of lib/benchmark-metadata-utils.ts
// ---------------------------------------------------------------------------

function normalizeBenchmarkKey(name: string): string {
  if (!name) return ""
  return name
    .replace(/^[a-z0-9_]+ ?\//i, "")
    .toLowerCase()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
}

function candidateBenchmarkKeys(name: string): string[] {
  const base = normalizeBenchmarkKey(name)
  return Array.from(
    new Set([
      base,
      base.replace(/-/g, " "),
      base.replace(/ /g, "-"),
      base.replace(/[^a-z0-9]/g, ""),
    ])
  )
}

// ---------------------------------------------------------------------------
// Verbatim copy of lib/benchmark-metadata.ts (map build + getBenchmarkCard)
// ---------------------------------------------------------------------------

interface MinimalCard {
  benchmark_details: { name: string }
  // tag for fixture identification
  __id: string
}

function buildMap(cards: Record<string, MinimalCard>): Map<string, MinimalCard> {
  const map = new Map<string, MinimalCard>()
  for (const card of Object.values(cards)) {
    if (!card?.benchmark_details?.name) continue
    for (const key of candidateBenchmarkKeys(card.benchmark_details.name)) {
      if (!map.has(key)) {
        map.set(key, card)
      }
    }
  }
  return map
}

function getBenchmarkCard(
  map: Map<string, MinimalCard>,
  benchmarkName: string
): MinimalCard | null {
  for (const key of candidateBenchmarkKeys(benchmarkName)) {
    const card = map.get(key)
    if (card) return card
  }
  return null
}

// ---------------------------------------------------------------------------
// Verbatim copy of lib/model-data.ts (summary attach order: name, name, key)
// ---------------------------------------------------------------------------

interface MinimalSummary {
  evaluation_name?: string
  composite_benchmark_name?: string
  composite_benchmark_key?: string
  benchmark_card?: MinimalCard | null
}

function attachBenchmarkCardToSummary(
  map: Map<string, MinimalCard>,
  summary: MinimalSummary
): MinimalSummary {
  if (summary.benchmark_card) return summary
  const candidates = [
    summary.evaluation_name,
    summary.composite_benchmark_name,
    summary.composite_benchmark_key,
  ]
  for (const candidate of candidates) {
    const card = getBenchmarkCard(map, candidate ?? "")
    if (card) return { ...summary, benchmark_card: card }
  }
  return summary
}

// ---------------------------------------------------------------------------
// Verbatim copy of lib/duckdb-data.ts (list attach order: name, key, name)
// ---------------------------------------------------------------------------

interface MinimalListItem {
  evaluation_name?: string
  composite_benchmark_name?: string
  composite_benchmark_key?: string
  benchmark_card?: MinimalCard | null
}

function attachBenchmarkCardToListItem(
  map: Map<string, MinimalCard>,
  item: MinimalListItem
): MinimalListItem {
  if (item.benchmark_card) return item
  const candidates = [
    item.evaluation_name,
    item.composite_benchmark_key,
    item.composite_benchmark_name,
  ].filter(Boolean) as string[]
  for (const name of candidates) {
    const card = getBenchmarkCard(map, name)
    if (card) return { ...item, benchmark_card: card }
  }
  return item
}

// ---------------------------------------------------------------------------
// Group A — normalizeBenchmarkKey
// ---------------------------------------------------------------------------

describe("Group A — normalizeBenchmarkKey", () => {
  const cases = [
    { input: "MMLU", expected: "mmlu", why: "lowercase only" },
    { input: "BIG-Bench Hard (BBH)", expected: "big bench hard (bbh)", why: "dashes → spaces" },
    { input: "hfopenllm_v2/mmlu", expected: "mmlu", why: "composite prefix stripped" },
    { input: "hfopenllm_v2 / mmlu", expected: "mmlu", why: "composite prefix with one space before /" },
    { input: "GPQA / Diamond", expected: "diamond", why: "regex allows optional space before /" },
    { input: "", expected: "", why: "falsy short-circuit (NOT 'unknown' fallback)" },
    { input: "  MMLU  ", expected: "mmlu", why: "trim leading/trailing whitespace" },
    { input: "foo___bar", expected: "foo bar", why: "underscore run → single space" },
    { input: "foo - - bar", expected: "foo bar", why: "dash + space runs collapse to single space" },
    { input: "mmlu_categories/mmlu_pro", expected: "mmlu pro", why: "prefix strip + underscore collapse" },
    { input: "BBH", expected: "bbh", why: "lowercase only" },
  ]
  it.each(cases)("'$input' → '$expected' ($why)", ({ input, expected }) => {
    expect(normalizeBenchmarkKey(input)).toBe(expected)
  })
})

// ---------------------------------------------------------------------------
// Group B — candidateBenchmarkKeys
// ---------------------------------------------------------------------------

describe("Group B — candidateBenchmarkKeys", () => {
  const cases = [
    { input: "MMLU", expected: ["mmlu"], why: "no dashes, no spaces, alnum-only → all 4 variants collapse" },
    {
      input: "BIG-Bench Hard (BBH)",
      expected: ["big bench hard (bbh)", "big-bench-hard-(bbh)", "bigbenchhardbbh"],
      why: "base; spaces→dashes; alnum-only (dashes→spaces collides with base after normalizer dash-collapse)",
    },
    { input: "GSM-8K", expected: ["gsm 8k", "gsm-8k", "gsm8k"], why: "base; spaces→dashes; alnum-only" },
    { input: "gsm 8k", expected: ["gsm 8k", "gsm-8k", "gsm8k"], why: "identical to above (input differs only in dash/space)" },
    { input: "hfopenllm_v2/mmlu", expected: ["mmlu"], why: "composite prefix stripped, no other variations" },
    { input: "", expected: [""], why: "all four variants collapse to empty string" },
  ]
  it.each(cases)("'$input' → $expected ($why)", ({ input, expected }) => {
    expect(candidateBenchmarkKeys(input)).toEqual(expected)
  })
})

// ---------------------------------------------------------------------------
// Group C — getBenchmarkCard (per-name lookup)
// ---------------------------------------------------------------------------

describe("Group C — getBenchmarkCard (per-name lookup against deduped map)", () => {
  const cards: Record<string, MinimalCard> = {
    mmlu: { __id: "mmlu", benchmark_details: { name: "MMLU" } },
    bbh: { __id: "bbh", benchmark_details: { name: "BIG-Bench Hard (BBH)" } },
    gsm: { __id: "gsm", benchmark_details: { name: "GSM-8K" } },
  }
  const map = buildMap(cards)

  it("finds MMLU via base candidate", () => {
    expect(getBenchmarkCard(map, "MMLU")?.__id).toBe("mmlu")
  })
  it("finds MMLU via case variation", () => {
    expect(getBenchmarkCard(map, "mmlu")?.__id).toBe("mmlu")
  })
  it("finds BBH card via full title (matches indexed key)", () => {
    expect(getBenchmarkCard(map, "BIG-Bench Hard (BBH)")?.__id).toBe("bbh")
  })
  it("MISSES BBH abbreviation (reverse-lookup limitation)", () => {
    // The card was indexed under variants of its full name. The eval name
    // "BBH" produces only ["bbh"] which does not collide with any indexed key.
    expect(getBenchmarkCard(map, "BBH")).toBeNull()
  })
  it("finds GSM-8K via input with space", () => {
    expect(getBenchmarkCard(map, "GSM 8K")?.__id).toBe("gsm")
  })
  it("returns null for empty string (no card indexed under '')", () => {
    expect(getBenchmarkCard(map, "")).toBeNull()
  })
  it("strips composite prefix and finds the leaf card", () => {
    expect(getBenchmarkCard(map, "hfopenllm_v2/mmlu")?.__id).toBe("mmlu")
  })
})

// ---------------------------------------------------------------------------
// Group D — Map build first-write-wins dedup
// ---------------------------------------------------------------------------

describe("Group D — map build dedup behaviour (first-write-wins)", () => {
  it("when two cards normalize to the same key, the first one wins", () => {
    const cards: Record<string, MinimalCard> = {
      first: { __id: "first", benchmark_details: { name: "MMLU" } },
      second: { __id: "second", benchmark_details: { name: "mmlu" } },
    }
    const map = buildMap(cards)
    expect(getBenchmarkCard(map, "MMLU")?.__id).toBe("first")
  })

  it("Object.values insertion order determines who wins", () => {
    // Reverse insertion order — now 'second' comes first.
    const cards: Record<string, MinimalCard> = {
      second: { __id: "second", benchmark_details: { name: "mmlu" } },
      first: { __id: "first", benchmark_details: { name: "MMLU" } },
    }
    const map = buildMap(cards)
    expect(getBenchmarkCard(map, "MMLU")?.__id).toBe("second")
  })

  it("a card with missing benchmark_details.name is skipped", () => {
    const cards: Record<string, MinimalCard> = {
      bad: { __id: "bad", benchmark_details: { name: "" } },
      good: { __id: "good", benchmark_details: { name: "MMLU" } },
    }
    const map = buildMap(cards)
    expect(getBenchmarkCard(map, "MMLU")?.__id).toBe("good")
  })

  it("a card with multiple distinct candidate keys is reachable via each", () => {
    const cards: Record<string, MinimalCard> = {
      bbh: { __id: "bbh", benchmark_details: { name: "BIG-Bench Hard (BBH)" } },
    }
    const map = buildMap(cards)
    expect(getBenchmarkCard(map, "BIG-Bench Hard (BBH)")?.__id).toBe("bbh")
    expect(getBenchmarkCard(map, "big-bench-hard-(bbh)")?.__id).toBe("bbh")
    expect(getBenchmarkCard(map, "bigbenchhardbbh")?.__id).toBe("bbh")
  })
})

// ---------------------------------------------------------------------------
// Group E — attachBenchmarkCardToSummary (3-candidate retry, summary order)
// ---------------------------------------------------------------------------

describe("Group E — attachBenchmarkCardToSummary (summary path, order: name, name, key)", () => {
  const cards: Record<string, MinimalCard> = {
    mmlu: { __id: "mmlu", benchmark_details: { name: "MMLU" } },
    bbh: { __id: "bbh", benchmark_details: { name: "BIG-Bench Hard (BBH)" } },
  }
  const map = buildMap(cards)

  it("hits on 1st candidate (evaluation_name)", () => {
    const result = attachBenchmarkCardToSummary(map, {
      evaluation_name: "MMLU",
      composite_benchmark_name: "Some other thing",
      composite_benchmark_key: "another_thing",
    })
    expect(result.benchmark_card?.__id).toBe("mmlu")
  })

  it("hits on 2nd candidate (composite_benchmark_name) when 1st misses", () => {
    const result = attachBenchmarkCardToSummary(map, {
      evaluation_name: "Accuracy on multi-choice questions",
      composite_benchmark_name: "MMLU",
      composite_benchmark_key: "mmlu",
    })
    expect(result.benchmark_card?.__id).toBe("mmlu")
  })

  it("hits on 3rd candidate (composite_benchmark_key) when 1st + 2nd miss", () => {
    const result = attachBenchmarkCardToSummary(map, {
      evaluation_name: "Accuracy on multi-choice questions",
      composite_benchmark_name: "Some unindexed display name",
      composite_benchmark_key: "MMLU",
    })
    expect(result.benchmark_card?.__id).toBe("mmlu")
  })

  it("no match → returns summary unchanged (passthrough)", () => {
    const summary = {
      evaluation_name: "nothing matches",
      composite_benchmark_name: "still nothing",
      composite_benchmark_key: "zilch",
    }
    const result = attachBenchmarkCardToSummary(map, summary)
    expect(result).toBe(summary) // identity — same object
    expect(result.benchmark_card).toBeUndefined()
  })

  it("default-only: pre-attached card is preserved (does NOT overwrite)", () => {
    const preExisting: MinimalCard = { __id: "preExisting", benchmark_details: { name: "preExisting" } }
    const summary = {
      evaluation_name: "MMLU",
      composite_benchmark_name: "MMLU",
      composite_benchmark_key: "mmlu",
      benchmark_card: preExisting,
    }
    const result = attachBenchmarkCardToSummary(map, summary)
    expect(result).toBe(summary)
    expect(result.benchmark_card?.__id).toBe("preExisting")
  })

  it("falsy benchmark_card (null) falls through to retry", () => {
    const result = attachBenchmarkCardToSummary(map, {
      evaluation_name: "MMLU",
      benchmark_card: null,
    })
    expect(result.benchmark_card?.__id).toBe("mmlu")
  })

  it("undefined candidate strings are passed through to getBenchmarkCard (which returns null on '')", () => {
    const result = attachBenchmarkCardToSummary(map, {
      // all three undefined
    })
    expect(result.benchmark_card).toBeUndefined()
  })
})

// ---------------------------------------------------------------------------
// Group F — attachBenchmarkCardToListItem (3-candidate retry, list path order)
// ---------------------------------------------------------------------------

describe("Group F — attachBenchmarkCardToListItem (list path, order: name, key, name)", () => {
  const cards: Record<string, MinimalCard> = {
    mmlu: { __id: "mmlu", benchmark_details: { name: "MMLU" } },
    bbh: { __id: "bbh", benchmark_details: { name: "BIG-Bench Hard (BBH)" } },
  }
  const map = buildMap(cards)

  it("hits on 1st candidate (evaluation_name)", () => {
    const result = attachBenchmarkCardToListItem(map, {
      evaluation_name: "MMLU",
      composite_benchmark_key: "other_key",
      composite_benchmark_name: "Other display name",
    })
    expect(result.benchmark_card?.__id).toBe("mmlu")
  })

  it("hits on 2nd candidate (composite_benchmark_KEY in this path, not name)", () => {
    const result = attachBenchmarkCardToListItem(map, {
      evaluation_name: "no match",
      composite_benchmark_key: "MMLU",
      composite_benchmark_name: "Other display",
    })
    expect(result.benchmark_card?.__id).toBe("mmlu")
  })

  it("hits on 3rd candidate (composite_benchmark_NAME in this path) when 1st + 2nd miss", () => {
    const result = attachBenchmarkCardToListItem(map, {
      evaluation_name: "no match",
      composite_benchmark_key: "no_match_either",
      composite_benchmark_name: "MMLU",
    })
    expect(result.benchmark_card?.__id).toBe("mmlu")
  })

  it(".filter(Boolean) drops empty/undefined candidates before iteration", () => {
    const item = {
      evaluation_name: "",
      composite_benchmark_key: undefined,
      composite_benchmark_name: "MMLU",
    }
    const result = attachBenchmarkCardToListItem(map, item)
    expect(result.benchmark_card?.__id).toBe("mmlu")
  })

  it("no match → returns item unchanged", () => {
    const item = {
      evaluation_name: "nothing",
      composite_benchmark_key: "nothing",
      composite_benchmark_name: "nothing",
    }
    const result = attachBenchmarkCardToListItem(map, item)
    expect(result).toBe(item)
    expect(result.benchmark_card).toBeUndefined()
  })

  it("default-only: pre-attached card preserved", () => {
    const preExisting: MinimalCard = { __id: "preExisting", benchmark_details: { name: "preExisting" } }
    const item = {
      evaluation_name: "MMLU",
      benchmark_card: preExisting,
    }
    const result = attachBenchmarkCardToListItem(map, item)
    expect(result).toBe(item)
    expect(result.benchmark_card?.__id).toBe("preExisting")
  })
})

// ---------------------------------------------------------------------------
// Group G — Asymmetric retry order between summary and list paths
// ---------------------------------------------------------------------------

describe("Group G — summary vs list path can disagree (TS-as-spec, not a bug)", () => {
  // Construct a map where the 2nd-position candidate in the SUMMARY path
  // (composite_benchmark_name) and the 2nd-position candidate in the LIST
  // path (composite_benchmark_key) point at DIFFERENT cards. The two paths
  // would attach different cards to the same underlying record.
  const cards: Record<string, MinimalCard> = {
    cardForName: { __id: "cardForName", benchmark_details: { name: "Display Name" } },
    cardForKey: { __id: "cardForKey", benchmark_details: { name: "raw_key" } },
  }
  const map = buildMap(cards)

  const record = {
    evaluation_name: "no first-position match",
    composite_benchmark_name: "Display Name",
    composite_benchmark_key: "raw_key",
  }

  it("summary path (2nd candidate is composite_benchmark_name) → cardForName", () => {
    const result = attachBenchmarkCardToSummary(map, { ...record })
    expect(result.benchmark_card?.__id).toBe("cardForName")
  })

  it("list path (2nd candidate is composite_benchmark_key) → cardForKey", () => {
    const result = attachBenchmarkCardToListItem(map, { ...record })
    expect(result.benchmark_card?.__id).toBe("cardForKey")
  })

  // Migration target: pipeline inlines benchmark_card so this asymmetry
  // becomes unobservable. Until then, document which path produced which
  // value if a bug report comes in.
})
