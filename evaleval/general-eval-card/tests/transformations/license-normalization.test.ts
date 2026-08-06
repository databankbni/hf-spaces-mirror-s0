import { describe, expect, it } from "vitest"

// Executable spec for the license-normalization transformation.
//
// These tests describe the `shortenLicense` function as it currently runs in
// production (components/eval-card.tsx). Quirks (lowercase SPDX
// identifiers passing through, free-form CC BY descriptions truncating, the
// asymmetric length>24 vs slice(0,22) cut) are preserved on purpose. The
// migration target is to move this transformation upstream without changing
// what users see.
//
// Pipeline-side implementation must produce identical outputs for every
// case below. Verify cross-corpus equivalence with
// `scripts/verify-license.mjs` once pipeline ships.

// Reproduces the function verbatim so tests are independent of import path.
function shortenLicense(license: string | null | undefined): string {
  if (!license || license === "Not specified") return ""
  if (license.toLowerCase().includes("creative commons attribution 4")) return "CC BY 4.0"
  if (license.toLowerCase().includes("creative commons zero")) return "CC0"
  if (license.toLowerCase().includes("apache license 2") || license.toLowerCase().includes("apache 2")) return "Apache 2.0"
  if (license.toLowerCase().includes("mit license")) return "MIT"
  if (license.toLowerCase().includes("cc-by-sa")) return "CC BY-SA"
  if (license.length > 24) return license.slice(0, 22) + "…"
  return license
}

// ---------------------------------------------------------------------------
// Group A — Rule firing order (first match wins)
// ---------------------------------------------------------------------------

describe("Group A — rule firing order", () => {
  const cases = [
    { input: "Apache License 2.0", expected: "Apache 2.0", why: "rule 4 (matches 'apache license 2')" },
    { input: "Apache 2.0", expected: "Apache 2.0", why: "rule 4 (matches 'apache 2')" },
    { input: "MIT License", expected: "MIT", why: "rule 5" },
    { input: "Creative Commons Attribution 4.0", expected: "CC BY 4.0", why: "rule 2" },
    { input: "Creative Commons Zero v1.0 Universal", expected: "CC0", why: "rule 3" },
    { input: "cc-by-sa-3.0", expected: "CC BY-SA", why: "rule 6" },
    {
      input: "Open Data Commons Attribution License",
      expected: "Open Data Commons Attr…",
      why: "rule 7 (truncate, length > 24, no other rule matches)",
    },
    {
      input: "The dataset is made available under a CC BY license.",
      expected: "The dataset is made av…",
      why: "rule 7 — prose form bypasses CC BY 4 rule (substring 'creative commons attribution 4' not present)",
    },
    {
      input: "apache-2.0",
      expected: "apache-2.0",
      why: "rule 8 (passthrough; SPDX lowercase doesn't contain 'apache license 2' or 'apache 2' with the required space)",
    },
    { input: "other", expected: "other", why: "rule 8 (passthrough, length ≤ 24)" },
    { input: "unknown", expected: "unknown", why: "rule 8 (passthrough, length ≤ 24)" },
    { input: "Not specified", expected: "", why: "rule 1 (sentinel for 'no license')" },
    { input: "", expected: "", why: "rule 1 (empty)" },
    { input: null, expected: "", why: "rule 1 (null short-circuits via falsy)" },
    { input: undefined, expected: "", why: "rule 1 (undefined short-circuits via falsy)" },
  ]
  it.each(cases)("'$input' → '$expected' ($why)", ({ input, expected }) => {
    expect(shortenLicense(input)).toBe(expected)
  })
})

// ---------------------------------------------------------------------------
// Group B — Truncation rule edge cases
// ---------------------------------------------------------------------------

describe("Group B — truncation rule", () => {
  const cases = [
    {
      input: "x".repeat(24),
      expected: "x".repeat(24),
      why: "exactly 24 chars passes through (length > 24 is the cutoff, not >= 24)",
    },
    {
      input: "x".repeat(25),
      expected: "x".repeat(22) + "…",
      why: "25 chars truncates — first 22 + ellipsis",
    },
    {
      input: "x".repeat(50),
      expected: "x".repeat(22) + "…",
      why: "50 chars truncates to same first-22 form",
    },
    {
      input: "the MIT license is awesome, very based",
      expected: "MIT",
      why: "rule 5 fires before rule 7 — substring 'mit license' matches even within longer prose",
    },
    {
      input: "some apache 2 thing that is long",
      expected: "Apache 2.0",
      why: "rule 4 fires before rule 7 — substring match wins",
    },
    {
      input: "MIT-like license that is custom and long",
      expected: "MIT-like license that …",
      why: "rule 5 does NOT fire — substring 'mit license' (with space) isn't present in 'mit-like license' (with hyphen between)",
    },
  ]
  it.each(cases)("'$input' → '$expected' ($why)", ({ input, expected }) => {
    expect(shortenLicense(input)).toBe(expected)
  })
})

// ---------------------------------------------------------------------------
// Group C — Case sensitivity
// ---------------------------------------------------------------------------

describe("Group C — case insensitivity in match rules", () => {
  const cases = [
    { input: "APACHE LICENSE 2.0", expected: "Apache 2.0" },
    { input: "apache license 2.0", expected: "Apache 2.0" },
    { input: "Apache License 2.0", expected: "Apache 2.0" },
    { input: "creative commons attribution 4.0", expected: "CC BY 4.0" },
    { input: "CREATIVE COMMONS ATTRIBUTION 4.0", expected: "CC BY 4.0" },
    { input: "Creative Commons Attribution 4.0 International", expected: "CC BY 4.0" },
    { input: "CREATIVE COMMONS ZERO v1.0", expected: "CC0" },
    { input: "Mit License", expected: "MIT" },
    { input: "MIT LICENSE", expected: "MIT" },
    { input: "CC-BY-SA-4.0", expected: "CC BY-SA" },
  ]
  it.each(cases)("'$input' → '$expected'", ({ input, expected }) => {
    expect(shortenLicense(input)).toBe(expected)
  })
})

// ---------------------------------------------------------------------------
// Group D — Production fixtures (the 11 distinct license strings observed
// in .cache/hf-data/benchmark-metadata.json on 2026-04-28)
// ---------------------------------------------------------------------------

describe("Group D — production fixtures (all 11 distinct license strings observed)", () => {
  const cases = [
    { input: "Not specified", expected: "" },
    { input: "Apache License 2.0", expected: "Apache 2.0" },
    { input: "MIT License", expected: "MIT" },
    { input: "Open Data Commons Attribution License", expected: "Open Data Commons Attr…" },
    { input: "Creative Commons Attribution 4.0", expected: "CC BY 4.0" },
    { input: "cc-by-sa-3.0", expected: "CC BY-SA" },
    { input: "other", expected: "other" },
    { input: "unknown", expected: "unknown" },
    { input: "Creative Commons Zero v1.0 Universal", expected: "CC0" },
    { input: "apache-2.0", expected: "apache-2.0" },
    { input: "The dataset is made available under a CC BY license.", expected: "The dataset is made av…" },
  ]
  it.each(cases)("'$input' → '$expected'", ({ input, expected }) => {
    expect(shortenLicense(input)).toBe(expected)
  })
})
