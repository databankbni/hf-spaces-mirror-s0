"use client"

import type { ReactNode } from "react"
import { ChevronDown, ClipboardCheck } from "lucide-react"

import { useAudienceMode } from "@/components/audience-mode-provider"
import { Badge } from "@/components/ui/badge"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Progress } from "@/components/ui/progress"
import type { ReportingCompleteness } from "@/lib/backend-artifacts"
import {
  formatFieldLabel,
  formatPercent,
  getCompletenessPopulatedCount,
} from "./signal-utils"

export function CompletenessPanel({
  completeness,
}: {
  completeness?: ReportingCompleteness | null
}) {
  const { mode } = useAudienceMode()
  const isResearchView = mode === "research"

  if (!completeness) {
    return null
  }

  const populatedCount = getCompletenessPopulatedCount(completeness)
  const total = completeness.total_fields_evaluated
  const missingFields = completeness.missing_required_fields ?? []
  const partialFields = completeness.partial_fields ?? []

  return (
    <section className="rounded-2xl border border-border/70 bg-background/70 p-4 sm:p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <ClipboardCheck className="h-4 w-4 text-primary" />
            <h3 className="font-semibold">
              {isResearchView ? "Reporting completeness" : "How well is this benchmark documented?"}
            </h3>
          </div>
          <p className="max-w-2xl text-sm text-muted-foreground">
            {isResearchView
              ? "Coverage of Evaluation Cards-required documentation fields for this benchmark."
              : "A quick read on how much supporting documentation is available before leaning on the scores."}
          </p>
        </div>

        <div className="min-w-[14rem] rounded-xl border border-border/70 bg-muted/10 px-3 py-2">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              Documentation
            </span>
            <span className="text-lg font-semibold tabular-nums">
              {formatPercent(completeness.completeness_score)}
            </span>
          </div>
          <Progress value={completeness.completeness_score * 100} className="mt-2 h-2" />
          <div className="mt-2 text-xs text-muted-foreground">
            {populatedCount} of {total} fields populated
          </div>
        </div>
      </div>

      {(missingFields.length > 0 || partialFields.length > 0) && (
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <SignalListCollapsible
            title="Missing required fields"
            count={missingFields.length}
          >
            {missingFields.length === 0 ? (
              <p className="text-sm text-muted-foreground">No missing required fields recorded.</p>
            ) : (
              <ul className="space-y-1.5 text-sm">
                {missingFields.slice(0, 12).map((field) => (
                  <li key={field} className="rounded-lg border border-border/50 bg-background px-3 py-2">
                    <span className="font-medium">{formatFieldLabel(field)}</span>
                    {isResearchView && (
                      <span className="ml-2 text-xs text-muted-foreground">{field}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </SignalListCollapsible>

          <SignalListCollapsible
            title="Partially populated"
            count={partialFields.length}
          >
            {partialFields.length === 0 ? (
              <p className="text-sm text-muted-foreground">No partially populated fields recorded.</p>
            ) : (
              <ul className="space-y-1.5 text-sm">
                {partialFields.slice(0, 12).map((field) => (
                  <li key={field.field_path} className="rounded-lg border border-border/50 bg-background px-3 py-2">
                    <div className="flex items-start justify-between gap-3">
                      <span className="font-medium">{formatFieldLabel(field.field_path)}</span>
                      <span className="shrink-0 text-muted-foreground">
                        {field.populated_subitems}/{field.total_subitems}
                      </span>
                    </div>
                    {isResearchView && (
                      <div className="mt-1 text-xs text-muted-foreground">{field.field_path}</div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </SignalListCollapsible>
        </div>
      )}
    </section>
  )
}

function SignalListCollapsible({
  title,
  count,
  children,
}: {
  title: string
  count: number
  children: ReactNode
}) {
  return (
    <Collapsible>
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="flex w-full items-center justify-between rounded-xl border border-border/70 bg-muted/10 px-3 py-2 text-left transition-colors hover:bg-muted/20"
        >
          <span className="flex items-center gap-2 text-sm font-semibold">
            {title}
            <Badge variant="secondary">{count}</Badge>
          </span>
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-2">
        {children}
      </CollapsibleContent>
    </Collapsible>
  )
}
