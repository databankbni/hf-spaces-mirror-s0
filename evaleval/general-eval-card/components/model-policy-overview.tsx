"use client"

import { BookOpen, ShieldCheck, AlertTriangle, GitCompareArrows, Users, Layers } from "lucide-react"
import { SignalTooltip } from "@/components/signals/signal-tooltip"
import type { ModelPolicySummary } from "@/lib/policy-summaries"

interface ModelPolicyOverviewProps {
  /** Display name of the model — surfaced in the kicker. */
  modelName: string
  policySummary: ModelPolicySummary
  /** Optional one-line model-scale framing (params / size context). */
  scaleNote?: string | null
}

/**
 * Plain-language policy note for the model detail page. Mirrors the structure
 * of `<PolicyOverview>` for the eval page but reframes around model-level
 * questions: how broad is the evidence, who reported it, can it be re-run,
 * can it be compared.
 *
 * All copy is rule-based — see lib/policy-summaries.ts. There is no live
 * LLM inference at runtime.
 */
export function ModelPolicyOverview({ modelName, policySummary, scaleNote }: ModelPolicyOverviewProps) {
  const {
    scopeSentence,
    coverageSentence,
    gapSentence,
    reportingSentence,
    reproducibilitySentence,
    comparabilitySentence,
    verificationLabel,
  } = policySummary

  return (
    <section className="ec-card warm" style={{ padding: "20px 24px" }}>
      <header className="mb-3 flex flex-wrap items-center gap-3">
        <BookOpen className="h-4 w-4" style={{ color: "var(--fg-muted)" }} />
        <span className="kicker kicker-fg" style={{ fontSize: 12, letterSpacing: "0.16em" }}>
          At a glance
        </span>
        <span
          className="font-mono text-[10px] uppercase tracking-[0.12em]"
          style={{ color: "var(--fg-subtle)" }}
        >
          {modelName}
        </span>
        {verificationLabel && (
          <span
            className="ec-tag outline ml-auto"
            style={{ textTransform: "uppercase" }}
            title="Whether scores have been reported by parties other than the model's developer."
          >
            <ShieldCheck className="h-3 w-3 shrink-0" />
            {verificationLabel}
          </span>
        )}
      </header>

      <dl
        className="grid gap-y-3 text-[14px]"
        style={{ gridTemplateColumns: "max-content 1fr", columnGap: 24 }}
      >
        <Row icon="layers" label="Reported on">
          {scopeSentence}
          {coverageSentence ? <> {coverageSentence}</> : null}
        </Row>

        {gapSentence && (
          <Row icon="alert" label="Gap" tone="accent">
            {gapSentence}
          </Row>
        )}

        <Row icon="users" label="Reported by">
          {reportingSentence}
        </Row>

        {reproducibilitySentence && (
          <Row icon="alert" label="Re-runnable">
            <SignalTooltip content="Whether someone could re-run this evaluation with the information available.">
              <span
                className="underline decoration-dotted underline-offset-4 cursor-help"
                style={{ textDecorationColor: "var(--fg-subtle)" }}
              >
                {reproducibilitySentence}
              </span>
            </SignalTooltip>
          </Row>
        )}

        {comparabilitySentence && (
          <Row icon="compare" label="Comparable">
            <SignalTooltip content="Flags when score differences may come from setup choices or different reporting sources.">
              <span
                className="underline decoration-dotted underline-offset-4 cursor-help"
                style={{ textDecorationColor: "var(--fg-subtle)" }}
              >
                {comparabilitySentence}
              </span>
            </SignalTooltip>
          </Row>
        )}

        {scaleNote && (
          <Row label="Scale note">
            {scaleNote}
          </Row>
        )}
      </dl>
    </section>
  )
}

function Row({
  icon,
  label,
  tone,
  children,
}: {
  icon?: "layers" | "alert" | "compare" | "users"
  label: string
  tone?: "accent"
  children: React.ReactNode
}) {
  const Icon =
    icon === "layers"
      ? Layers
      : icon === "alert"
        ? AlertTriangle
        : icon === "compare"
          ? GitCompareArrows
          : icon === "users"
            ? Users
            : null

  return (
    <>
      <dt
        className="font-mono uppercase tracking-[0.14em] inline-flex items-center gap-1.5"
        style={{
          fontSize: 10,
          color: tone === "accent" ? "var(--accent)" : "var(--fg-subtle)",
          paddingTop: 3,
        }}
      >
        {Icon && <Icon className="h-3 w-3 shrink-0" />}
        {label}
      </dt>
      <dd style={{ color: "var(--fg)", lineHeight: 1.6, margin: 0 }}>
        {children}
      </dd>
    </>
  )
}
