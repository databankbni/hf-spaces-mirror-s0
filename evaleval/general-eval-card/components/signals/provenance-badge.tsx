"use client"

import { AlertTriangle, BadgeCheck, Handshake, UserRoundCheck } from "lucide-react"

import { useAudienceMode } from "@/components/audience-mode-provider"
import { Badge } from "@/components/ui/badge"
import type { Provenance, ProvenanceSourceType } from "@/lib/backend-artifacts"
import { cn } from "@/lib/utils"
import { SignalTooltip } from "./signal-tooltip"

export function getRelationshipDisplayName(value: string | null | undefined) {
  const normalized = value?.replace(/_/g, " ").trim()
  if (!normalized) {
    return "Unknown"
  }

  return normalized
    .split(/\s+/)
    .map((token) => `${token.charAt(0).toUpperCase()}${token.slice(1).toLowerCase()}`)
    .join(" ")
}

export function getRelationshipShortLabel(value: string | null | undefined, mode: "research" | "policy" = "research") {
  switch ((value ?? "").toLowerCase()) {
    case "first_party":
      return mode === "policy" ? "Reported by model developer" : "1st party"
    case "third_party":
      return mode === "policy" ? "Independently reported" : "3rd party"
    case "collaborative":
      return mode === "policy" ? "Joint report" : "Collaborative"
    case "other":
      return "Other"
    default:
      return getRelationshipDisplayName(value)
  }
}

export function getRelationshipBadgeTone(value: string | null | undefined): string {
  switch ((value ?? "").toLowerCase()) {
    case "first_party":
      return "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-100"
    case "third_party":
      return "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-900/60 dark:bg-emerald-950/40 dark:text-emerald-100"
    case "collaborative":
      return "border-sky-300 bg-sky-50 text-sky-900 dark:border-sky-900/60 dark:bg-sky-950/40 dark:text-sky-100"
    default:
      return "border-border/70 bg-muted/40 text-muted-foreground"
  }
}

function normalizeSourceType(value: string | null | undefined): ProvenanceSourceType | "other" | null {
  switch ((value ?? "").toLowerCase()) {
    case "first_party":
    case "third_party":
    case "collaborative":
    case "unspecified":
      return value?.toLowerCase() as ProvenanceSourceType
    case "other":
      return "other"
    default:
      return null
  }
}

function ProvenanceIcon({ sourceType }: { sourceType: ProvenanceSourceType | "other" }) {
  if (sourceType === "third_party") {
    return <BadgeCheck className="h-3 w-3" />
  }

  if (sourceType === "collaborative") {
    return <Handshake className="h-3 w-3" />
  }

  return <UserRoundCheck className="h-3 w-3" />
}

export function ProvenanceBadge({
  provenance,
  relationship,
  sourceOrganizationName,
  showOther = false,
  className,
}: {
  provenance?: Provenance | null
  relationship?: string | null
  sourceOrganizationName?: string | null
  showOther?: boolean
  className?: string
}) {
  const { mode } = useAudienceMode()
  const sourceType = provenance?.source_type ?? normalizeSourceType(relationship)

  if (!sourceType || sourceType === "unspecified" || (!showOther && sourceType === "other")) {
    return null
  }

  const firstPartyOnly = provenance?.first_party_only === true
  const label = firstPartyOnly
    ? mode === "policy"
      ? "Only model developer reported"
      : "1st party only"
    : getRelationshipShortLabel(sourceType, mode)

  const tooltip = firstPartyOnly
    ? mode === "policy"
      ? "Only the model developer reported this score; no independent replication is recorded."
      : "First-party only - no independent replication is recorded for this group."
    : sourceOrganizationName
      ? `Reported by ${sourceOrganizationName}.`
      : getRelationshipDisplayName(sourceType)

  return (
    <SignalTooltip content={tooltip}>
      <Badge
        variant="outline"
        className={cn(getRelationshipBadgeTone(sourceType), className)}
      >
        <ProvenanceIcon sourceType={sourceType} />
        {label}
        {firstPartyOnly && <AlertTriangle className="h-3 w-3" />}
      </Badge>
    </SignalTooltip>
  )
}
