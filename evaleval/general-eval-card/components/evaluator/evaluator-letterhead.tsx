"use client"

import { ExternalLink } from "lucide-react"

import { OrgLogo } from "@/components/evaluator/org-logo"
import { VerifiedBadge } from "@/components/signals/verified-badge"
import { cn } from "@/lib/utils"

/**
 * EvaluatorLetterhead — the masthead header for an evaluator (reporting org)
 * page. A full-bleed warm band with a hairline base rule, set like an academic
 * journal letterhead:
 *
 *   eyebrow ("Evaluator")
 *   [ logo plate ]  Org Name  ✓        ← vertically-centred hero row
 *                   reporting organisation · N evaluations · N families · N verified
 *
 * The logo is rendered through <OrgLogo/>, which auto-squares and auto-sizes
 * any aspect ratio onto a consistent light plate and falls back to a monogram
 * when no mark is known. The meta strip is indented to begin under the name
 * (plate width + gap) so the lockup reads as one unit.
 *
 * Full bleed: the negative margin matches the evaluator page's responsive
 * padding (px-4 → sm:px-8) so the band paints to the content-column edges
 * without causing horizontal overflow at any width.
 */

export interface EvaluatorLetterheadProps {
  name: string
  /** Brand-mark URL/path or null → monogram. Sourced from the registry org
   *  metadata (organizations.json sidecar). */
  logoSrc: string | null
  /** Org homepage (registry `website`). When present, a small external-link
   *  affordance is shown next to the name; hidden entirely when absent. */
  homepageUrl?: string
  isVerified: boolean
  recognized: boolean
  evalCount: number
  familyCount: number
  verifiedCount: number
}

export default function EvaluatorLetterhead({
  name,
  logoSrc,
  homepageUrl,
  isVerified,
  recognized,
  evalCount,
  familyCount,
  verifiedCount,
}: EvaluatorLetterheadProps) {
  return (
    <header
      className={cn(
        "-mx-4 mb-8 border-b border-[color:var(--border-soft)] bg-[color:var(--bg-warm)] px-4",
        "sm:-mx-8 sm:px-8",
      )}
    >
      <div className="py-8">
        {logoSrc === null && <span className="sr-only">{name} (no logo available)</span>}

        <div className="kicker">Evaluator</div>

        {/* Hero row — plate + name vertically centred together. */}
        <div className="mt-2.5 flex items-center gap-5 sm:gap-6">
          <OrgLogo
            name={name}
            src={logoSrc}
            className="[--logo-size:64px] sm:[--logo-size:72px]"
          />

          <h1 className="ec-page-h1 inline-flex flex-wrap items-center gap-x-2.5 gap-y-1">
            <span className="min-w-0 break-words">{name}</span>
            <VerifiedBadge verified={isVerified} recognized={recognized} size="md" />
            {homepageUrl && (
              <a
                href={homepageUrl}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Visit ${name}'s homepage`}
                title={`Visit ${name}'s homepage`}
                className="inline-flex shrink-0 items-center text-[color:var(--fg-subtle)] transition-colors hover:text-[color:var(--accent)]"
              >
                <ExternalLink className="h-4 w-4" aria-hidden />
              </a>
            )}
          </h1>
        </div>

        {/* Mono-caps colophon — indented to begin under the name. */}
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 pl-[84px] font-mono text-[11px] uppercase tracking-[0.12em] text-[color:var(--fg-muted)] sm:pl-[96px]">
          <span>Reporting organisation</span>
          <Dot />
          <span>
            <span className="font-semibold tabular-nums text-[color:var(--fg)]">
              {evalCount.toLocaleString()}
            </span>{" "}
            {evalCount === 1 ? "evaluation" : "evaluations"}
          </span>
          <Dot />
          <span>
            <span className="font-semibold tabular-nums text-[color:var(--fg)]">
              {familyCount.toLocaleString()}
            </span>{" "}
            {familyCount === 1 ? "family" : "families"}
          </span>
          <Dot />
          <span>
            <span className="font-semibold tabular-nums text-[color:var(--fg)]">
              {verifiedCount.toLocaleString()}
            </span>{" "}
            verified
          </span>
        </div>
      </div>
    </header>
  )
}

function Dot() {
  return (
    <span aria-hidden="true" className="text-[color:var(--fg-subtle)]">
      ·
    </span>
  )
}
