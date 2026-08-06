"use client"

import type { ReactNode } from "react"
import { useEffect, useMemo, useState } from "react"
import { BarChart3, ClipboardCheck, GitCompareArrows, ShieldCheck } from "lucide-react"

import { useAudienceMode } from "@/components/audience-mode-provider"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type {
  ComparabilityCorpusBlock,
  CompletenessCorpusBlock,
  CorpusAggregates,
  ProvenanceCorpusBlock,
  ReproducibilityCorpusBlock,
} from "@/lib/backend-artifacts"
import { getTagColor } from "@/lib/benchmark-schema"
import {
  formatFieldLabel,
  formatPercent,
} from "./signal-utils"

const CATEGORY_ORDER = ["Agentic", "General", "Knowledge", "Reasoning", "Safety", "Other"]

const SOURCE_COLORS: Record<string, string> = {
  first_party: "bg-amber-500",
  third_party: "bg-emerald-500",
  collaborative: "bg-sky-500",
  unspecified: "bg-stone-400",
}

export function CorpusDashboard({
  aggregates,
  completenessScores,
  embedded = false,
}: {
  aggregates: CorpusAggregates
  completenessScores: number[]
  /**
   * When true, hides the dashboard's own masthead card. The host page is
   * expected to provide its own title and generated-date badge. The view
   * toggle is preserved inline above the signal sections.
   */
  embedded?: boolean
}) {
  const { mode } = useAudienceMode()
  const [view, setView] = useState<"overall" | "category">("overall")

  useEffect(() => {
    setView(mode === "research" ? "category" : "overall")
  }, [mode])

  const categoryKeys = useMemo(
    () => {
      const available = new Set([
        ...Object.keys(aggregates.reproducibility.by_category),
        ...Object.keys(aggregates.completeness.by_category),
        ...Object.keys(aggregates.provenance.by_category),
        ...Object.keys(aggregates.comparability.by_category),
      ])

      return [
        ...CATEGORY_ORDER.filter((category) => available.has(category)),
        ...Array.from(available)
          .filter((category) => !CATEGORY_ORDER.includes(category))
          .sort((a, b) => a.localeCompare(b)),
      ]
    },
    [aggregates]
  )

  return (
    <div className="space-y-6">
      {embedded ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
            Interpretive signals
          </div>
          <div className="inline-flex rounded-full border bg-muted/20 p-1">
            <Button
              type="button"
              size="sm"
              variant={view === "overall" ? "default" : "ghost"}
              className="h-8 rounded-full"
              onClick={() => setView("overall")}
            >
              Overall
            </Button>
            <Button
              type="button"
              size="sm"
              variant={view === "category" ? "default" : "ghost"}
              className="h-8 rounded-full"
              onClick={() => setView("category")}
            >
              By category
            </Button>
          </div>
        </div>
      ) : (
        <section className="rounded-2xl border border-border/70 bg-card p-5 shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                Interpretive signals
              </div>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight">Corpus Dashboard</h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
                Corpus-level rollups for reproducibility, reporting completeness, provenance, and comparability.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">Generated {formatGeneratedDate(aggregates.generated_at)}</Badge>
              <div className="inline-flex rounded-full border bg-muted/20 p-1">
                <Button
                  type="button"
                  size="sm"
                  variant={view === "overall" ? "default" : "ghost"}
                  className="h-8 rounded-full"
                  onClick={() => setView("overall")}
                >
                  Overall
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={view === "category" ? "default" : "ghost"}
                  className="h-8 rounded-full"
                  onClick={() => setView("category")}
                >
                  By category
                </Button>
              </div>
            </div>
          </div>
        </section>
      )}

      {view === "overall" ? (
        <div className="grid gap-6">
          <ReproducibilitySection block={aggregates.reproducibility.overall} />
          <CompletenessSection block={aggregates.completeness.overall} scores={completenessScores} />
          <ProvenanceSection block={aggregates.provenance.overall} />
          <ComparabilitySection block={aggregates.comparability.overall} />
        </div>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {categoryKeys.map((category) => (
            <CategoryPanel
              key={category}
              category={category}
              reproducibility={aggregates.reproducibility.by_category[category]}
              completeness={aggregates.completeness.by_category[category]}
              provenance={aggregates.provenance.by_category[category]}
              comparability={aggregates.comparability.by_category[category]}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function ReproducibilitySection({ block }: { block: ReproducibilityCorpusBlock }) {
  return (
    <DashboardSection
      icon={<ShieldCheck className="h-5 w-5" />}
      title="Reproducibility"
      subtitle="Reported scores with enough setup documentation to re-run."
      headline={formatPercent(block.reproducibility_gap_rate)}
      headlineLabel={`${block.triples_with_reproducibility_gap.toLocaleString()} of ${block.total_triples.toLocaleString()} reported scores have gaps`}
    >
      <div className="grid gap-2">
        {Object.entries(block.per_field_missingness).slice(0, 10).map(([field, value]) => (
          <MetricBar
            key={field}
            label={formatFieldLabel(field)}
            value={value.missing_rate}
            detail={`${value.missing_count.toLocaleString()} missing / ${value.denominator === "agentic_only" ? "agentic only" : "all scores"}`}
          />
        ))}
      </div>
    </DashboardSection>
  )
}

function CompletenessSection({
  block,
  scores,
}: {
  block: CompletenessCorpusBlock
  scores: number[]
}) {
  return (
    <DashboardSection
      icon={<ClipboardCheck className="h-5 w-5" />}
      title="Reporting Completeness"
      subtitle="How much benchmark documentation is populated."
      headline={formatPercent(block.completeness_avg)}
      headlineLabel={`Range ${formatPercent(block.completeness_min)} to ${formatPercent(block.completeness_max)} across ${block.total_triples.toLocaleString()} reported score triples`}
    >
      {scores.length > 0 && <Histogram scores={scores} />}
      <div className="mt-4 grid gap-2 sm:grid-cols-3">
        <MiniMetric label="Minimum" value={formatPercent(block.completeness_min)} />
        <MiniMetric label="Average" value={formatPercent(block.completeness_avg)} />
        <MiniMetric label="Maximum" value={formatPercent(block.completeness_max)} />
      </div>
    </DashboardSection>
  )
}

function ProvenanceSection({ block }: { block: ProvenanceCorpusBlock }) {
  const distribution = block.source_type_distribution
  const total = Object.values(distribution).reduce((sum, value) => sum + value, 0)
  const multiSourceRate = rate(block.multi_source_triples, block.total_triples)
  const firstPartyOnlyRate = rate(block.first_party_only_triples, block.total_triples)

  return (
    <DashboardSection
      icon={<BarChart3 className="h-5 w-5" />}
      title="Provenance"
      subtitle="Who reported the scores, and whether groups have multiple sources."
      headline={formatPercent(multiSourceRate)}
      headlineLabel="of reported score triples have multiple reporting sources"
    >
      <div className="overflow-hidden rounded-full border border-border/70 bg-muted/30">
        <div className="flex h-4 w-full">
          {Object.entries(distribution).map(([sourceType, count]) => (
            <div
              key={sourceType}
              className={SOURCE_COLORS[sourceType] ?? "bg-muted-foreground"}
              style={{ width: total > 0 ? `${(count / total) * 100}%` : "0%" }}
              title={`${sourceType.replace(/_/g, " ")}: ${count}`}
            />
          ))}
        </div>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <RatioTile label="Multi-source triples" value={multiSourceRate} count={block.multi_source_triples} />
        <RatioTile label="First-party only triples" value={firstPartyOnlyRate} count={block.first_party_only_triples} />
      </div>
    </DashboardSection>
  )
}

function ComparabilitySection({ block }: { block: ComparabilityCorpusBlock }) {
  const variantRate = rate(block.variant_divergent_count, block.groups_with_variant_check)
  const crossPartyRate = rate(
    block.cross_party_divergent_count,
    block.groups_with_cross_party_check
  )

  return (
    <DashboardSection
      icon={<GitCompareArrows className="h-5 w-5" />}
      title="Comparability"
      subtitle="Eligible groups where scores diverge across setups or reporting organizations."
      headline={formatNullableRate(variantRate)}
      headlineLabel={`${block.variant_divergent_count.toLocaleString()} of ${block.groups_with_variant_check.toLocaleString()} setup-eligible groups diverge`}
    >
      <div className="grid gap-3 md:grid-cols-2">
        <ComparabilityRateCard
          title="Variant divergence"
          rate={variantRate}
          eligible={block.groups_with_variant_check}
          divergent={block.variant_divergent_count}
        />
        <ComparabilityRateCard
          title="Cross-party divergence"
          rate={crossPartyRate}
          eligible={block.groups_with_cross_party_check}
          divergent={block.cross_party_divergent_count}
        />
      </div>
    </DashboardSection>
  )
}

function CategoryPanel({
  category,
  reproducibility,
  completeness,
  provenance,
  comparability,
}: {
  category: string
  reproducibility?: ReproducibilityCorpusBlock
  completeness?: CompletenessCorpusBlock
  provenance?: ProvenanceCorpusBlock
  comparability?: ComparabilityCorpusBlock
}) {
  const categoryLabel = `${category.charAt(0).toUpperCase()}${category.slice(1)}`
  const multiSourceRate = rate(provenance?.multi_source_triples, provenance?.total_triples)
  const variantRate = rate(
    comparability?.variant_divergent_count,
    comparability?.groups_with_variant_check
  )
  const crossPartyRate = rate(
    comparability?.cross_party_divergent_count,
    comparability?.groups_with_cross_party_check
  )

  return (
    <section className="rounded-2xl border border-border/70 bg-card p-4 shadow-sm">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="font-semibold">{categoryLabel}</h2>
        <Badge className={getTagColor(categoryLabel)}>{categoryLabel}</Badge>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <MiniMetric label="Reproducibility gaps" value={formatPercent(reproducibility?.reproducibility_gap_rate)} />
        <MiniMetric label="Documentation mean" value={formatPercent(completeness?.completeness_avg)} />
        <MiniMetric label="Multi-source triples" value={formatPercent(multiSourceRate)} />
        <MiniMetric label="Variant divergence" value={formatNullableRate(variantRate)} />
      </div>
      {crossPartyRate == null && (
        <div className="mt-3 rounded-xl border border-dashed border-border/70 bg-muted/10 px-3 py-2 text-sm text-muted-foreground">
          Cross-party divergence: N/A - not enough multi-org coverage.
        </div>
      )}
    </section>
  )
}

function DashboardSection({
  icon,
  title,
  subtitle,
  headline,
  headlineLabel,
  children,
}: {
  icon: ReactNode
  title: string
  subtitle: string
  headline: string
  headlineLabel: string
  children: ReactNode
}) {
  return (
    <section className="rounded-2xl border border-border/70 bg-card p-5 shadow-sm">
      <div className="grid gap-5 lg:grid-cols-[minmax(0,18rem)_1fr]">
        <div>
          <div className="flex items-center gap-2 text-primary">
            {icon}
            <h2 className="font-semibold">{title}</h2>
          </div>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{subtitle}</p>
          <div className="mt-5 rounded-xl border border-border/70 bg-muted/10 px-3 py-3">
            <div className="text-3xl font-semibold tabular-nums">{headline}</div>
            <div className="mt-1 text-xs leading-5 text-muted-foreground">{headlineLabel}</div>
          </div>
        </div>
        <div>{children}</div>
      </div>
    </section>
  )
}

function MetricBar({
  label,
  value,
  detail,
  compact = false,
}: {
  label: string
  value: number | null
  detail?: string
  compact?: boolean
}) {
  const percent = value == null ? 0 : Math.max(0, Math.min(100, value * 100))

  return (
    <div className={compact ? "space-y-1" : "rounded-xl border border-border/60 bg-background px-3 py-2"}>
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="min-w-0 truncate font-medium">{label}</span>
        <span className="shrink-0 tabular-nums text-muted-foreground">{formatPercent(value)}</span>
      </div>
      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-primary/75" style={{ width: `${percent}%` }} />
      </div>
      {detail && <div className="mt-1 text-xs text-muted-foreground">{detail}</div>}
    </div>
  )
}

function Histogram({ scores }: { scores: number[] }) {
  const buckets = Array.from({ length: 10 }, (_, index) => ({
    label: `${index * 10}-${(index + 1) * 10}%`,
    count: 0,
  }))

  for (const score of scores) {
    if (!Number.isFinite(score)) continue
    const bucket = Math.min(9, Math.max(0, Math.floor(score * 10)))
    buckets[bucket].count += 1
  }

  const maxCount = Math.max(...buckets.map((bucket) => bucket.count), 1)

  return (
    <div className="rounded-xl border border-border/60 bg-background px-3 py-3">
      <div className="mb-3 text-sm font-semibold">Benchmark completeness distribution</div>
      <div className="flex h-28 items-end gap-1.5">
        {buckets.map((bucket) => (
          <div key={bucket.label} className="flex min-w-0 flex-1 flex-col items-center gap-1">
            <div
              className="w-full rounded-t bg-primary/70"
              style={{ height: `${Math.max(4, (bucket.count / maxCount) * 100)}%` }}
              title={`${bucket.label}: ${bucket.count}`}
            />
            <span className="text-[9px] text-muted-foreground">{bucket.label.split("-")[0]}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function RatioTile({ label, value, count }: { label: string; value: number | null; count: number }) {
  return (
    <div className="rounded-xl border border-border/60 bg-background px-3 py-2">
      <div className="text-sm font-medium">{label}</div>
      <div className="mt-1 flex items-baseline justify-between gap-2">
        <span className="text-xl font-semibold tabular-nums">{formatPercent(value)}</span>
        <span className="text-xs text-muted-foreground">{count.toLocaleString()} triples</span>
      </div>
    </div>
  )
}

function ComparabilityRateCard({
  title,
  rate,
  eligible,
  divergent,
}: {
  title: string
  rate: number | null
  eligible: number
  divergent: number
}) {
  if (rate == null) {
    return (
      <div className="rounded-xl border border-dashed border-border/70 bg-muted/10 px-4 py-5">
        <div className="font-semibold">{title}</div>
        <div className="mt-2 text-sm text-muted-foreground">
          N/A - not enough data to compute this rate.
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-border/70 bg-background px-4 py-4">
      <div className="font-semibold">{title}</div>
      <div className="mt-3 text-2xl font-semibold tabular-nums">{formatPercent(rate)}</div>
      <div className="mt-1 text-sm text-muted-foreground">
        {divergent.toLocaleString()} of {eligible.toLocaleString()} eligible groups
      </div>
    </div>
  )
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border/60 bg-muted/10 px-3 py-2">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-xl font-semibold tabular-nums">{value}</div>
    </div>
  )
}

function formatNullableRate(value: number | null | undefined) {
  return value == null ? "N/A" : formatPercent(value)
}

function rate(numerator: number | null | undefined, denominator: number | null | undefined) {
  if (numerator == null || denominator == null || denominator <= 0) return null
  return numerator / denominator
}

function formatGeneratedDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}
