"use client"

import type { ComponentType, CSSProperties } from "react"
import { useRouter } from "next/navigation"
import { BarChart3, Boxes, ChevronRight, Sparkles } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import type { DeveloperListItem } from "@/lib/dashboard-data-client"
import { routeIdToPath } from "@/lib/utils"

interface DeveloperCardProps {
  developer: DeveloperListItem
  delayMs?: number
}

export function DeveloperCard({ developer, delayMs = 0 }: DeveloperCardProps) {
  const router = useRouter()

  return (
    <Card
      className="motion-academic-enter motion-academic-surface motion-academic-hover group cursor-pointer overflow-hidden border-border/70 bg-card hover:shadow-lg"
      style={{ "--enter-delay": `${delayMs}ms` } as CSSProperties}
      onClick={() => router.push(`/developers/${routeIdToPath(developer.route_id)}`)}
    >
      <CardHeader className="space-y-3 border-b border-border/60 pb-4">
        <div className="text-[10px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">
          Developer Summary
        </div>

        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="truncate text-xl font-bold">{developer.developer}</div>
            <div className="mt-1 text-sm text-muted-foreground">
              Aggregated reporting across published model variants and their most common single benchmarks
            </div>
          </div>
          <ChevronRight className="mt-1 h-5 w-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
        </div>
      </CardHeader>

      <CardContent className="space-y-4 pt-4">
        <div className="grid gap-2 sm:grid-cols-3">
          <MetricPill
            icon={Boxes}
            label="Models"
            value={developer.model_count.toLocaleString()}
            tone="bg-sky-100/80 text-sky-900 dark:bg-sky-950/40 dark:text-sky-100"
          />
          <MetricPill
            icon={BarChart3}
            label="Benchmarks"
            value={developer.benchmark_count.toLocaleString()}
            tone="bg-amber-100/80 text-amber-900 dark:bg-amber-950/40 dark:text-amber-100"
          />
          <MetricPill
            icon={Sparkles}
            label="Results"
            value={developer.evaluation_count.toLocaleString()}
            tone="bg-emerald-100/80 text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-100"
          />
        </div>

        <div className="rounded-xl border bg-muted/10 p-3">
          <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Scores From
          </div>
          <div className="flex flex-wrap gap-2">
            {developer.popular_evals.length > 0 ? (
              developer.popular_evals.map((evaluation) => (
                <Badge key={evaluation.benchmark} variant="secondary">
                  {evaluation.benchmark}
                  <span className="ml-1 text-muted-foreground">· {evaluation.model_count}</span>
                </Badge>
              ))
            ) : (
              <span className="text-sm text-muted-foreground">No benchmark coverage indexed yet</span>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between rounded-xl border border-border/70 bg-muted/10 px-3 py-3">
          <div className="text-sm text-muted-foreground">
            Open the developer card for model-by-model coverage and benchmark detail.
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="gap-1"
            onClick={(event) => {
              event.stopPropagation()
              router.push(`/developers/${routeIdToPath(developer.route_id)}`)
            }}
          >
            Open card
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function MetricPill({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: ComponentType<{ className?: string }>
  label: string
  value: string
  tone: string
}) {
  return (
    <div className={`flex items-center justify-between rounded-xl px-3 py-2 ${tone}`}>
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4" />
        <span className="text-[11px] font-semibold uppercase tracking-[0.18em] opacity-80">
          {label}
        </span>
      </div>
      <span className="text-sm font-bold">{value}</span>
    </div>
  )
}
