import type {
  EvalHierarchy,
  HierarchyComposite,
  HierarchyFamily,
} from "@/lib/backend-artifacts"

export interface HierarchyEvalLocation {
  familyKey: string
  familyDisplayName: string
  compositeKey?: string
  compositeDisplayName?: string
  /** Resolved leaf benchmark — set when `eval_summary_id` lives inside a
   *  hierarchy benchmark's `constituent_evaluation_ids`. Lets the model-detail
   *  plotbox builder bucket every eval row that resolves to the same
   *  benchmark together (so a standalone like Fibble Arena with N
   *  per-split eval rows renders as one plotbox, not N). */
  benchmarkKey?: string
  benchmarkDisplayName?: string
  /** Curated category tags (data/benchmarks/categories.json vocabulary)
   *  for the leaf benchmark this eval belongs to, falling back to its
   *  composite/family. Decorated by `decorateHierarchyDerivedTags` at
   *  hydration time. */
  tags?: string[]
}

interface FamilyAppearance {
  family: HierarchyFamily
  composite?: HierarchyComposite
  benchmarkTags?: string[]
  benchmarkKey?: string
  benchmarkDisplayName?: string
}

function findComposite(
  family: HierarchyFamily,
  evalSummaryId: string,
): HierarchyComposite | undefined {
  const composites = family.composites
  if (!composites?.length) {
    return undefined
  }
  const sourcePrefix = evalSummaryId.split("%2F")[0]
  const byPrefix = composites.find((composite) => composite.key === sourcePrefix)
  if (byPrefix) return byPrefix
  // Fallback: scan benchmarks' `constituent_evaluation_ids`. The clean-hierarchy
  // post-processor synthesises composites for split families (Fibble
  // Arena's per-N-lies splits, CapArena-Auto, AgentHarm) whose
  // children carry mixed source prefixes (`fibble1-arena%2F…`,
  // `fibble2-arena%2F…`, …) that wouldn't match the synthetic
  // composite's key by prefix alone.
  return composites.find((composite) =>
    composite.benchmarks?.some((bench) =>
      bench.constituent_evaluation_ids?.includes(evalSummaryId),
    ),
  )
}

function findBenchmark(
  family: HierarchyFamily,
  composite: HierarchyComposite | undefined,
  evalSummaryId: string,
):
  | { key: string; displayName: string; tags?: string[] }
  | undefined {
  const benchmarks = [
    ...(composite?.benchmarks ?? []),
    ...(family.standalone_benchmarks ?? []),
    ...(family.benchmarks ?? []),
  ]
  for (const benchmark of benchmarks) {
    if (benchmark.constituent_evaluation_ids?.includes(evalSummaryId)) {
      return {
        key: benchmark.key,
        displayName: benchmark.display_name,
        tags: benchmark.derivedTags,
      }
    }
  }
  return undefined
}

function buildAppearancesIndex(
  hierarchy: EvalHierarchy | null | undefined,
): Map<string, FamilyAppearance[]> {
  const index = new Map<string, FamilyAppearance[]>()
  if (!hierarchy?.families) {
    return index
  }

  for (const family of hierarchy.families) {
    for (const evalSummaryId of family.constituent_evaluation_ids ?? []) {
      const composite = findComposite(family, evalSummaryId)
      const bench = findBenchmark(family, composite, evalSummaryId)
      const list = index.get(evalSummaryId) ?? []
      list.push({
        family,
        composite,
        benchmarkTags: bench?.tags,
        benchmarkKey: bench?.key,
        benchmarkDisplayName: bench?.displayName,
      })
      index.set(evalSummaryId, list)
    }
  }

  return index
}

/**
 * Build a lookup that maps each `eval_summary_id` to the family / composite
 * that contains it in `hierarchy.json`. The model-detail benchmark grouping
 * needs this because the eval row's own `family_id` is null for some evals
 * (e.g. CySE2 composites) and points at the leaf instead of the parent for
 * singleton families. The hierarchy is the only source that captures
 * curated family→composite→benchmark grouping.
 *
 * Some constituent_evaluation_ids appear in multiple families. The optional
 * `preferFamilyKey(evalSummaryId)` callback lets the caller pick the canonical
 * family — typically by passing in the eval row's own `family_id`. When no
 * preference is given, the first family encountered wins.
 */
export function buildHierarchyEvalIndex(
  hierarchy: EvalHierarchy | null | undefined,
  preferFamilyKey?: (evalSummaryId: string) => string | null | undefined,
): Map<string, HierarchyEvalLocation> {
  const appearances = buildAppearancesIndex(hierarchy)
  const index = new Map<string, HierarchyEvalLocation>()

  for (const [evalSummaryId, candidates] of appearances) {
    let chosen = candidates[0]
    if (candidates.length > 1) {
      const preferredKey = preferFamilyKey?.(evalSummaryId)?.toString().trim()
      if (preferredKey) {
        const match = candidates.find((c) => c.family.key === preferredKey)
        if (match) {
          chosen = match
        }
      }
    }

    // Tag preference order for the leaf: benchmark > composite > family.
    // We want the most specific tags available so the model-view bucketing
    // groups by leaf semantics, not by the family-level union.
    const tags =
      chosen.benchmarkTags && chosen.benchmarkTags.length > 0
        ? chosen.benchmarkTags
        : chosen.composite?.derivedTags ?? chosen.family.derivedTags ?? []

    index.set(evalSummaryId, {
      familyKey: chosen.family.key,
      familyDisplayName: chosen.family.display_name,
      compositeKey: chosen.composite?.key,
      compositeDisplayName: chosen.composite?.display_name,
      benchmarkKey: chosen.benchmarkKey,
      benchmarkDisplayName: chosen.benchmarkDisplayName,
      tags,
    })
  }

  return index
}
