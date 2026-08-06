import { describe, expect, it } from "vitest"

// Executable spec for the slug-candidates transformation.
//
// Replicates pipelineSlugify, getModelDetailSlugCandidates, and
// getDeveloperSlugCandidates from lib/model-data.ts verbatim.
// Pipeline must produce identical outputs for every case below.

function pipelineSlugify(text: string): string {
  return (
    text
      .replace(/[\x00-\x1f\x7f]/g, "")
      .replace(/[^a-zA-Z0-9._-]/g, "_")
      .replace(/^_+|_+$/g, "") || "unknown"
  )
}

function getModelDetailSlugCandidates(modelId: string): string[] {
  const normalized = modelId.trim()
  const candidates = new Set<string>()
  const withSlash = normalized.replace(/\//g, "__")
  const withDots = withSlash.replace(/\./g, "-")
  candidates.add(pipelineSlugify(withSlash))
  candidates.add(pipelineSlugify(withSlash.toLowerCase()))
  candidates.add(pipelineSlugify(withDots))
  candidates.add(pipelineSlugify(withDots.toLowerCase()))
  candidates.add(pipelineSlugify(normalized))
  candidates.add(pipelineSlugify(normalized.toLowerCase()))
  return Array.from(candidates)
}

function getDeveloperSlugCandidates(developerOrRouteId: string): string[] {
  const normalized = developerOrRouteId.trim()
  const candidates = new Set<string>()
  const lowercase = normalized.toLowerCase()
  const underscoreSlug = pipelineSlugify(normalized)
  const lowercaseUnderscoreSlug = pipelineSlugify(lowercase)
  const hyphenSlug = lowercase
    .replace(/[\x00-\x1f\x7f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
  const compactSlug = lowercase.replace(/[^a-z0-9]+/g, "")
  candidates.add(underscoreSlug)
  candidates.add(lowercaseUnderscoreSlug)
  candidates.add(underscoreSlug.replace(/_/g, "-"))
  candidates.add(lowercaseUnderscoreSlug.replace(/_/g, "-"))
  if (hyphenSlug) candidates.add(hyphenSlug)
  if (compactSlug) candidates.add(compactSlug)
  return Array.from(candidates)
}

// ---------------------------------------------------------------------------
// Group A — pipelineSlugify
// ---------------------------------------------------------------------------

describe("Group A — pipelineSlugify", () => {
  const cases = [
    { input: "openai__gpt-5", expected: "openai__gpt-5", why: "passthrough (alnum + dash + underscore)" },
    { input: "openai__gpt-5.2", expected: "openai__gpt-5.2", why: "passthrough (dot allowed)" },
    { input: "openai/gpt-5", expected: "openai_gpt-5", why: "slash → underscore (slash not in allowed set)" },
    { input: "OpenAI", expected: "OpenAI", why: "case preserved" },
    { input: "x0000001", expected: "x0000001", why: "passthrough" },
    { input: "foo bar", expected: "foo_bar", why: "space → underscore" },
    { input: "foo!@#bar", expected: "foo___bar", why: "each special char → underscore" },
    { input: "___foo___", expected: "foo", why: "trim leading/trailing underscores" },
    { input: "!!!", expected: "unknown", why: "empty after trim → 'unknown' fallback" },
    { input: "", expected: "unknown", why: "empty → 'unknown' fallback" },
    { input: "_", expected: "unknown", why: "single underscore trimmed → empty → 'unknown'" },
    { input: "a.b.c", expected: "a.b.c", why: "dots passthrough" },
    { input: "a-b-c", expected: "a-b-c", why: "dashes passthrough" },
  ]
  it.each(cases)("'$input' → '$expected' ($why)", ({ input, expected }) => {
    expect(pipelineSlugify(input)).toBe(expected)
  })
})

// ---------------------------------------------------------------------------
// Group B — getModelDetailSlugCandidates
// ---------------------------------------------------------------------------

describe("Group B — getModelDetailSlugCandidates", () => {
  const cases = [
    {
      input: "openai/gpt-5",
      expected: ["openai__gpt-5", "openai_gpt-5"],
      why: "lowercase + no dots → only slash + slash-stripped variants survive Set dedup",
    },
    {
      input: "openai/gpt-5.2",
      expected: ["openai__gpt-5.2", "openai__gpt-5-2", "openai_gpt-5.2"],
      why: "dotted form → slash, slash+dot-stripped, fallback",
    },
    {
      input: "OpenAI/GPT-5",
      expected: ["OpenAI__GPT-5", "openai__gpt-5", "OpenAI_GPT-5", "openai_gpt-5"],
      why: "mixed case → both case variants survive",
    },
    {
      input: "anthropic/claude-3.7-sonnet",
      expected: ["anthropic__claude-3.7-sonnet", "anthropic__claude-3-7-sonnet", "anthropic_claude-3.7-sonnet"],
      why: "dotted version variant",
    },
    {
      input: "unknown/foo",
      expected: ["unknown__foo", "unknown_foo"],
      why: "lowercase + no dots → 2 candidates",
    },
    {
      input: "openai__gpt-5",
      expected: ["openai__gpt-5"],
      why: "no slashes, no dots, lowercase → all variants collapse to one",
    },
  ]
  it.each(cases)("'$input' → $expected ($why)", ({ input, expected }) => {
    expect(getModelDetailSlugCandidates(input)).toEqual(expected)
  })
})

// ---------------------------------------------------------------------------
// Group C — getDeveloperSlugCandidates
// ---------------------------------------------------------------------------

describe("Group C — getDeveloperSlugCandidates", () => {
  const cases = [
    {
      input: "openai",
      expected: ["openai"],
      why: "lowercase + no special chars → all 6 variants collapse to one",
    },
    {
      input: "OpenAI",
      expected: ["OpenAI", "openai"],
      why: "case-mixed → 2 candidates (the case variant differs)",
    },
    {
      input: "01-ai",
      expected: ["01-ai", "01ai"],
      why: "compactSlug strips the dash → 2 candidates",
    },
    {
      input: "Mistral AI",
      expected: ["Mistral_AI", "mistral_ai", "Mistral-AI", "mistral-ai", "mistralai"],
      why: "space → underscore variants + hyphen variants + compact",
    },
    {
      input: "01_ai",
      expected: ["01_ai", "01-ai", "01ai"],
      why: "underscore-slug + dash variant + compact",
    },
    {
      input: "Allenai",
      expected: ["Allenai", "allenai"],
      why: "case-mixed but no special chars",
    },
  ]
  it.each(cases)("'$input' → $expected ($why)", ({ input, expected }) => {
    expect(getDeveloperSlugCandidates(input)).toEqual(expected)
  })
})

// ---------------------------------------------------------------------------
// Group D — Production sanity (fixture-based)
// ---------------------------------------------------------------------------
//
// Concrete production cases from the audit (2026-04-28). For each, document
// which candidate position resolves to the actual file. These are the cases
// the pipeline-side fix needs to make redundant.

describe("Group D — production sanity (which candidate position wins)", () => {
  it("openai/gpt-5.2 needs the dot→dash variant (position 1)", () => {
    const candidates = getModelDetailSlugCandidates("openai/gpt-5.2")
    expect(candidates[0]).toBe("openai__gpt-5.2") // would be the file IF cache used dotted form (it doesn't)
    expect(candidates[1]).toBe("openai__gpt-5-2") // this is what actually exists in cache
  })

  it("anthropic/claude-3.7-sonnet needs the dot→dash variant (position 1)", () => {
    const candidates = getModelDetailSlugCandidates("anthropic/claude-3.7-sonnet")
    expect(candidates).toContain("anthropic__claude-3-7-sonnet")
  })

  it("OpenAI developer needs lowercase variant (position 1)", () => {
    const candidates = getDeveloperSlugCandidates("Google")
    expect(candidates).toEqual(["Google", "google"])
  })

  it("Allenai developer needs lowercase variant (position 1)", () => {
    const candidates = getDeveloperSlugCandidates("Allenai")
    expect(candidates).toEqual(["Allenai", "allenai"])
  })
})
