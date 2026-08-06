import { describe, expect, it } from "vitest"

// Executable spec for the dataset-url-synthesis transformation.
//
// Replicates the 4-step fallback chain from components/eval-card.tsx
// verbatim. Pipeline must produce identical outputs for every case below.
// Verify cross-corpus equivalence with `scripts/verify-dataset-url.mjs`.

interface SourceData {
  dataset_url?: string
  url?: string | string[] | null
  hf_repo?: string
  [key: string]: unknown
}

// Replicates the actual TS expression verbatim. The original uses `??`
// (nullish coalescing), NOT `||` truthiness — so empty strings stay; only
// null/undefined fall through. Don't "improve" by switching to truthiness.
function resolveDatasetUrl(sourceData: SourceData | null | undefined): string | undefined {
  const fromDataset = sourceData?.dataset_url
  const fromUrl = Array.isArray(sourceData?.url) ? sourceData?.url?.[0] : sourceData?.url
  const fromHfRepo = sourceData?.hf_repo ? `https://huggingface.co/datasets/${sourceData.hf_repo}` : undefined
  return fromDataset ?? fromUrl ?? fromHfRepo
}

// ---------------------------------------------------------------------------
// Group A — Branch firing order (first non-nullish wins, NOT truthy)
// ---------------------------------------------------------------------------

describe("Group A — branch firing order", () => {
  const cases = [
    { input: { dataset_url: "https://example.com/x" }, expected: "https://example.com/x", why: "branch 1" },
    { input: { dataset_url: "x", url: ["y"] }, expected: "x", why: "branch 1 short-circuits even with url present" },
    { input: { url: ["https://a.com", "https://b.com"] }, expected: "https://a.com", why: "branch 2 — first array element" },
    { input: { url: ["only"] }, expected: "only", why: "branch 2 — single-element array" },
    { input: { url: "https://a.com" }, expected: "https://a.com", why: "branch 3 — string form" },
    { input: { hf_repo: "Mercor/ACE" }, expected: "https://huggingface.co/datasets/Mercor/ACE", why: "branch 4 — HF template" },
    {
      input: { hf_repo: "mercor/apex-agents" },
      expected: "https://huggingface.co/datasets/mercor/apex-agents",
      why: "branch 4 — preserves case",
    },
    { input: { dataset_name: "x" }, expected: undefined, why: "branch 5 — none of the above" },
    { input: {}, expected: undefined, why: "branch 5 — empty object" },
    { input: null, expected: undefined, why: "branch 5 — null defensive" },
    { input: undefined, expected: undefined, why: "branch 5 — undefined defensive" },
  ]
  it.each(cases)("$why → '$expected'", ({ input, expected }) => {
    expect(resolveDatasetUrl(input as SourceData | null | undefined)).toBe(expected)
  })
})

// ---------------------------------------------------------------------------
// Group B — Edge cases of the fallback chain
// ---------------------------------------------------------------------------

describe("Group B — fallback chain edge cases (?? nullish semantics)", () => {
  it("empty dataset_url string is RETURNED (not nullish, ?? does NOT fall through)", () => {
    // "" is not nullish — ?? short-circuits to it. TS quirk to preserve.
    expect(resolveDatasetUrl({ dataset_url: "", url: ["fallback"] })).toBe("")
  })

  it("empty url array — url[0] is undefined, ?? falls through to hf_repo", () => {
    expect(resolveDatasetUrl({ url: [], hf_repo: "x/y" })).toBe("https://huggingface.co/datasets/x/y")
  })

  it("url array containing only empty string — returns empty string (NO further fallback because '' is not nullish)", () => {
    expect(resolveDatasetUrl({ url: [""], hf_repo: "x/y" })).toBe("")
  })

  it("url array containing only null — null IS nullish, ?? falls through to hf_repo", () => {
    expect(resolveDatasetUrl({ url: [null as unknown as string], hf_repo: "x/y" })).toBe(
      "https://huggingface.co/datasets/x/y"
    )
  })

  it("url array short-circuits hf_repo when first element is truthy", () => {
    expect(resolveDatasetUrl({ url: ["a"], hf_repo: "x/y" })).toBe("a")
  })

  it("empty hf_repo evaluated as falsy by inline ternary, falls through to undefined", () => {
    // The hf_repo branch uses `sourceData.hf_repo ? template : undefined`,
    // a truthiness check (NOT ??), so empty string is treated as falsy.
    expect(resolveDatasetUrl({ hf_repo: "" })).toBe(undefined)
  })

  it("hf_repo with leading slash produces double-slash URL (no normalization)", () => {
    expect(resolveDatasetUrl({ hf_repo: "/leading-slash" })).toBe(
      "https://huggingface.co/datasets//leading-slash"
    )
  })
})

// ---------------------------------------------------------------------------
// Group C — Production fixtures (real source_data shapes from prod cache)
// ---------------------------------------------------------------------------

describe("Group C — production fixtures", () => {
  const cases = [
    {
      input: { dataset_name: "appworld/test_normal", source_type: "url", url: ["https://github.com/Exgentic/exgentic"] },
      expected: "https://github.com/Exgentic/exgentic",
      why: "url-array path (564/587 eval-details use this)",
    },
    {
      input: { dataset_name: "ace", source_type: "hf_dataset", hf_repo: "Mercor/ACE" },
      expected: "https://huggingface.co/datasets/Mercor/ACE",
      why: "hf_repo template (22/587)",
    },
    {
      input: {
        dataset_name: "Artificial Analysis LLM API",
        source_type: "url",
        url: ["https://artificialanalysis.ai/api/v2/data/llms/models"],
      },
      expected: "https://artificialanalysis.ai/api/v2/data/llms/models",
      why: "third-party API URL",
    },
    {
      input: {
        dataset_name: "CocoaBench v1.0",
        source_type: "other",
        additional_details: { samples_number: "153" },
      },
      expected: undefined,
      why: "no url, no hf_repo, no dataset_url — branch 5 (1/587)",
    },
  ]
  it.each(cases)("$why → '$expected'", ({ input, expected }) => {
    expect(resolveDatasetUrl(input as SourceData)).toBe(expected)
  })
})
