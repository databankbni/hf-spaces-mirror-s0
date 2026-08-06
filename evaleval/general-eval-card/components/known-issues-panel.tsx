"use client"

import { AlertOctagon, AlertTriangle, ExternalLink, Info } from "lucide-react"
import type { KnownIssue } from "@/lib/known-issues"

interface KnownIssuesPanelProps {
  issues: KnownIssue[]
  /**
   * "compact" — single-line summary chip suitable for surfacing at the top of
   * the policy overview. "full" — full bordered list with descriptions.
   */
  variant?: "compact" | "full"
}

const SEVERITY_ACCENT: Record<KnownIssue["severity"], string> = {
  info: "var(--accent)",
  warning: "oklch(0.65 0.14 75)",
  critical: "var(--destructive)",
}

const SEVERITY_STYLE: Record<KnownIssue["severity"], { Icon: React.ComponentType<{ className?: string }>; label: string }> = {
  info: { Icon: Info, label: "Note" },
  warning: { Icon: AlertTriangle, label: "Known issue" },
  critical: { Icon: AlertOctagon, label: "Critical issue" },
}

export function KnownIssuesPanel({ issues, variant = "full" }: KnownIssuesPanelProps) {
  if (issues.length === 0) return null

  const sorted = [...issues].sort((a, b) => severityRank(b.severity) - severityRank(a.severity))
  const headlineSeverity = sorted[0].severity
  const Style = SEVERITY_STYLE[headlineSeverity]
  const Icon = Style.Icon
  const accent = SEVERITY_ACCENT[headlineSeverity]

  if (variant === "compact") {
    return (
      <div
        className="flex items-start gap-2 text-sm"
        style={{
          border: "1px solid var(--border-strong)",
          borderLeft: `3px solid ${accent}`,
          background: "var(--bg-warm)",
          padding: "10px 14px",
          color: "var(--fg-muted)",
          lineHeight: 1.6,
        }}
      >
        <span style={{ color: accent, flexShrink: 0, marginTop: 2 }}><Icon className="h-4 w-4" /></span>
        <div className="min-w-0">
          <strong style={{ color: "var(--fg)", fontWeight: 600 }}>
            {issues.length} known issue{issues.length === 1 ? "" : "s"} documented
          </strong>
          <span>. See below for details.</span>
        </div>
      </div>
    )
  }

  return (
    <section className="space-y-2">
      <div className="kicker mb-2">Known issues with this benchmark</div>
      <ul className="space-y-2">
        {sorted.map((issue, idx) => {
          const S = SEVERITY_STYLE[issue.severity]
          const I = S.Icon
          const a = SEVERITY_ACCENT[issue.severity]
          return (
            <li
              key={`${issue.title}-${idx}`}
              style={{
                border: "1px solid var(--border-strong)",
                borderLeft: `3px solid ${a}`,
                background: "var(--bg-warm)",
                padding: "12px 16px",
              }}
            >
              <div className="flex items-start gap-2">
                <span style={{ color: a, flexShrink: 0, marginTop: 2 }}><I className="h-4 w-4" /></span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span
                      className="font-mono uppercase"
                      style={{ fontSize: 10, letterSpacing: "0.18em", color: a, fontWeight: 600 }}
                    >
                      {S.label}
                    </span>
                    <span style={{ fontSize: 14, fontWeight: 600, color: "var(--fg)" }}>{issue.title}</span>
                  </div>
                  <p style={{ marginTop: 6, fontSize: 13, lineHeight: 1.55, color: "var(--fg-muted)" }}>{issue.summary}</p>
                  {(issue.source_url || issue.published) && (
                    <div className="mt-2 flex flex-wrap items-center gap-3" style={{ fontSize: 11 }}>
                      {issue.source_url && (
                        <a
                          href={issue.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1"
                          style={{ color: "var(--accent)", borderBottom: "1px solid var(--border-strong)" }}
                        >
                          Source <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                      {issue.published && <span style={{ color: "var(--fg-subtle)" }}>Published {issue.published}</span>}
                    </div>
                  )}
                </div>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function severityRank(s: KnownIssue["severity"]): number {
  if (s === "critical") return 3
  if (s === "warning") return 2
  return 1
}
