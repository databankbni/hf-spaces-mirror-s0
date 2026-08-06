import { describe, expect, it } from "vitest"

// Executable spec for the developer-name-canonicalization transformation.
//
// Replicates KNOWN_DEVELOPER_NAMES + normalizeDeveloperName from
// lib/model-data.ts verbatim.

const KNOWN_DEVELOPER_NAMES: Record<string, string> = {
  openai: "OpenAI",
  google: "Google",
  anthropic: "Anthropic",
  meta: "Meta",
  microsoft: "Microsoft",
  mistralai: "Mistral AI",
  deepseek: "DeepSeek",
  "deepseek-ai": "DeepSeek",
  cohere: "Cohere",
  nvidia: "NVIDIA",
  alibaba: "Alibaba",
  amazon: "Amazon",
  apple: "Apple",
  ibm: "IBM",
  xai: "xAI",
  "x-ai": "xAI",
}

function normalizeDeveloperName(name: string): string {
  const key = name.trim().toLowerCase()
  if (KNOWN_DEVELOPER_NAMES[key]) return KNOWN_DEVELOPER_NAMES[key]
  if (name === name.toLowerCase() && /^[a-z]/.test(name)) {
    return name.charAt(0).toUpperCase() + name.slice(1)
  }
  return name
}

// ---------------------------------------------------------------------------
// Group A — Map hits (case-insensitive lookup, may be substantive transform)
// ---------------------------------------------------------------------------

describe("Group A — KNOWN_DEVELOPER_NAMES map hits", () => {
  const cases = [
    { input: "openai", expected: "OpenAI", why: "case fix" },
    { input: "OpenAI", expected: "OpenAI", why: "case-insensitive lookup → same canonical form" },
    { input: "OPENAI", expected: "OpenAI", why: "case-insensitive lookup" },
    { input: "google", expected: "Google" },
    { input: "Google", expected: "Google" },
    { input: "anthropic", expected: "Anthropic" },
    { input: "Anthropic", expected: "Anthropic" },
    { input: "meta", expected: "Meta" },
    { input: "microsoft", expected: "Microsoft" },
    { input: "mistralai", expected: "Mistral AI", why: "substantive transform: space added" },
    { input: "MistralAI", expected: "Mistral AI", why: "case-insensitive substantive transform" },
    { input: "MISTRALAI", expected: "Mistral AI" },
    { input: "deepseek", expected: "DeepSeek" },
    { input: "deepseek-ai", expected: "DeepSeek", why: "substantive transform: -ai suffix dropped" },
    { input: "DeepSeek-AI", expected: "DeepSeek", why: "case-insensitive" },
    { input: "DEEPSEEK-AI", expected: "DeepSeek" },
    { input: "cohere", expected: "Cohere" },
    { input: "nvidia", expected: "NVIDIA", why: "uppercase" },
    { input: "NVIDIA", expected: "NVIDIA" },
    { input: "alibaba", expected: "Alibaba" },
    { input: "amazon", expected: "Amazon" },
    { input: "apple", expected: "Apple" },
    { input: "ibm", expected: "IBM", why: "uppercase" },
    { input: "IBM", expected: "IBM" },
    { input: "xai", expected: "xAI", why: "mid-word capital" },
    { input: "XAI", expected: "xAI" },
    { input: "x-ai", expected: "xAI", why: "alias key for xAI" },
    { input: "X-AI", expected: "xAI" },
  ]
  it.each(cases)("'$input' → '$expected'", ({ input, expected }) => {
    expect(normalizeDeveloperName(input)).toBe(expected)
  })
})

// ---------------------------------------------------------------------------
// Group B — Title-case fallback (lowercase input not in map)
// ---------------------------------------------------------------------------

describe("Group B — title-case fallback for lowercase non-map inputs", () => {
  const cases = [
    { input: "jaspionjader", expected: "Jaspionjader", why: "lowercase + starts [a-z] → first-char uppercase" },
    { input: "allenai", expected: "Allenai", why: "lowercase + not in map (note: not 'Allen AI'; would need a map entry for that)" },
    { input: "bunnycore", expected: "Bunnycore" },
    { input: "zelk12", expected: "Zelk12", why: "digits inside don't matter" },
    { input: "qwen", expected: "Qwen", why: "lowercase qwen → Qwen via title-case (NOT in the map; map has no qwen entry)" },
    { input: "a", expected: "A", why: "single char lowercase → uppercase" },
  ]
  it.each(cases)("'$input' → '$expected' ($why)", ({ input, expected }) => {
    expect(normalizeDeveloperName(input)).toBe(expected)
  })
})

// ---------------------------------------------------------------------------
// Group C — Passthrough (mixed case, not in map)
// ---------------------------------------------------------------------------

describe("Group C — passthrough for mixed-case non-map inputs", () => {
  const cases = [
    { input: "JayHyeon", expected: "JayHyeon", why: "already has uppercase → not lowercase → passthrough" },
    { input: "DreadPoor", expected: "DreadPoor" },
    { input: "Qwen", expected: "Qwen", why: "Qwen NOT in map; capitalized form passes through" },
    { input: "prithivMLmods", expected: "prithivMLmods", why: "mixed case but starts lowercase — note: NOT title-cased! lowercase check `name === name.toLowerCase()` fails because of internal uppercase letters" },
    { input: "Quazim0t0", expected: "Quazim0t0", why: "mixed case + digits" },
    { input: "01-ai", expected: "01-ai", why: "01-ai NOT in map; starts with digit → fails /^[a-z]/ → passthrough" },
    { input: "01_ai", expected: "01_ai", why: "same — starts with digit" },
    { input: "01-hero", expected: "01-hero", why: "same — starts with digit, title-case rule fails" },
    { input: "1-800-llms", expected: "1-800-llms", why: "starts with digit" },
  ]
  it.each(cases)("'$input' → '$expected' ($why)", ({ input, expected }) => {
    expect(normalizeDeveloperName(input)).toBe(expected)
  })
})

// ---------------------------------------------------------------------------
// Group D — Edge cases
// ---------------------------------------------------------------------------

describe("Group D — edge cases", () => {
  it("leading/trailing whitespace on map name — trim happens for key lookup, original returned", () => {
    expect(normalizeDeveloperName("  google  ")).toBe("Google")
  })

  it("leading whitespace on non-map lowercase name — title-case rule does NOT fire, passes through with whitespace", () => {
    // key = "jaspionjader" → no map hit
    // name === name.toLowerCase() is true ("  jaspionjader  " === "  jaspionjader  ")
    // but /^[a-z]/.test("  jaspionjader  ") is FALSE (starts with space)
    // → falls to passthrough (returns unchanged including whitespace)
    expect(normalizeDeveloperName("  jaspionjader  ")).toBe("  jaspionjader  ")
  })

  it("empty string → empty string", () => {
    // key = "" → no map hit
    // name === name.toLowerCase() is true
    // /^[a-z]/.test("") is false
    // → passthrough
    expect(normalizeDeveloperName("")).toBe("")
  })

  it("whitespace-only string → whitespace-only string", () => {
    expect(normalizeDeveloperName("   ")).toBe("   ")
  })
})
