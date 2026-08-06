"use client"

import { Check, CheckCircle2, ShieldCheck } from "lucide-react"

import { useAudienceMode } from "@/components/audience-mode-provider"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { SignalTooltip } from "./signal-tooltip"

/**
 * VerifiedBadge — a small, simple "this result is verified" marker shown
 * next to an individual evaluation result / metric value.
 *
 * Driven by a single boolean (`is_verified`) the producer emits per atomic
 * result (see docs/verified-badge/README.md). When the flag is false / absent
 * the component renders nothing, so unverified rows stay visually quiet —
 * mirroring the existing row-signal badges (RowSignalsCompact, etc.).
 *
 * Several `design` options are provided so the look can be chosen during
 * review (see /verified-badge-preview). They split into two families:
 *
 *   Icon-only (lowest footprint — best inside dense leaderboards/score cells):
 *     - "check"  (default): clean geometric check-in-circle. Neutral, not
 *                  social-media-y.
 *     - "shield":  shield + check — reads as governance / "validated".
 *                  Matches the ShieldCheck already used for clean row signals.
 *     - "glyph":   hairline rounded box + check — matches the editorial
 *                  .sig-glyph signal-letter vocabulary. Most on-brand.
 *     - "tick":    bare accent check with a hairline underline. Minimal,
 *                  proofreading-mark feel.
 *     - "seal":    scalloped lucide BadgeCheck. Closest to a social verified
 *                  badge — kept for comparison.
 *
 *   Labelled (carry the word "Verified"):
 *     - "tag":   hairline mono-caps outline pill. Editorial label.
 *     - "chip":  filled accent pill. Highest emphasis; use sparingly.
 */

export type VerifiedBadgeDesign =
  | "tile"
  | "check"
  | "shield"
  | "glyph"
  | "tick"
  | "seal"
  | "tag"
  | "chip"
export type VerifiedBadgeSize = "sm" | "md"

/**
 * Two trust tiers share the same mark, distinguished by colour:
 *   - "verified"   (accent/blue): submitter-validated results.
 *   - "recognized" (grey):        known public-leaderboard sources we ingest
 *                                 directly (Artificial Analysis, LLM Stats,
 *                                 HF Open LLM v2, Global-MMLU-Lite) that are
 *                                 not submitter-verified.
 */
type BadgeTone = "verified" | "recognized"

const TONE_CLASSES: Record<
  BadgeTone,
  { text: string; tileBg: string; glyphBorder: string; tickUnderline: string; tagBorder: string; chipBg: string }
> = {
  verified: {
    text: "text-[var(--accent)]",
    tileBg: "bg-[var(--accent)] text-[var(--accent-fg)]",
    glyphBorder: "border-[var(--accent)]/55 text-[var(--accent)]",
    tickUnderline: "text-[var(--accent)] border-[var(--accent)]/40",
    tagBorder: "border-[var(--accent)]/40 text-[var(--accent)]",
    chipBg: "bg-[var(--accent)] text-[var(--accent-fg)] hover:bg-[var(--accent-hover)]",
  },
  recognized: {
    text: "text-[color:var(--fg-muted)]",
    tileBg: "bg-[color:var(--fg-muted)] text-[var(--accent-fg)]",
    glyphBorder: "border-[color:var(--fg-muted)]/55 text-[color:var(--fg-muted)]",
    tickUnderline: "text-[color:var(--fg-muted)] border-[color:var(--fg-muted)]/40",
    tagBorder: "border-[color:var(--fg-muted)]/40 text-[color:var(--fg-muted)]",
    chipBg: "bg-[color:var(--fg-muted)] text-[var(--accent-fg)]",
  },
}

const ICON_SIZE: Record<VerifiedBadgeSize, string> = {
  sm: "h-3.5 w-3.5",
  md: "h-4 w-4",
}

const ICON_ONLY: VerifiedBadgeDesign[] = ["tile", "check", "shield", "glyph", "tick", "seal"]

export function verifiedTooltipCopy(_mode: "research" | "policy"): string {
  // The badge is a provenance signal, not an accuracy/verification claim: it
  // marks results contributed by the org that ran the evaluation. Same copy in
  // both audience modes; aria-label mirrors it (see VerifiedBadge).
  return "Submitted by the organization that ran this evaluation."
}

export function recognizedTooltipCopy(_mode: "research" | "policy"): string {
  // Grey tier: the result was ingested directly from a known source's
  // official API, but the submitter has not been validated.
  return "Imported from this organization's official API."
}

function IconOnly({
  design,
  size,
  tone,
  className,
}: {
  design: VerifiedBadgeDesign
  size: VerifiedBadgeSize
  tone: BadgeTone
  className?: string
}) {
  const sz = ICON_SIZE[size]
  const tc = TONE_CLASSES[tone]
  const base = cn("inline-flex shrink-0 items-center justify-center align-middle", tc.text)

  switch (design) {
    case "tile":
      // Filled accent rounded-square + white check — echoes the EvalEval
      // brand mark (rounded-square accent tile), so it reads as "our"
      // verification rather than a generic/social one. Square, not circular.
      return (
        <span
          className={cn(
            "inline-flex shrink-0 items-center justify-center rounded-[3px] align-middle",
            tc.tileBg,
            size === "md" ? "h-[18px] w-[18px]" : "h-4 w-4",
            className
          )}
        >
          <Check className={size === "md" ? "h-3 w-3" : "h-2.5 w-2.5"} strokeWidth={3.5} />
        </span>
      )
    case "check":
      // Clean geometric check-in-circle. Geometric, not scalloped.
      return (
        <span className={cn(base, className)}>
          <CheckCircle2 className={sz} strokeWidth={2.25} />
        </span>
      )
    case "shield":
      // Governance / "validated" read.
      return (
        <span className={cn(base, className)}>
          <ShieldCheck className={sz} strokeWidth={2} />
        </span>
      )
    case "glyph":
      // Hairline rounded box + check — matches the .sig-glyph editorial
      // signal vocabulary (bordered mark, sharp corners).
      return (
        <span
          className={cn(
            "inline-flex shrink-0 items-center justify-center rounded-[3px] border align-middle",
            tc.glyphBorder,
            size === "md" ? "h-[18px] w-[18px]" : "h-4 w-4",
            className
          )}
        >
          <Check className={size === "md" ? "h-3 w-3" : "h-2.5 w-2.5"} strokeWidth={3} />
        </span>
      )
    case "tick":
      // Bare accent check with a hairline underline — minimal proofreading mark.
      return (
        <span
          className={cn(
            "inline-flex shrink-0 items-center align-middle border-b leading-none",
            tc.tickUnderline,
            className
          )}
        >
          <Check className={sz} strokeWidth={3} />
        </span>
      )
    case "seal":
    default:
      // Original scalloped social-style mark, kept for comparison.
      return (
        <span className={cn(base, className)} role="img">
          <BadgeCheckScalloped className={sz} />
        </span>
      )
  }
}

// Inline copy of lucide's BadgeCheck so "seal" stays available without adding
// it to the active icon imports above.
function BadgeCheckScalloped({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M3.85 8.62a4 4 0 0 1 4.78-4.77 4 4 0 0 1 6.74 0 4 4 0 0 1 4.78 4.78 4 4 0 0 1 0 6.74 4 4 0 0 1-4.77 4.78 4 4 0 0 1-6.75 0 4 4 0 0 1-4.78-4.77 4 4 0 0 1 0-6.76Z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  )
}

export function VerifiedBadge({
  verified,
  recognized,
  design = "check",
  size = "sm",
  withTooltip = true,
  label,
  className,
}: {
  /** The per-result `is_verified` boolean. Null/false/undefined → renders nothing. */
  verified?: boolean | null
  /**
   * Grey fallback tier: result/org comes from a recognized public leaderboard
   * (see lib/evaluators.ts RECOGNIZED_EVALUATOR_NAMES) but isn't submitter-
   * verified. Only takes effect when `verified` is falsy; both falsy → null.
   */
  recognized?: boolean | null
  design?: VerifiedBadgeDesign
  size?: VerifiedBadgeSize
  withTooltip?: boolean
  /** Visible text for the "tag" / "chip" designs. */
  label?: string
  className?: string
}) {
  // Hooks must run unconditionally; guard on the value afterwards.
  const { mode } = useAudienceMode()

  const tone: BadgeTone | null = verified ? "verified" : recognized ? "recognized" : null
  if (!tone) {
    return null
  }

  const tc = TONE_CLASSES[tone]
  const tooltip = tone === "verified" ? verifiedTooltipCopy(mode) : recognizedTooltipCopy(mode)
  const visibleLabel = label ?? (tone === "verified" ? "Verified" : "Recognized")
  // Screen-reader text mirrors the tooltip so the two never drift. `label`
  // ("Verified evaluator") only surfaces visually on the tag/chip designs.
  const ariaLabel = tooltip

  let node: React.ReactNode

  if (ICON_ONLY.includes(design)) {
    node = (
      <span aria-label={ariaLabel} role="img" className="inline-flex">
        <IconOnly design={design} size={size} tone={tone} className={className} />
      </span>
    )
  } else if (design === "tag") {
    // Hairline mono-caps outline pill — matches the .ec-tag editorial
    // vocabulary (sharp corners, IBM Plex Mono, wide tracking).
    node = (
      <span
        className={cn(
          "inline-flex shrink-0 items-center gap-1 rounded-[2px] border px-1.5 py-0.5 align-middle",
          tc.tagBorder,
          "font-mono text-[10px] font-semibold uppercase tracking-[0.12em]",
          className
        )}
        aria-label={ariaLabel}
      >
        <Check className={size === "md" ? "h-3.5 w-3.5" : "h-3 w-3"} strokeWidth={3} />
        {visibleLabel}
      </span>
    )
  } else {
    // "chip" — filled accent pill, highest-emphasis.
    node = (
      <Badge
        className={cn(
          "shrink-0 gap-1 rounded-full border-transparent align-middle",
          tc.chipBg,
          className
        )}
        aria-label={ariaLabel}
      >
        <Check className={ICON_SIZE[size]} strokeWidth={3} />
        {visibleLabel}
      </Badge>
    )
  }

  if (!withTooltip) {
    return node
  }

  // Short single-sentence copy → render it on one tight line instead of
  // wrapping inside the default 320px box (which left a lot of empty space).
  return (
    <SignalTooltip content={tooltip} contentClassName="max-w-none whitespace-nowrap px-2.5 py-1.5">
      {node}
    </SignalTooltip>
  )
}
