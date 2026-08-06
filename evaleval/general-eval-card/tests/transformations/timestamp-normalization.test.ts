import { describe, expect, it } from "vitest"

// Executable spec for the timestamp-normalization transformation.
//
// Three implementations of timestamp normalization exist in TS:
//   - Variant A: lib/model-data.ts (normalizeEvalTimestamp)
//   - Variant B: lib/hf-data.ts (toComparableTimestamp)
//   - Variant C: components/benchmark-detail.tsx (toComparableTimestamp)
//
// They DIVERGE on cross-format comparisons but converge on production data
// (99.99% unix-seconds-strings). This test file documents all three with
// their distinct semantics.

// === Variant A: lib/model-data.ts — Number(), * 1000 if numeric & no dash ===
function normalizeEvalTimestamp(value: string): number {
  const numericTimestamp = Number(value)
  return !Number.isNaN(numericTimestamp) && !value.includes("-")
    ? numericTimestamp * 1000
    : new Date(value).getTime()
}

// === Variant B: lib/hf-data.ts — parseFloat, no multiplier, undefined-safe ===
function toComparableTimestampHfData(timestamp: string | undefined): number {
  if (!timestamp) return Number.NEGATIVE_INFINITY
  const numericTimestamp = Number.parseFloat(timestamp)
  if (Number.isFinite(numericTimestamp)) return numericTimestamp
  const parsedTimestamp = new Date(timestamp).getTime()
  return Number.isFinite(parsedTimestamp) ? parsedTimestamp : Number.NEGATIVE_INFINITY
}

// === Variant C: components/benchmark-detail.tsx — same as B but no undefined check ===
function toComparableTimestampBenchmarkDetail(timestamp: string): number {
  const numericTimestamp = Number.parseFloat(timestamp)
  if (Number.isFinite(numericTimestamp)) return numericTimestamp
  const parsedTimestamp = new Date(timestamp).getTime()
  return Number.isFinite(parsedTimestamp) ? parsedTimestamp : Number.NEGATIVE_INFINITY
}

// ---------------------------------------------------------------------------
// Group A — Variant A (normalizeEvalTimestamp)
// ---------------------------------------------------------------------------

describe("Group A — normalizeEvalTimestamp (Variant A, lib/model-data.ts)", () => {
  const cases = [
    {
      input: "1774096306",
      expected: 1774096306000,
      why: "numeric + no dash → * 1000 (treat as unix seconds, output ms)",
    },
    {
      input: "1774096306.427425",
      expected: 1774096306427.4248,
      why: "numeric float → * 1000",
    },
    {
      input: "2026-04-13T12:34:56Z",
      expected: new Date("2026-04-13T12:34:56Z").getTime(),
      why: "Number() returns NaN on ISO → fall to Date.getTime()",
    },
    {
      input: "2025-01-01",
      expected: new Date("2025-01-01").getTime(),
      why: "ISO date → Date.getTime()",
    },
    {
      input: "20240620",
      expected: 20240620000,
      why: "TS quirk: numeric + no dash → * 1000 (treated as unix seconds, NOT YYYYMMDD)",
    },
    {
      input: "",
      expected: 0,
      why: "TS quirk: Number('') = 0, no dash → 0 * 1000 = 0 (not NEGATIVE_INFINITY)",
    },
  ]
  it.each(cases)("'$input' → $expected ($why)", ({ input, expected }) => {
    expect(normalizeEvalTimestamp(input)).toBe(expected)
  })

  it("non-numeric, non-Date string → NaN", () => {
    expect(normalizeEvalTimestamp("not a date")).toBeNaN()
  })

  it("'-1774096306' (negative numeric, includes dash) → falls to Date.getTime() of negative-string", () => {
    // Number("-1774096306") = -1774096306 (numeric), but includes("-") is true
    // → falls to new Date("-1774096306") which is invalid → NaN
    const result = normalizeEvalTimestamp("-1774096306")
    expect(Number.isNaN(result)).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// Group B — Variant B (toComparableTimestamp in lib/hf-data.ts)
// ---------------------------------------------------------------------------

describe("Group B — toComparableTimestamp (Variant B, lib/hf-data.ts)", () => {
  const cases = [
    {
      input: "1774096306",
      expected: 1774096306,
      why: "parseFloat finite → return AS-IS (NO multiplier — different from Variant A)",
    },
    {
      input: "1774096306.427425",
      expected: 1774096306.427425,
      why: "parseFloat finite → return as-is",
    },
    {
      input: "2026-04-13T12:34:56Z",
      expected: 2026,
      why: "TS quirk: parseFloat extracts leading '2026' → returns 2026 (NOT a timestamp!)",
    },
    {
      input: "2025-01-01",
      expected: 2025,
      why: "TS quirk: parseFloat → 2025",
    },
    {
      input: "20240620",
      expected: 20240620,
      why: "parseFloat finite → return as-is (no multiplier)",
    },
    {
      input: "not a date",
      expected: Number.NEGATIVE_INFINITY,
      why: "parseFloat NaN AND Date NaN → fallback",
    },
    {
      input: "",
      expected: Number.NEGATIVE_INFINITY,
      why: "falsy → defensive NEGATIVE_INFINITY",
    },
    {
      input: undefined,
      expected: Number.NEGATIVE_INFINITY,
      why: "undefined → defensive NEGATIVE_INFINITY",
    },
  ]
  it.each(cases)("'$input' → $expected ($why)", ({ input, expected }) => {
    expect(toComparableTimestampHfData(input)).toBe(expected)
  })
})

// ---------------------------------------------------------------------------
// Group C — Variant C (toComparableTimestamp in components/benchmark-detail.tsx)
// ---------------------------------------------------------------------------

describe("Group C — toComparableTimestamp (Variant C, benchmark-detail.tsx)", () => {
  // Variant C is functionally identical to B except no undefined-handling.
  // All non-undefined cases match B.
  const cases = [
    { input: "1774096306", expected: 1774096306 },
    { input: "1774096306.427425", expected: 1774096306.427425 },
    { input: "2026-04-13T12:34:56Z", expected: 2026 },
    { input: "2025-01-01", expected: 2025 },
    { input: "20240620", expected: 20240620 },
    { input: "not a date", expected: Number.NEGATIVE_INFINITY },
    { input: "", expected: Number.NEGATIVE_INFINITY, why: "parseFloat('')=NaN, Date('').getTime()=NaN → fallback" },
  ]
  it.each(cases)("'$input' → $expected", ({ input, expected }) => {
    expect(toComparableTimestampBenchmarkDetail(input)).toBe(expected)
  })
})

// ---------------------------------------------------------------------------
// Group D — Cross-variant divergence (DOCUMENTED, NOT FIXED)
// ---------------------------------------------------------------------------
//
// The three variants produce different numeric values for the same input.
// Comparing values across variants is unsafe. Within each variant's own scope,
// comparisons are consistent (same format → same parser → correct ordering).
// In production, format consistency (99.99% unix-seconds) means cross-format
// comparison rarely fires — so this divergence doesn't usually manifest.

describe("Group D — cross-variant divergence (TS quirk, do not 'fix')", () => {
  it("unix-seconds-string: Variant A applies * 1000, Variants B/C don't", () => {
    expect(normalizeEvalTimestamp("1774096306.427425")).toBe(1774096306427.4248)
    expect(toComparableTimestampHfData("1774096306.427425")).toBe(1774096306.427425)
    expect(toComparableTimestampBenchmarkDetail("1774096306.427425")).toBe(1774096306.427425)
  })

  it("ISO datetime: Variant A correctly parses to ms-of-epoch; Variants B/C extract year via parseFloat", () => {
    expect(normalizeEvalTimestamp("2026-04-13T12:34:56Z")).toBe(new Date("2026-04-13T12:34:56Z").getTime())
    expect(toComparableTimestampHfData("2026-04-13T12:34:56Z")).toBe(2026)
    expect(toComparableTimestampBenchmarkDetail("2026-04-13T12:34:56Z")).toBe(2026)
  })

  it("cross-format ordering (unix-seconds vs ISO): Variant A correct, Variants B/C INCORRECT (TS bug, deferred)", () => {
    const unixSec = "1774096306.427425" // ~year 2026
    const isoDate = "2026-04-13T12:34:56Z"
    // Variant A correctly identifies isoDate as more recent (or close enough)
    expect(normalizeEvalTimestamp(unixSec)).toBeLessThan(normalizeEvalTimestamp(isoDate))
    // Variants B/C INCORRECTLY treat ISO as the year-number (2026) which is much smaller
    expect(toComparableTimestampHfData(unixSec)).toBeGreaterThan(toComparableTimestampHfData(isoDate))
    expect(toComparableTimestampBenchmarkDetail(unixSec)).toBeGreaterThan(toComparableTimestampBenchmarkDetail(isoDate))
  })

  it("within-format ordering: all three variants agree on chronological order for unix-seconds inputs", () => {
    const a = "1700000000"
    const b = "1800000000"
    expect(normalizeEvalTimestamp(a)).toBeLessThan(normalizeEvalTimestamp(b))
    expect(toComparableTimestampHfData(a)).toBeLessThan(toComparableTimestampHfData(b))
    expect(toComparableTimestampBenchmarkDetail(a)).toBeLessThan(toComparableTimestampBenchmarkDetail(b))
  })

  it("within-format ordering: all three variants agree on chronological order for ISO inputs", () => {
    const a = "2025-01-01"
    const b = "2026-01-01"
    expect(normalizeEvalTimestamp(a)).toBeLessThan(normalizeEvalTimestamp(b))
    expect(toComparableTimestampHfData(a)).toBeLessThan(toComparableTimestampHfData(b))
    expect(toComparableTimestampBenchmarkDetail(a)).toBeLessThan(toComparableTimestampBenchmarkDetail(b))
  })
})
