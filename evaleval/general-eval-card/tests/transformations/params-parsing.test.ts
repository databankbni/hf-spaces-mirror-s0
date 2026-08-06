import { describe, expect, it } from "vitest"

// Executable spec for the params-parsing transformation.
//
// Five implementations of params-billions parsing exist in TS:
//   - Variant A: lib/model-data.ts (parseParamsBillions)
//   - Variant B: components/eval-detail.tsx (parseParamsBillionsFromText)
//   - Variant C: components/eval-detail.tsx (parseParamsBillionsFromModelName)
//   - Variant D: components/eval-detail.tsx (getParamsBillionsFromModelInfo — orchestrator)
//   - Variant E: components/model-compare-dialog.tsx (parseParamsBillionsFromModelName)
//   - Variant F: app/evals/[id]/page.tsx (inline regex on `name + " " + id`)
//
// They DIVERGE on edge cases (units accepted, anchoring, fallback chains, ≤0 handling)
// but converge on the most common production inputs (clean "7B" / "34.389" strings).
// Migration target: pipeline emits a single canonical numeric `params_billions` per
// model-result; all five parsers delete.

// === Variant A: lib/model-data.ts ===
function parseParamsBillions(value: unknown): number | null {
  if (typeof value === "number") {
    return Number.isFinite(value) && value > 0 ? value : null
  }
  if (typeof value !== "string") return null

  const normalized = value.trim().toLowerCase()
  if (!normalized) return null

  const compact = normalized.replace(/,/g, "")
  const tokenMatch = compact.match(/(\d+(?:\.\d+)?)\s*(trillion|tn|t|billion|bn|b|million|mn|m|thousand|k)\b/)
  if (tokenMatch) {
    const amount = Number.parseFloat(tokenMatch[1])
    if (!Number.isFinite(amount) || amount <= 0) return null
    const unit = tokenMatch[2]
    if (unit === "trillion" || unit === "tn" || unit === "t") return amount * 1000
    if (unit === "billion" || unit === "bn" || unit === "b") return amount
    if (unit === "million" || unit === "mn" || unit === "m") return amount / 1000
    if (unit === "thousand" || unit === "k") return amount / 1_000_000
  }

  const numeric = Number.parseFloat(compact)
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null
}

// === Variant B: components/eval-detail.tsx ===
function parseParamsBillionsFromText(value: string | null | undefined): number | null {
  if (!value) return null
  const normalized = value.trim().toLowerCase()
  if (!normalized) return null

  const compact = normalized.replace(/,/g, "")
  const tokenMatch = compact.match(/(\d+(?:\.\d+)?)\s*(trillion|tn|t|billion|bn|b|million|mn|m|thousand|k)\b/)
  if (tokenMatch) {
    const amount = Number.parseFloat(tokenMatch[1])
    if (!Number.isFinite(amount)) return null
    const unit = tokenMatch[2]
    if (unit === "trillion" || unit === "tn" || unit === "t") return amount * 1000
    if (unit === "billion" || unit === "bn" || unit === "b") return amount
    if (unit === "million" || unit === "mn" || unit === "m") return amount / 1000
    if (unit === "thousand" || unit === "k") return amount / 1_000_000
  }
  const numeric = Number.parseFloat(compact)
  return Number.isFinite(numeric) ? numeric : null
}

// === Variant C: components/eval-detail.tsx ===
function parseParamsBillionsFromModelNameC(modelName: string | null | undefined): number | null {
  if (!modelName) return null
  const sizeTokens = Array.from(modelName.matchAll(/\b(\d+(?:\.\d+)?)\s*([tmbk])\b/gi))
  if (sizeTokens.length === 0) return null

  const lastToken = sizeTokens[sizeTokens.length - 1]
  const numericValue = Number.parseFloat(lastToken[1])
  if (!Number.isFinite(numericValue)) return null

  const unit = lastToken[2].toLowerCase()
  if (unit === "t") return numericValue * 1000
  if (unit === "b") return numericValue
  if (unit === "m") return numericValue / 1000
  if (unit === "k") return numericValue / 1_000_000
  return null
}

// === Variant E: components/model-compare-dialog.tsx ===
function parseParamsBillionsFromModelNameE(modelName: string | null | undefined): number | null {
  if (!modelName) return null
  const sizeTokens = Array.from(modelName.matchAll(/\b(\d+(?:\.\d+)?)\s*([bm])\b/gi))
  if (sizeTokens.length === 0) return null

  const lastToken = sizeTokens[sizeTokens.length - 1]
  const numericValue = Number(lastToken[1])
  if (!Number.isFinite(numericValue)) return null

  const unit = lastToken[2].toLowerCase()
  if (unit === "b") return numericValue
  if (unit === "m") return numericValue / 1000
  return null
}

// === Variant F: app/evals/[id]/page.tsx:434-437 ===
function parseParamsBillionsInline(name: string, id: string): number | null {
  const sizeMatch = (name + " " + id).match(/\b(\d+(?:\.\d+)?)\s*[bB]\b/)
  if (sizeMatch) return parseFloat(sizeMatch[1])
  return null
}

// ---------------------------------------------------------------------------
// Group A — Variant A (parseParamsBillions, lib/model-data.ts)
// ---------------------------------------------------------------------------

describe("Group A — parseParamsBillions (Variant A, lib/model-data.ts)", () => {
  describe("number-input branch", () => {
    const cases = [
      { input: 7, expected: 7, why: "finite + >0 → return as-is" },
      { input: 34.389, expected: 34.389, why: "float passes through" },
      { input: 0, expected: null, why: ">0 reject" },
      { input: -3, expected: null, why: ">0 reject" },
      { input: NaN, expected: null, why: "isFinite reject" },
      { input: Infinity, expected: null, why: "isFinite reject" },
    ]
    it.each(cases)("$input → $expected ($why)", ({ input, expected }) => {
      expect(parseParamsBillions(input)).toBe(expected)
    })
  })

  describe("non-string non-number → null", () => {
    it.each([
      { input: null },
      { input: undefined },
      { input: [] },
      { input: {} },
      { input: true },
    ])("$input → null", ({ input }) => {
      expect(parseParamsBillions(input)).toBe(null)
    })
  })

  describe("string-input branch — unit tokens", () => {
    const cases = [
      { input: "7B", expected: 7, why: "b → as-is" },
      { input: "7b", expected: 7, why: "lowercased" },
      { input: "70B params", expected: 70, why: "regex anchors at b\\b; trailing text ignored" },
      { input: "1.5B", expected: 1.5, why: "decimal supported" },
      { input: "405b", expected: 405, why: "lowercased" },
      { input: "7 billion", expected: 7, why: "billion → as-is" },
      { input: "7bn", expected: 7, why: "bn alias" },
      { input: "1.2T", expected: 1200, why: "t → ×1000" },
      { input: "2 trillion", expected: 2000, why: "trillion → ×1000" },
      { input: "2T params", expected: 2000, why: "t\\b anchor; trailing text ignored" },
      { input: "3.5tn", expected: 3500, why: "tn alias" },
      { input: "560M", expected: 0.56, why: "m → ÷1000" },
      { input: "560 million", expected: 0.56, why: "million → ÷1000" },
      { input: "1000K", expected: 0.001, why: "k → ÷1_000_000" },
      { input: "1,500B", expected: 1500, why: "comma stripped" },
      { input: "7  B", expected: 7, why: "\\s* matches multiple spaces" },
    ]
    it.each(cases)("'$input' → $expected ($why)", ({ input, expected }) => {
      expect(parseParamsBillions(input)).toBe(expected)
    })
  })

  describe("string-input branch — parseFloat fallback (no unit token)", () => {
    const cases = [
      { input: "34.389", expected: 34.389, why: "no unit → parseFloat fallback" },
      { input: "7", expected: 7, why: "bare numeric → parseFloat fallback" },
      { input: "7Banana", expected: 7, why: "regex `b\\b` fails; parseFloat('7banana')=7. TS quirk: trailing junk allowed" },
      { input: "abc", expected: null, why: "no match, parseFloat NaN → null" },
      { input: "", expected: null, why: "trim empty → early return" },
      { input: "   ", expected: null, why: "trim empty → early return" },
    ]
    it.each(cases)("'$input' → $expected ($why)", ({ input, expected }) => {
      expect(parseParamsBillions(input)).toBe(expected)
    })
  })

  describe("string-input branch — TS quirks (positive-only filtering)", () => {
    it("'0B' → null (regex matches; amount=0 fails ≤0 check)", () => {
      expect(parseParamsBillions("0B")).toBe(null)
    })
    it("'-5' → null (parseFloat=-5; >0 reject)", () => {
      expect(parseParamsBillions("-5")).toBe(null)
    })
    it("'-5B' → 5 (regex matches `5b` substring; leading minus silently dropped)", () => {
      // TS quirk: `\d+` doesn't include `-`, but the regex isn't anchored at start,
      // so it scans past `-` and matches `5b`. amount=5 → returns 5 (NOT -5, NOT null).
      expect(parseParamsBillions("-5B")).toBe(5)
    })
  })

  describe("string-input branch — model names (Variant A on names)", () => {
    // Variant A is callable on any string; using it on model names exhibits
    // different behavior from Variant C because A uses `match()` (first match)
    // and a regex without leading `\b`.
    it("'Llama-3-70B-Instruct' → 70 (first match)", () => {
      expect(parseParamsBillions("Llama-3-70B-Instruct")).toBe(70)
    })
    it("'Llama-3-70B-Instruct-8K' → 70 (first match wins, NOT last like Variant C)", () => {
      expect(parseParamsBillions("Llama-3-70B-Instruct-8K")).toBe(70)
    })
    it("'Yi-1.5-34B-32K' → 34 (first match)", () => {
      expect(parseParamsBillions("Yi-1.5-34B-32K")).toBe(34)
    })
    it("'Mixtral-8x7B' → 7 (no leading \\b → matches `7b` inside `8x7b`)", () => {
      // TS quirk: A's regex has no `\b` before `\d+`, so it can start matching
      // mid-word. C/E/F all return null here because they DO require leading `\b`.
      expect(parseParamsBillions("Mixtral-8x7B")).toBe(7)
    })
  })
})

// ---------------------------------------------------------------------------
// Group B — Variant B (parseParamsBillionsFromText, eval-detail.tsx)
// ---------------------------------------------------------------------------

describe("Group B — parseParamsBillionsFromText (Variant B, eval-detail.tsx)", () => {
  describe("string inputs (mostly converges with Variant A)", () => {
    const cases = [
      { input: "7B", expected: 7 },
      { input: "1.5B", expected: 1.5 },
      { input: "1.2T", expected: 1200 },
      { input: "560M", expected: 0.56 },
      { input: "1000K", expected: 0.001 },
      { input: "7 billion", expected: 7 },
      { input: "34.389", expected: 34.389, why: "parseFloat fallback" },
      { input: "1,500B", expected: 1500 },
      { input: "7Banana", expected: 7, why: "parseFloat lenient; same as A" },
      { input: "abc", expected: null },
      { input: "", expected: null },
      { input: "   ", expected: null },
      { input: null, expected: null },
      { input: undefined, expected: null },
    ]
    it.each(cases)("'$input' → $expected", ({ input, expected }) => {
      expect(parseParamsBillionsFromText(input)).toBe(expected)
    })
  })

  describe("DIVERGES from Variant A — no ≤0 reject", () => {
    it("'0B' → 0 (B has no ≤0 check; A returns null)", () => {
      expect(parseParamsBillionsFromText("0B")).toBe(0)
      expect(parseParamsBillions("0B")).toBe(null)
    })
    it("'-5' → -5 (B has no >0 check; A returns null)", () => {
      expect(parseParamsBillionsFromText("-5")).toBe(-5)
      expect(parseParamsBillions("-5")).toBe(null)
    })
    it("'-5B' → 5 (matches `5b` substring; same as A)", () => {
      expect(parseParamsBillionsFromText("-5B")).toBe(5)
      expect(parseParamsBillions("-5B")).toBe(5)
    })
  })

  describe("rejects non-string inputs (DIVERGES from Variant A which is polymorphic)", () => {
    // Variant B is typed as string|null|undefined; passing a number falls through `if (!value)`
    // when value is 0, but otherwise goes through trim/lowercase which throws on non-string.
    it("number input is not supported by Variant B (Variant A handles it)", () => {
      expect(parseParamsBillions(7)).toBe(7)
      // parseParamsBillionsFromText(7) would throw at .trim() — don't call it
    })
  })
})

// ---------------------------------------------------------------------------
// Group C — Variant C (parseParamsBillionsFromModelName, eval-detail.tsx)
// ---------------------------------------------------------------------------

describe("Group C — parseParamsBillionsFromModelName (Variant C, eval-detail.tsx)", () => {
  describe("happy-path model names", () => {
    const cases = [
      { input: "Llama-3-70B-Instruct", expected: 70, why: "matchAll → only `70B`; last token; b → 70" },
      { input: "Phi-3.5-mini-3.8B", expected: 3.8, why: "matches `3.8B`" },
      { input: "Qwen2-7B-Instruct", expected: 7, why: "matches `7B`" },
      { input: "560M", expected: 0.56, why: "m → ÷1000" },
      { input: "1.2T", expected: 1200, why: "t → ×1000" },
      { input: "2K", expected: 0.000002, why: "k → ÷1_000_000" },
    ]
    it.each(cases)("'$input' → $expected ($why)", ({ input, expected }) => {
      expect(parseParamsBillionsFromModelNameC(input)).toBe(expected)
    })
  })

  describe("TS quirk — context-window suffix beats parameter count (last-token wins)", () => {
    it("'Llama-3-8B-Instruct-8K' → 0.000008 (last token = `8K`, NOT `8B`)", () => {
      expect(parseParamsBillionsFromModelNameC("Llama-3-8B-Instruct-8K")).toBe(0.000008)
    })
    it("'Llama-3-70B-Instruct-32K' → 0.000032 (last token = `32K`)", () => {
      expect(parseParamsBillionsFromModelNameC("Llama-3-70B-Instruct-32K")).toBe(0.000032)
    })
    it("'Yi-1.5-34B-32K' → 0.000032 (real production model name; returns context window)", () => {
      expect(parseParamsBillionsFromModelNameC("Yi-1.5-34B-32K")).toBe(0.000032)
    })
  })

  describe("regex anchoring quirks (leading \\b required)", () => {
    it("'Mixtral-8x7B' → null (no `\\b` between `x` and `7` → no match)", () => {
      expect(parseParamsBillionsFromModelNameC("Mixtral-8x7B")).toBe(null)
    })
    it("'7 billion' → null (single-letter unit only; `billion` doesn't match [tmbk])", () => {
      expect(parseParamsBillionsFromModelNameC("7 billion")).toBe(null)
    })
    it("'GPT-4' → null (no unit token)", () => {
      expect(parseParamsBillionsFromModelNameC("GPT-4")).toBe(null)
    })
  })

  describe("falsy inputs", () => {
    it.each([
      { input: "", expected: null },
      { input: null, expected: null },
      { input: undefined, expected: null },
    ])("$input → null", ({ input, expected }) => {
      expect(parseParamsBillionsFromModelNameC(input)).toBe(expected)
    })
  })
})

// ---------------------------------------------------------------------------
// Group D — Variant E (parseParamsBillionsFromModelName, model-compare-dialog.tsx)
// ---------------------------------------------------------------------------

describe("Group D (E) — parseParamsBillionsFromModelName (Variant E, model-compare-dialog.tsx)", () => {
  describe("converges with C on b|m inputs", () => {
    const cases = [
      { input: "Llama-3-70B-Instruct", expected: 70 },
      { input: "Phi-3.5-mini-3.8B", expected: 3.8 },
      { input: "560M", expected: 0.56 },
    ]
    it.each(cases)("'$input' → $expected", ({ input, expected }) => {
      expect(parseParamsBillionsFromModelNameE(input)).toBe(expected)
    })
  })

  describe("DIVERGES from C — rejects t and k", () => {
    it("'Llama-3-8B-Instruct-8K' → 8 (E ignores K; last `b|m` token = `8B`; C returns 0.000008)", () => {
      expect(parseParamsBillionsFromModelNameE("Llama-3-8B-Instruct-8K")).toBe(8)
      expect(parseParamsBillionsFromModelNameC("Llama-3-8B-Instruct-8K")).toBe(0.000008)
    })
    it("'Yi-1.5-34B-32K' → 34 (E ignores K; C returns 0.000032)", () => {
      expect(parseParamsBillionsFromModelNameE("Yi-1.5-34B-32K")).toBe(34)
      expect(parseParamsBillionsFromModelNameC("Yi-1.5-34B-32K")).toBe(0.000032)
    })
    it("'1.2T' → null (E rejects t)", () => {
      expect(parseParamsBillionsFromModelNameE("1.2T")).toBe(null)
      expect(parseParamsBillionsFromModelNameC("1.2T")).toBe(1200)
    })
    it("'2K' → null (E rejects k)", () => {
      expect(parseParamsBillionsFromModelNameE("2K")).toBe(null)
    })
  })

  describe("regex anchoring matches C", () => {
    it("'Mixtral-8x7B' → null (same as C — leading \\b fails)", () => {
      expect(parseParamsBillionsFromModelNameE("Mixtral-8x7B")).toBe(null)
    })
  })
})

// ---------------------------------------------------------------------------
// Group E (F) — Variant F (inline regex, app/evals/[id]/page.tsx)
// ---------------------------------------------------------------------------

describe("Group E (F) — inline regex on `name + ' ' + id` (Variant F, app/evals/[id]/page.tsx)", () => {
  describe("happy-path (b|B only)", () => {
    const cases = [
      { name: "Llama-3-70B-Instruct", id: "meta/llama-3-70b-instruct", expected: 70, why: "first 70B match" },
      { name: "1.5B-instruct", id: "meta/foo-1-5b", expected: 1.5, why: "first 1.5B match" },
    ]
    it.each(cases)("['$name' + '$id'] → $expected ($why)", ({ name, id, expected }) => {
      expect(parseParamsBillionsInline(name, id)).toBe(expected)
    })
  })

  describe("DIVERGES from C/E — first-match (not last-match) ordering", () => {
    it("name with both `8B` and `70B` → returns FIRST (8), Variant C returns LAST (70)", () => {
      expect(parseParamsBillionsInline("Llama-3-8B-70B-Instruct", "meta/llama-3-8b-70b")).toBe(8)
      expect(parseParamsBillionsFromModelNameC("Llama-3-8B-70B-Instruct")).toBe(70)
    })

    it("'Llama-3-70B-Instruct-8K' → 70 (8K not matched by [bB]; first 70B wins)", () => {
      // Variant F is *more correct* than C here because it ignores `K` entirely.
      expect(parseParamsBillionsInline("Llama-3-70B-Instruct-8K", "meta/llama-3-70b-instruct")).toBe(70)
    })

    it("'Yi-1.5-34B-32K' → 34 (real production name; F returns correct value, C returns context window)", () => {
      expect(parseParamsBillionsInline("Yi-1.5-34B-32K", "01-ai/yi-1-5-34b-32k")).toBe(34)
      expect(parseParamsBillionsFromModelNameC("Yi-1.5-34B-32K")).toBe(0.000032)
    })
  })

  describe("DIVERGES from A/B/C — only b|B accepted", () => {
    it("'560M' → null (F is B-only)", () => {
      expect(parseParamsBillionsInline("560M", "openai/foo-560m")).toBe(null)
    })
    it("'1.2T' → null (F is B-only)", () => {
      expect(parseParamsBillionsInline("1.2T", "openai/foo-1-2t")).toBe(null)
    })
    it("'GPT-4' → null (no B token at all)", () => {
      expect(parseParamsBillionsInline("GPT-4", "openai/gpt-4")).toBe(null)
    })
  })

  describe("regex anchoring matches C/E (leading \\b required)", () => {
    it("'Mixtral-8x7B' → null (same as C/E — `\\b` fails between `x` and `7`)", () => {
      expect(parseParamsBillionsInline("Mixtral-8x7B", "mistralai/mixtral-8x7b")).toBe(null)
    })
  })

  describe("uses concatenated name + id (not just name)", () => {
    it("name lacks B but id has it → still matches", () => {
      // e.g. raw model id might carry the `7b` token even if display name omits it
      expect(parseParamsBillionsInline("Llama 3", "meta/llama-3-7b")).toBe(7)
    })
  })

  describe("empty/falsy", () => {
    it("'' + '' → null", () => {
      expect(parseParamsBillionsInline("", "")).toBe(null)
    })
  })
})

// ---------------------------------------------------------------------------
// Group F — Cross-variant divergence (DOCUMENTED, NOT FIXED)
// ---------------------------------------------------------------------------
//
// The five variants produce different outputs for the same input.
// In production these don't usually disagree (because the input *type* per
// callsite is consistent: A sees clean numbers, B sees clean decimal strings,
// C/E/F see model-name strings).

describe("Group F — cross-variant divergence (TS quirks, do NOT fix)", () => {
  it("'0B' — A rejects (≤0); B/C/E accept; F accepts", () => {
    expect(parseParamsBillions("0B")).toBe(null)
    expect(parseParamsBillionsFromText("0B")).toBe(0)
    expect(parseParamsBillionsFromModelNameC("0B")).toBe(0)
    expect(parseParamsBillionsFromModelNameE("0B")).toBe(0)
    expect(parseParamsBillionsInline("0B", "")).toBe(0)
  })

  it("'-5' (string) — A rejects (>0); B accepts -5; C/E/F have no unit so return null", () => {
    expect(parseParamsBillions("-5")).toBe(null)
    expect(parseParamsBillionsFromText("-5")).toBe(-5)
    expect(parseParamsBillionsFromModelNameC("-5")).toBe(null)
    expect(parseParamsBillionsFromModelNameE("-5")).toBe(null)
    expect(parseParamsBillionsInline("-5", "")).toBe(null)
  })

  it("'7 billion' — A and B parse to 7; C/E/F have no full-word `billion` → null", () => {
    expect(parseParamsBillions("7 billion")).toBe(7)
    expect(parseParamsBillionsFromText("7 billion")).toBe(7)
    expect(parseParamsBillionsFromModelNameC("7 billion")).toBe(null)
    expect(parseParamsBillionsFromModelNameE("7 billion")).toBe(null)
    expect(parseParamsBillionsInline("7 billion", "")).toBe(null)
  })

  it("'1.2T' — A/B/C accept; E/F reject (no `t` unit)", () => {
    expect(parseParamsBillions("1.2T")).toBe(1200)
    expect(parseParamsBillionsFromText("1.2T")).toBe(1200)
    expect(parseParamsBillionsFromModelNameC("1.2T")).toBe(1200)
    expect(parseParamsBillionsFromModelNameE("1.2T")).toBe(null)
    expect(parseParamsBillionsInline("1.2T", "")).toBe(null)
  })

  it("'560M' — A/B/C/E accept; F rejects (no `m` unit)", () => {
    expect(parseParamsBillions("560M")).toBe(0.56)
    expect(parseParamsBillionsFromText("560M")).toBe(0.56)
    expect(parseParamsBillionsFromModelNameC("560M")).toBe(0.56)
    expect(parseParamsBillionsFromModelNameE("560M")).toBe(0.56)
    expect(parseParamsBillionsInline("560M", "")).toBe(null)
  })

  it("'Mixtral-8x7B' — A/B accept (regex has no leading \\b → matches `7b` inside `8x7b`); C/E/F reject", () => {
    // Most striking divergence: A and B return 7, all model-name parsers return null.
    expect(parseParamsBillions("Mixtral-8x7B")).toBe(7)
    expect(parseParamsBillionsFromText("Mixtral-8x7B")).toBe(7)
    expect(parseParamsBillionsFromModelNameC("Mixtral-8x7B")).toBe(null)
    expect(parseParamsBillionsFromModelNameE("Mixtral-8x7B")).toBe(null)
    expect(parseParamsBillionsInline("Mixtral-8x7B", "mistralai/mixtral-8x7b")).toBe(null)
  })

  it("'Llama-3-8B-Instruct-8K' — A/B/F return 8/8/8 (first match or [bB]-only); C returns 0.000008; E returns 8", () => {
    // A and B both use match() (first match) on a leading-anchor-free regex → first
    // match is `8B` → 8. C uses matchAll() (last match) and accepts `K` → `8K` → 0.000008.
    // E uses matchAll() but rejects `K` → last `b|m` token = `8B` → 8. F is [bB]-only,
    // first match → `8B` → 8.
    expect(parseParamsBillions("Llama-3-8B-Instruct-8K")).toBe(8)
    expect(parseParamsBillionsFromText("Llama-3-8B-Instruct-8K")).toBe(8)
    expect(parseParamsBillionsFromModelNameC("Llama-3-8B-Instruct-8K")).toBe(0.000008)
    expect(parseParamsBillionsFromModelNameE("Llama-3-8B-Instruct-8K")).toBe(8)
    expect(parseParamsBillionsInline("Llama-3-8B-Instruct-8K", "meta/llama-3-8b-8k")).toBe(8)
  })

  it("'Yi-1.5-34B-32K' (real production name) — only Variant C is wrong (returns context window)", () => {
    expect(parseParamsBillions("Yi-1.5-34B-32K")).toBe(34)
    expect(parseParamsBillionsFromText("Yi-1.5-34B-32K")).toBe(34)
    expect(parseParamsBillionsFromModelNameC("Yi-1.5-34B-32K")).toBe(0.000032)
    expect(parseParamsBillionsFromModelNameE("Yi-1.5-34B-32K")).toBe(34)
    expect(parseParamsBillionsInline("Yi-1.5-34B-32K", "01-ai/yi-1-5-34b-32k")).toBe(34)
  })

  it("name with multiple B-tokens — first vs last divergence (F vs C/E)", () => {
    // Synthetic: `Llama-3-8B-70B-Instruct` — first is 8B, last is 70B
    expect(parseParamsBillionsInline("Llama-3-8B-70B-Instruct", "")).toBe(8) // F: first
    expect(parseParamsBillionsFromModelNameC("Llama-3-8B-70B-Instruct")).toBe(70) // C: last
    expect(parseParamsBillionsFromModelNameE("Llama-3-8B-70B-Instruct")).toBe(70) // E: last
    expect(parseParamsBillions("Llama-3-8B-70B-Instruct")).toBe(8) // A: first via match()
    expect(parseParamsBillionsFromText("Llama-3-8B-70B-Instruct")).toBe(8) // B: first via match()
  })

  it("clean production-shaped inputs — all variants converge", () => {
    // The empirical reason this divergence rarely fires: in production, A/B see
    // `additional_details.params_billions` strings like "34.389" (clean decimal),
    // while C/E/F see model names like "Llama-3-70B-Instruct" (single B-token,
    // no context-window suffix). For these inputs all variants agree.
    expect(parseParamsBillions("34.389")).toBe(34.389)
    expect(parseParamsBillionsFromText("34.389")).toBe(34.389)
    // C/E/F can't handle bare decimals (no unit) but they're not given them
    expect(parseParamsBillionsFromModelNameC("Llama-3-70B-Instruct")).toBe(70)
    expect(parseParamsBillionsFromModelNameE("Llama-3-70B-Instruct")).toBe(70)
    expect(parseParamsBillionsInline("Llama-3-70B-Instruct", "meta/llama-3-70b-instruct")).toBe(70)
  })
})
