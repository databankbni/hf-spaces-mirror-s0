"use client"

import { UsersRound } from "lucide-react"

import { useAudienceMode } from "@/components/audience-mode-provider"
import { Badge } from "@/components/ui/badge"
import type { CrossPartyDivergence } from "@/lib/backend-artifacts"
import { cn } from "@/lib/utils"
import { formatSignalNumber } from "./signal-utils"
import { SignalTooltip } from "./signal-tooltip"

export function CrossPartyDivergenceBadge({
  divergence,
  className,
}: {
  divergence?: CrossPartyDivergence | null
  className?: string
}) {
  const { mode } = useAudienceMode()
  const isResearchView = mode === "research"

  if (!divergence?.has_cross_party_divergence) {
    return null
  }

  const magnitude = formatSignalNumber(divergence.divergence_magnitude)
  const orgCount = divergence.organization_count
  const tooltip = isResearchView
    ? `Reports diverge by ${magnitude} across ${orgCount} organization${orgCount === 1 ? "" : "s"}.`
    : "Different organizations reported different scores for this same model on this same benchmark."

  return (
    <SignalTooltip content={tooltip}>
      <Badge
        variant="outline"
        className={cn(
          "border-violet-300 bg-violet-50 text-violet-900 dark:border-violet-900/60 dark:bg-violet-950/40 dark:text-violet-100",
          className
        )}
      >
        <UsersRound className="h-3 w-3" />
        {isResearchView ? "Cross-party divergence" : "Sources disagree"}
      </Badge>
    </SignalTooltip>
  )
}
