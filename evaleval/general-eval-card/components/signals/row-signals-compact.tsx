"use client"

import { AlertTriangle, ShieldCheck } from "lucide-react"
import { useAudienceMode } from "@/components/audience-mode-provider"
import type { RowAnnotations } from "@/lib/backend-artifacts"
import { cn } from "@/lib/utils"
import { SignalTooltip } from "./signal-tooltip"
import { formatMissingField } from "./signal-utils"
import { getRelationshipShortLabel } from "./provenance-badge"

/**
 * Compact, single-icon row signal indicator. Shows a warning icon when any
 * row-level concern fires (reproducibility gap, first-party-only reporting),
 * with a tooltip listing the specifics. Replaces the two full coloured badges
 * that were taking up vertical space under every model name.
 *
 * Returns null when there are no concerns, so green rows stay quiet.
 */
export function RowSignalsCompact({
  annotations,
  className,
  showWhenClean = false,
}: {
  annotations?: RowAnnotations | null
  className?: string
  showWhenClean?: boolean
}) {
  const { mode } = useAudienceMode()

  if (!annotations) return null

  const reproGap = annotations.reproducibility_gap
  const provenance = annotations.provenance
  const hasReproGap = reproGap?.has_reproducibility_gap === true
  const firstPartyOnly = provenance?.first_party_only === true

  const concerns: { title: string; detail: string }[] = []

  if (hasReproGap && reproGap) {
    const missing = reproGap.missing_fields.map(formatMissingField)
    concerns.push({
      title: mode === "policy" ? "Setup not documented" : "Reproducibility gap",
      detail:
        mode === "policy"
          ? `${reproGap.populated_field_count} of ${reproGap.required_field_count} setup fields recorded. This score may be hard to re-run.`
          : `Missing: ${missing.join(", ") || "none listed"}. ${reproGap.populated_field_count} of ${reproGap.required_field_count} setup fields recorded.`,
    })
  }

  if (firstPartyOnly) {
    concerns.push({
      title:
        mode === "policy" ? "Only model developer reported" : `${getRelationshipShortLabel("first_party", mode)} only`,
      detail:
        mode === "policy"
          ? "Only the model developer reported this score; no independent replication is recorded."
          : "First-party only: no independent replication is recorded for this group.",
    })
  }

  if (concerns.length === 0) {
    if (!showWhenClean) return null
    return (
      <SignalTooltip content="No row-level concerns flagged for this score.">
        <span className={cn("inline-flex h-5 w-5 items-center justify-center", className)}>
          <ShieldCheck className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
        </span>
      </SignalTooltip>
    )
  }

  return (
    <SignalTooltip
      content={
        <span className="block space-y-1.5">
          <span className="block font-semibold">{concerns.length === 1 ? "1 concern" : `${concerns.length} concerns`}</span>
          {concerns.map((c) => (
            <span key={c.title} className="block">
              <span className="font-medium">{c.title}.</span>{" "}
              <span className="text-muted-foreground">{c.detail}</span>
            </span>
          ))}
        </span>
      }
    >
      <span
        className={cn(
          "inline-flex h-5 items-center gap-1 rounded-full bg-amber-50 px-1.5 text-amber-700 dark:bg-amber-950/40 dark:text-amber-200 cursor-help",
          className
        )}
        aria-label={`${concerns.length} reporting concern${concerns.length === 1 ? "" : "s"} for this row`}
      >
        <AlertTriangle className="h-3 w-3" />
        {concerns.length > 1 && <span className="text-[10px] font-semibold leading-none">{concerns.length}</span>}
      </span>
    </SignalTooltip>
  )
}
