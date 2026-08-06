"use client"

import { Suspense, useCallback, useDeferredValue, useEffect, useMemo, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Search } from "lucide-react"

import { EvaluatorTable, type EvaluatorTableSortCol } from "@/components/evaluator-table"
import { useOrgMetadata } from "@/components/org-metadata-provider"
import { FamilyTable, getFamilyNavId, type FamilySortCol } from "@/components/family-table"
import { InfiniteScrollSentinel } from "@/components/infinite-scroll"
import { Navigation } from "@/components/navigation"
import { PageLoadingState, type PageLoadingStage } from "@/components/page-loading-state"
import type { EvalHierarchy, HierarchyFamily } from "@/lib/backend-artifacts"
import { fetchBenchmarkMetadata, fetchEvalHierarchy, fetchEvalList } from "@/lib/dashboard-data-client"
import type { BenchmarkEvalListItem } from "@/lib/eval-processing"
import type { BenchmarkCard } from "@/lib/benchmark-schema"
import { formatTagLabel } from "@/lib/benchmark-tags"
import { groupEvalsByEvaluator, verifiedEvalIds } from "@/lib/evaluators"

const PAGE_SIZE = 60

function getFamilyBenchmarkCount(fam: HierarchyFamily): number {
  return (
    (fam.standalone_benchmarks?.length ?? 0) +
    (fam.benchmarks?.length ?? 0) +
    (fam.composites ?? []).reduce((sum, c) => sum + (c.benchmarks?.length ?? 0), 0)
  )
}

function getFamilyEvalsCount(fam: HierarchyFamily): number {
  if (fam.evals_count != null) return fam.evals_count
  const all = [
    ...(fam.standalone_benchmarks ?? []),
    ...(fam.benchmarks ?? []),
    ...(fam.composites ?? []).flatMap((c) => c.benchmarks ?? []),
  ]
  return all.reduce((sum, b) => sum + (b.metrics?.length ?? 0), 0)
}

function EvalsPageInner() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const familyParam = searchParams.get("family")
  const queryParam = searchParams.get("q")
  const groupByParam = searchParams.get("groupBy")
  const verifiedParam = searchParams.get("verified")

  const [hierarchy, setHierarchy] = useState<EvalHierarchy | null>(null)
  const [totalModels, setTotalModels] = useState<number>(0)
  const [evalItems, setEvalItems] = useState<Map<string, BenchmarkEvalListItem>>(new Map())
  const [benchmarkCards, setBenchmarkCards] = useState<Record<string, BenchmarkCard>>({})
  const [hierarchyStageDone, setHierarchyStageDone] = useState(false)
  const [evalListStageDone, setEvalListStageDone] = useState(false)
  const [metadataStageDone, setMetadataStageDone] = useState(false)
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState("")
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  const [selectedCategories, setSelectedCategories] = useState<string[]>([])
  const [agentMode, setAgentMode] = useState<"all" | "agentic" | "non-agentic">("all")
  const [sortCol, setSortCol] = useState<FamilySortCol>("name")
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc")
  const [groupBy, setGroupBy] = useState<"family" | "evaluator">(
    groupByParam === "evaluator" ? "evaluator" : "family",
  )
  const [verifiedOnly, setVerifiedOnly] = useState<boolean>(
    verifiedParam === "1" || verifiedParam === "true",
  )
  const [evaluatorSortCol, setEvaluatorSortCol] = useState<EvaluatorTableSortCol>("evals")
  const [evaluatorSortDir, setEvaluatorSortDir] = useState<"asc" | "desc">("desc")
  // In verified-only mode the Verified column is hidden (it equals
  // Evaluations reported), so a stale "verified" sort would otherwise sit
  // active on a column the user can no longer see or toggle. Clamp it to
  // "evals" — same ordering, but on a visible, interactive header.
  const effectiveEvaluatorSortCol: EvaluatorTableSortCol =
    verifiedOnly && evaluatorSortCol === "verified" ? "evals" : evaluatorSortCol
  const deferredSearchQuery = useDeferredValue(searchQuery)

  const handleEvaluatorSort = useCallback((col: EvaluatorTableSortCol) => {
    setEvaluatorSortCol((current) => {
      if (current === col) {
        setEvaluatorSortDir((dir) => (dir === "asc" ? "desc" : "asc"))
        return current
      }
      setEvaluatorSortDir(col === "name" ? "asc" : "desc")
      return col
    })
  }, [])

  const handleSort = useCallback((col: FamilySortCol) => {
    if (sortCol === col) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    } else {
      setSortCol(col)
      setSortDir("asc")
    }
  }, [sortCol])

  useEffect(() => {
    const hierarchyRequest = fetchEvalHierarchy()
      .then((h) => {
        setHierarchy(h)
        setHierarchyStageDone(true)
      })
      .catch(console.error)

    const evalListRequest = fetchEvalList()
      .then((list) => {
        setTotalModels(list.totalModels)
        const map = new Map<string, BenchmarkEvalListItem>()
        for (const item of list.evals) map.set(item.evaluation_id, item)
        setEvalItems(map)
        setEvalListStageDone(true)
      })
      .catch(console.error)

    const benchmarkMetadataRequest = fetchBenchmarkMetadata()
      .then((metadata) => {
        setBenchmarkCards(metadata)
        setMetadataStageDone(true)
      })
      .catch(console.error)

    Promise.allSettled([hierarchyRequest, evalListRequest, benchmarkMetadataRequest])
      .finally(() => setLoading(false))
  }, [])

  const loadingStages = useMemo<PageLoadingStage[]>(() => [
    { label: "Evaluation hierarchy", done: hierarchyStageDone },
    { label: `Evaluation index${totalModels > 0 ? ` (${totalModels.toLocaleString()} models)` : ""}`, done: evalListStageDone },
    { label: "Benchmark metadata", done: metadataStageDone },
  ], [evalListStageDone, hierarchyStageDone, metadataStageDone, totalModels])

  // Resolve the `?q=<term>` deep link from tag chips on benchmark pages.
  useEffect(() => {
    if (queryParam) setSearchQuery(queryParam)
  }, [queryParam])

  // Resolve the `?family=<key>` deep link from the home page family cards.
  // For families with a clean family-level summary we redirect to the
  // detail page; for aggregator families (no nav target) we seed the
  // search box so the listing narrows to that family and the user can
  // expand it. Runs once per `family` param value, after data loads.
  useEffect(() => {
    if (!familyParam || !hierarchy) return
    const fam = hierarchy.families.find((f) => f.key === familyParam)
    if (!fam) return
    const navId = getFamilyNavId(fam, benchmarkCards)
    if (navId) {
      router.replace(`/evals/${navId.replace(/%2F/g, "/")}`)
      return
    }
    setSearchQuery(fam.display_name || fam.key)
  }, [familyParam, hierarchy, benchmarkCards, router])

  // Reflect groupBy / verified into the URL (nice-to-have deep link).
  // Shallow replace so the back button isn't spammed and data isn't refetched.
  useEffect(() => {
    const params = new URLSearchParams(searchParams.toString())
    if (groupBy === "evaluator") params.set("groupBy", "evaluator")
    else params.delete("groupBy")
    if (verifiedOnly) params.set("verified", "1")
    else params.delete("verified")
    const qs = params.toString()
    router.replace(qs ? `/evals?${qs}` : "/evals", { scroll: false })
    // searchParams intentionally omitted — we only push when our own toggles change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupBy, verifiedOnly])

  const allEvals = useMemo(() => Array.from(evalItems.values()), [evalItems])

  // Verified-eval id universe — drives the Family-mode "Verified only" gate.
  const verifiedIds = useMemo(() => verifiedEvalIds(allEvals), [allEvals])

  // Evaluator groups (group-by-Evaluator mode). Verified filter is
  // evaluator-aware: counts only (eval, org) pairs where org is verified.
  const orgMeta = useOrgMetadata()
  const evaluatorGroups = useMemo(
    () => groupEvalsByEvaluator(allEvals, { verifiedOnly, orgMeta }),
    [allEvals, verifiedOnly, orgMeta],
  )

  const filteredEvaluators = useMemo(() => {
    const query = deferredSearchQuery.trim().toLowerCase()
    let list = evaluatorGroups
    if (query) list = list.filter((g) => g.name.toLowerCase().includes(query))
    const dirMul = evaluatorSortDir === "asc" ? 1 : -1
    return list.slice().sort((a, b) => {
      let cmp = 0
      if (effectiveEvaluatorSortCol === "name") cmp = a.name.localeCompare(b.name)
      else if (effectiveEvaluatorSortCol === "verified") cmp = a.verifiedCount - b.verifiedCount
      else cmp = a.evalCount - b.evalCount
      if (cmp === 0) cmp = a.name.localeCompare(b.name)
      return cmp * dirMul
    })
  }, [evaluatorGroups, deferredSearchQuery, effectiveEvaluatorSortCol, evaluatorSortDir])

  const families = hierarchy?.families ?? []

  // Tags per family — union of derivedTags across the family and every
  // nested benchmark/composite. derivedTags is attached at hydration
  // time by decorateHierarchyDerivedTags (lib/benchmark-tags.ts) so all
  // the lookup, inheritance, and fallback logic lives in one place.
  // Drives both the pill selector below and the filter predicate.
  const familyTags = useMemo(() => {
    const out = new Map<string, Set<string>>()
    for (const fam of families) {
      const tags = new Set<string>(fam.derivedTags ?? [])
      for (const b of fam.standalone_benchmarks ?? []) for (const t of b.derivedTags ?? []) tags.add(t)
      for (const b of fam.benchmarks ?? []) for (const t of b.derivedTags ?? []) tags.add(t)
      for (const c of fam.composites ?? []) {
        for (const t of c.derivedTags ?? []) tags.add(t)
        for (const b of c.benchmarks ?? []) for (const t of b.derivedTags ?? []) tags.add(t)
      }
      out.set(fam.key, tags)
    }
    return out
  }, [families])

  // Tag → family-count map, sorted by descending count so the most
  // common tags surface first in the pill bar. Excludes "agentic" — it
  // lives on its own dedicated toggle since it's an orthogonal axis
  // (interaction style) rather than a category.
  const availableTags = useMemo(() => {
    const counts = new Map<string, number>()
    for (const tags of familyTags.values()) {
      for (const tag of tags) {
        if (tag.toLowerCase() === "agentic") continue
        counts.set(tag, (counts.get(tag) ?? 0) + 1)
      }
    }
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .map(([tag]) => tag)
  }, [familyTags])

  const filteredFamilies = useMemo(() => {
    const query = deferredSearchQuery.trim().toLowerCase()
    let list = families

    if (query) {
      // The query has to also reach nested benchmark keys / display names /
      // evaluation ids — otherwise typing "mmlu-pro" misses
      // helm-capabilities/mmlu-pro and friends because they live as leaves
      // under the MMLU family, whose family-level metadata doesn't contain
      // the substring. Decoding %2F so percent-encoded ids also match
      // human-typed slashes.
      const matchesNestedBenchmark = (fam: HierarchyFamily): boolean => {
        const benches = [
          ...(fam.standalone_benchmarks ?? []),
          ...(fam.benchmarks ?? []),
          ...(fam.composites ?? []).flatMap((c) => c.benchmarks ?? []),
        ]
        for (const b of benches) {
          if (b.key && b.key.toLowerCase().includes(query)) return true
          if (b.display_name && b.display_name.toLowerCase().includes(query)) return true
          for (const id of b.constituent_evaluation_ids ?? []) {
            const decoded = decodeURIComponent(id).toLowerCase()
            if (decoded.includes(query) || id.toLowerCase().includes(query)) return true
          }
        }
        return false
      }
      list = list.filter((fam) => {
        if (fam.display_name.toLowerCase().includes(query)) return true
        if (fam.key.toLowerCase().includes(query)) return true
        if (fam.category?.toLowerCase().includes(query)) return true
        // Also match the curated tag set so the search box and the
        // category pill bar agree on what is filterable. Without this,
        // typing "finance" returned zero families even though the
        // Finance pill catches several.
        const tags = familyTags.get(fam.key)
        if (tags) {
          for (const tag of tags) {
            if (tag.toLowerCase().includes(query)) return true
            if (formatTagLabel(tag).toLowerCase().includes(query)) return true
          }
        }
        return matchesNestedBenchmark(fam)
      })
    }

    if (selectedCategories.length > 0) {
      const set = new Set(selectedCategories)
      list = list.filter((fam) => {
        const tags = familyTags.get(fam.key)
        if (!tags) return false
        for (const tag of tags) if (set.has(tag)) return true
        return false
      })
    }

    if (agentMode !== "all") {
      list = list.filter((fam) => {
        const tags = familyTags.get(fam.key)
        const hasAgentic = !!tags && Array.from(tags).some((t) => t.toLowerCase() === "agentic")
        return agentMode === "agentic" ? hasAgentic : !hasAgentic
      })
    }

    return list.slice().sort((a, b) => {
      let cmp = 0
      switch (sortCol) {
        case "name":
          cmp = a.display_name.localeCompare(b.display_name)
          break
        case "benchmarks":
          cmp = getFamilyBenchmarkCount(a) - getFamilyBenchmarkCount(b)
          break
        case "results":
          cmp = getFamilyEvalsCount(a) - getFamilyEvalsCount(b)
          break
      }
      return sortDir === "asc" ? cmp : -cmp
    })
  }, [families, deferredSearchQuery, selectedCategories, agentMode, familyTags, sortCol, sortDir])

  useEffect(() => {
    setVisibleCount(PAGE_SIZE)
  }, [deferredSearchQuery, selectedCategories, agentMode, sortCol, sortDir, groupBy, verifiedOnly, evaluatorSortCol, evaluatorSortDir])

  const visibleFamilies = useMemo(
    () => filteredFamilies.slice(0, visibleCount),
    [filteredFamilies, visibleCount],
  )
  const visibleEvaluators = useMemo(
    () => filteredEvaluators.slice(0, visibleCount),
    [filteredEvaluators, visibleCount],
  )
  const totalRows = groupBy === "evaluator" ? filteredEvaluators.length : filteredFamilies.length
  const hasMore = visibleCount < totalRows
  const handleLoadMore = useCallback(() => {
    setVisibleCount((current) => Math.min(current + PAGE_SIZE, totalRows))
  }, [totalRows])

  return (
    <div className="min-h-screen bg-background">
      <Navigation />

      <main className="mx-auto w-full max-w-[96rem] px-4 pt-12 pb-24 sm:px-8">
        {/* HEADER --------------------------------------------------- */}
        <div className="kicker">Index</div>
        <h1 className="ec-page-h1">Evaluations</h1>
        <p className="ec-page-lede">
          {groupBy === "evaluator" ? (
            <>
              Evaluations grouped by the <strong>organisation that reported them</strong>. A
              verified evaluator submitted the results from the org that ran the evaluation.
            </>
          ) : (
            <>
              Evaluations are grouped into <strong>families</strong>. A family may hold a single
              standalone benchmark or many related ones; each benchmark has one or more slices, and
              each slice reports one or more metrics.
            </>
          )}
        </p>

        {/* MODE + FILTER ROW --------------------------------------- */}
        <div className="mb-6 flex flex-wrap items-center gap-x-6 gap-y-3 border-y border-[color:var(--border-soft)] py-4">
          <div className="ec-mode-toggle" role="group" aria-label="Group evaluations by">
            <button
              type="button"
              className={groupBy === "family" ? "on" : ""}
              onClick={() => setGroupBy("family")}
            >
              Family
            </button>
            <button
              type="button"
              className={groupBy === "evaluator" ? "on" : ""}
              onClick={() => setGroupBy("evaluator")}
            >
              Evaluator
            </button>
          </div>

          <div className="ec-mode-toggle" role="group" aria-label="Verified only filter">
            <button
              type="button"
              className={!verifiedOnly ? "on" : ""}
              onClick={() => setVerifiedOnly(false)}
            >
              All
            </button>
            <button
              type="button"
              className={verifiedOnly ? "on" : ""}
              onClick={() => setVerifiedOnly(true)}
            >
              Verified only
            </button>
          </div>

          <div className="relative ml-auto min-w-[180px] flex-1 sm:max-w-[360px]">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[color:var(--fg-subtle)]" />
            <input
              className="ec-input pl-9"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder={
                groupBy === "evaluator"
                  ? "Search evaluator…"
                  : "Search family, benchmark, or category…"
              }
            />
          </div>
        </div>

        {/* Family-mode-only filters: interaction style + category pills.
            These operate on the family hierarchy and have no meaning in
            the evaluator grouping. */}
        {groupBy === "family" && (
        <>
        {/* INTERACTION STYLE TOGGLE — orthogonal axis from category,
            surfaced on its own so users don't mix "is this an agent
            benchmark?" with "what category is this in?" */}
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="kicker mr-2">Interaction style</span>
          <button
            type="button"
            onClick={() => setAgentMode("all")}
            className={`ec-pill ${agentMode === "all" ? "on" : ""}`}
          >
            All
          </button>
          <button
            type="button"
            onClick={() => setAgentMode("non-agentic")}
            className={`ec-pill ${agentMode === "non-agentic" ? "on" : ""}`}
            title="Single-turn or non-agent benchmarks"
          >
            Non-agent
          </button>
          <button
            type="button"
            onClick={() => setAgentMode("agentic")}
            className={`ec-pill ${agentMode === "agentic" ? "on" : ""}`}
            title="Agentic / multi-step / tool-use benchmarks"
          >
            Agent
          </button>
        </div>

        {/* CATEGORY PILLS — multi-select filter by curated benchmark
            tag (data/benchmarks/categories.json), with the legacy
            inferCategoryFromBenchmark buckets mixed in for benchmarks
            not present in the curated file. Agentic is excluded — it
            has its own dedicated toggle above. */}
        {availableTags.length > 0 && (
          <div className="mb-5 flex flex-wrap items-center gap-2">
            <span className="kicker mr-2">Category</span>
            <button
              type="button"
              onClick={() => setSelectedCategories([])}
              className={`ec-pill ${selectedCategories.length === 0 ? "on" : ""}`}
            >
              All
            </button>
            {availableTags.map((tag) => {
              const isSelected = selectedCategories.includes(tag)
              return (
                <button
                  key={tag}
                  type="button"
                  onClick={() =>
                    setSelectedCategories((current) =>
                      current.includes(tag)
                        ? current.filter((item) => item !== tag)
                        : [...current, tag],
                    )
                  }
                  className={`ec-pill ${isSelected ? "on" : ""}`}
                >
                  {formatTagLabel(tag)}
                </button>
              )
            })}
          </div>
        )}
        </>
        )}

        {/* TABLE ---------------------------------------------------- */}
        {loading ? (
          <PageLoadingState
            title="Loading evaluations"
            description="Refreshing the family hierarchy, evaluation index, and benchmark metadata."
            stages={loadingStages}
            className="py-14"
          />
        ) : totalRows === 0 ? (
          <div className="py-16 text-center border border-dashed border-[color:var(--border-soft)] bg-[color:var(--bg-warm)]">
            <p className="mb-4 text-base text-[color:var(--fg-muted)]">
              {groupBy === "evaluator"
                ? "No evaluators found matching your filters."
                : "No families found matching your filters."}
            </p>
            <button
              type="button"
              className="btn-ec outline"
              onClick={() => {
                setSearchQuery("")
                setSelectedCategories([])
                setVerifiedOnly(false)
              }}
            >
              Reset filters
            </button>
          </div>
        ) : groupBy === "evaluator" ? (
          <EvaluatorTable
            rows={visibleEvaluators}
            sortCol={effectiveEvaluatorSortCol}
            sortDir={evaluatorSortDir}
            onSort={handleEvaluatorSort}
            verifiedOnly={verifiedOnly}
          />
        ) : (
          <FamilyTable
            families={visibleFamilies}
            evalItems={evalItems}
            benchmarkCards={benchmarkCards}
            categoryFilter={new Set(selectedCategories)}
            searchQuery={deferredSearchQuery}
            verifiedEvalIds={verifiedOnly ? verifiedIds : null}
            sortCol={sortCol}
            sortDir={sortDir}
            onSort={handleSort}
          />
        )}

        <InfiniteScrollSentinel
          hasMore={hasMore}
          onLoadMore={handleLoadMore}
          loadingLabel="Loading more…"
          endLabel={`Showing ${Math.min(visibleCount, totalRows).toLocaleString()} of ${totalRows.toLocaleString()} ${groupBy === "evaluator" ? "evaluators" : "families"}`}
        />
      </main>
    </div>
  )
}

export default function EvalsPage() {
  return (
    <Suspense fallback={null}>
      <EvalsPageInner />
    </Suspense>
  )
}
