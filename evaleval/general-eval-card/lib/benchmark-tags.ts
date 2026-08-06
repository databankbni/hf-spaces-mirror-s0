/**
 * Benchmark tag lookup, primary source for filtering pills on the evals
 * index. Resolves a benchmark or family display name to a list of
 * categorical tags drawn from data/benchmarks/categories.json (a curated
 * mapping of ~550 benchmark names → 1+ tags). Names that aren't in the
 * file fall back to inferCategoryFromBenchmark() so every benchmark gets
 * at least one tag.
 *
 * The ref file uses a richer vocabulary (mathematics,
 * software_engineering, multimodal, hallucination, robustness, finance,
 * law, …) than the legacy 5-bucket CategoryType. The fallback is
 * projected into ref vocabulary (FALLBACK_TO_REF below) so the filter
 * UI sees a single set of pills.
 */
import categoriesJson from "@/data/benchmarks/categories.json"
import type {
  EvalHierarchy,
  HierarchyBenchmark,
  HierarchyComposite,
  HierarchyFamily,
  HierarchySlice,
} from "@/lib/backend-artifacts"
import { inferTagsFromBenchmark } from "@/lib/benchmark-schema"

const REF: Record<string, string[]> = categoriesJson as Record<string, string[]>

// Two normalized lookup tables built once at module load. The first
// keeps spaces (so "MMLU Pro" still differs from "MMLUPro" if both
// were ever in the file); the second strips everything non-alphanumeric
// for a tolerant fallback ("ARC-C" ↔ "arc c" ↔ "arcc").
const NORMALIZED_LOOSE: Map<string, string[]> = new Map()
const NORMALIZED_TIGHT: Map<string, string[]> = new Map()

function normalizeLoose(name: string): string {
  return name.trim().toLowerCase().replace(/\s+/g, " ")
}

function normalizeTight(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]/g, "")
}

// Strip trailing "(...)" segments — applied to QUERY names only, not
// to ref keys. Without this, hierarchy children like
//   "Humanity's Last Exam (accuracy)"
//   "SWE-bench Verified Mini (MariusHobbhahn)"
// miss their parent ref entries that lack the parenthesised suffix.
// Iterates because some names have multiple suffixes ("Foo (a) (b)").
function stripParenSuffix(name: string): string {
  let prev = name
  let cur = name.replace(/\s*\([^)]*\)\s*$/, "").trim()
  while (cur && cur !== prev) {
    prev = cur
    cur = cur.replace(/\s*\([^)]*\)\s*$/, "").trim()
  }
  return cur
}

for (const [name, tags] of Object.entries(REF)) {
  NORMALIZED_LOOSE.set(normalizeLoose(name), tags)
  const tight = normalizeTight(name)
  if (tight && !NORMALIZED_TIGHT.has(tight)) NORMALIZED_TIGHT.set(tight, tags)
}

/**
 * Resolve one or more candidate names to a tag list. Match priority,
 * tried for each candidate in order:
 *   1. loose match (case-insensitive, whitespace-collapsed)
 *   2. tight match (alphanumeric-only)
 *   3. strip trailing "(suffix)" segments and retry loose match
 * If nothing matches, inherits `parentTags` (when non-empty) so a
 * child benchmark of a curated family does not get a noisy regex
 * fallback. Final fallback is `inferCategoryFromBenchmark` projected
 * into the ref vocabulary.
 */
export function getBenchmarkTags(
  parentTags: string[] | null | undefined,
  ...candidates: Array<string | null | undefined>
): string[] {
  const names = candidates.filter((n): n is string => typeof n === "string" && n.trim().length > 0)
  for (const name of names) {
    const loose = NORMALIZED_LOOSE.get(normalizeLoose(name))
    if (loose) return loose
    const tight = NORMALIZED_TIGHT.get(normalizeTight(name))
    if (tight) return tight
    const stripped = stripParenSuffix(name)
    if (stripped && stripped !== name) {
      const loose2 = NORMALIZED_LOOSE.get(normalizeLoose(stripped))
      if (loose2) return loose2
      const tight2 = NORMALIZED_TIGHT.get(normalizeTight(stripped))
      if (tight2) return tight2
    }
  }
  // No own match. Prefer inheriting from a curated parent over the
  // regex fallback — trusts the curator's chosen tags rather than
  // injecting whatever the regex's substring matcher happens to
  // catch on the child name.
  if (parentTags && parentTags.length > 0) return parentTags
  // Final fallback: regex-based tag inference (17-tag vocabulary).
  return inferTagsFromBenchmark(names[0] ?? "")
}

/**
 * True iff at least one of the candidate names is present in the ref
 * file. Useful for surfacing "this benchmark was curated" affordances
 * separately from the auto-inferred fallback.
 */
export function hasCuratedTags(...candidates: Array<string | null | undefined>): boolean {
  for (const name of candidates) {
    if (typeof name !== "string" || !name.trim()) continue
    if (NORMALIZED_LOOSE.has(normalizeLoose(name))) return true
    if (NORMALIZED_TIGHT.has(normalizeTight(name))) return true
  }
  return false
}

/**
 * Walk an EvalHierarchy and attach `derivedTags: string[]` to every
 * family / composite / benchmark / slice. Inheritance flows top-down:
 * a child with no own ref hit inherits its nearest ancestor's tags
 * rather than falling to the regex fallback.
 *
 * Mutates in place — fetchEvalHierarchy passes the just-loaded object
 * straight in, so no allocations beyond the new tag arrays. Idempotent:
 * calling twice produces the same result.
 */
export function decorateHierarchyDerivedTags(h: EvalHierarchy): EvalHierarchy {
  // Idempotent guard: cleanHierarchy (server-side) tags fully-processed
  // hierarchies with `_evalCardCleaned`; subsequent client-side calls
  // skip the work entirely. Without the guard this would still produce
  // the same output (sanitiseName / unionTags are idempotent) but would
  // pay an unnecessary walk through every node on each fetch.
  if ((h as { _evalCardCleaned?: boolean })._evalCardCleaned) return h
  for (const fam of h.families ?? []) {
    sanitizeFamilyDisplayNames(fam)
    decorateFamily(fam)
  }
  return h
}

// Workaround for an upstream warehouse bug where some families inherit a
// sibling family's `display_name` (e.g. `math-mc` and `gsm-mc` both ship
// with "wasp (Writer's Assessor of System Performance)"). When the
// display_name shares no token with the entry's `key`, fall back to a
// readable rendering of the key.
function shareToken(displayName: string, key: string): boolean {
  const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "")
  const k = norm(key)
  if (!k) return true
  return norm(displayName).includes(k)
}

// Acronyms that should stay uppercase when humanizing a slug. Mirrors
// the set used in family-table.tsx; kept here so the sanitiser can
// produce the same output across surfaces.
const ACRONYMS = new Set([
  "ai", "aa", "api", "arc", "bbh", "bfcl", "cli", "cv", "gpqa", "gpt",
  "gsm", "hf", "hle", "llm", "llms", "mc", "ml", "mt", "nlp", "qa",
  "rl", "sql", "swe", "vlm", "vqa",
])

function humanizeKey(key: string): string {
  const parts = key.split(/[_\-\s]+/).filter(Boolean)
  if (parts.length === 0) return key
  return parts
    .map((word) => {
      const lower = word.toLowerCase()
      if (ACRONYMS.has(lower)) return word.toUpperCase()
      // Treat short all-letter parts (≤4 chars) as acronym-like.
      if (word.length <= 4 && /^[a-zA-Z]+$/.test(word)) return word.toUpperCase()
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
    })
    .join("-")
}

function sanitizeName(displayName: string | null | undefined, key: string): string {
  if (!displayName || !displayName.trim()) return humanizeKey(key)
  if (!shareToken(displayName, key)) return humanizeKey(key)
  return displayName
}

function sanitizeFamilyDisplayNames(fam: HierarchyFamily): void {
  fam.display_name = sanitizeName(fam.display_name, fam.key)
  for (const c of fam.composites ?? []) {
    c.display_name = sanitizeName(c.display_name, c.key)
    for (const b of c.benchmarks ?? []) {
      b.display_name = sanitizeName(b.display_name, b.key)
      for (const s of b.slices ?? []) s.display_name = sanitizeName(s.display_name, s.key)
    }
  }
  for (const b of fam.standalone_benchmarks ?? []) {
    b.display_name = sanitizeName(b.display_name, b.key)
    for (const s of b.slices ?? []) s.display_name = sanitizeName(s.display_name, s.key)
  }
  for (const b of fam.benchmarks ?? []) {
    b.display_name = sanitizeName(b.display_name, b.key)
    for (const s of b.slices ?? []) s.display_name = sanitizeName(s.display_name, s.key)
  }
}

function decorateFamily(fam: HierarchyFamily): void {
  fam.derivedTags = getBenchmarkTags(null, fam.display_name, fam.key)
  for (const b of fam.standalone_benchmarks ?? []) decorateBenchmark(b, fam.derivedTags)
  for (const b of fam.benchmarks ?? []) decorateBenchmark(b, fam.derivedTags)
  for (const c of fam.composites ?? []) decorateComposite(c, fam.derivedTags)
  // Bottom-up union: parents accumulate their descendants' tags so a
  // family-level filter ("mathematics") matches families whose own name
  // doesn't, but whose children do.
  fam.derivedTags = unionTags(
    fam.derivedTags,
    ...(fam.standalone_benchmarks ?? []).map((b) => b.derivedTags ?? []),
    ...(fam.benchmarks ?? []).map((b) => b.derivedTags ?? []),
    ...(fam.composites ?? []).map((c) => c.derivedTags ?? []),
  )
}

function decorateComposite(comp: HierarchyComposite, parentTags: string[]): void {
  comp.derivedTags = getBenchmarkTags(parentTags, comp.display_name, comp.key)
  for (const b of comp.benchmarks ?? []) decorateBenchmark(b, comp.derivedTags)
  comp.derivedTags = unionTags(
    comp.derivedTags,
    ...(comp.benchmarks ?? []).map((b) => b.derivedTags ?? []),
  )
}

function decorateBenchmark(b: HierarchyBenchmark, parentTags: string[]): void {
  b.derivedTags = getBenchmarkTags(parentTags, b.display_name, b.key)
  for (const s of b.slices ?? []) decorateSlice(s, b.derivedTags)
  b.derivedTags = unionTags(b.derivedTags, ...(b.slices ?? []).map((s) => s.derivedTags ?? []))
}

function decorateSlice(s: HierarchySlice, parentTags: string[]): void {
  s.derivedTags = getBenchmarkTags(parentTags, s.display_name, s.key)
}

function unionTags(...lists: Array<string[] | null | undefined>): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const list of lists) {
    for (const tag of list ?? []) {
      if (!tag || seen.has(tag)) continue
      seen.add(tag)
      out.push(tag)
    }
  }
  return out
}

/**
 * Render a tag for display: snake_case → Sentence case, with a small
 * map of overrides for terms whose default casing would mislead readers.
 * "software_engineering" → "Software engineering";
 * "humanities_and_social_sciences" → "Humanities and social sciences";
 * "multimodal" → "Multimodal (text+image/audio/video)" — "multimodal" alone
 * is too ambiguous (modal what?), so we expand on first appearance.
 */
const TAG_LABEL_OVERRIDES: Record<string, string> = {
  multimodal: "Multimodal input",
}

export function formatTagLabel(tag: string): string {
  if (!tag) return tag
  const override = TAG_LABEL_OVERRIDES[tag.toLowerCase()]
  if (override) return override
  return tag
    .split("_")
    .filter(Boolean)
    .map((segment, index) =>
      index === 0
        ? segment[0].toUpperCase() + segment.slice(1)
        : segment.toLowerCase(),
    )
    .join(" ")
}
