"use client"

import { useEffect, useState } from "react"
import { Eye } from "lucide-react"
import { useAudienceMode } from "@/components/audience-mode-provider"
import { fetchBackendManifest } from "@/lib/dashboard-data-client"
import { cn } from "@/lib/utils"

function formatSnapshotDate(value: string | null | undefined): string | null {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}

/**
 * Page-scoped reader-mode bar. Mounted only on routes whose rendering
 * actually branches on audience mode (currently the eval and model
 * detail pages); every other route is mode-agnostic so showing the
 * toggle there would be noise.
 */
export function ReaderModeBar() {
  const { mode, setMode } = useAudienceMode()
  const [snapshotLabel, setSnapshotLabel] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchBackendManifest()
      .then((status) => {
        if (cancelled) return
        setSnapshotLabel(formatSnapshotDate(status?.currentManifest?.generated_at))
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className={cn("mode-banner", `mode-${mode}`)}>
      <div className="mode-banner-inner">
        <div className="ec-mode-toggle" title="Same evidence, different level of detail.">
          <span className="ec-mode-toggle-label" aria-label="Reader mode">
            <Eye className="h-3.5 w-3.5" />
          </span>
          <button
            type="button"
            className={mode === "policy" ? "on" : ""}
            onClick={() => setMode("policy")}
            title="Plain-language summary for non-technical readers"
          >
            Summary view
          </button>
          <button
            type="button"
            className={mode === "research" ? "on" : ""}
            onClick={() => setMode("research")}
            title="Full methodology, configuration, and missing-field detail"
          >
            Researcher view
          </button>
        </div>
        <span className="mode-banner-spacer" />
        {snapshotLabel && (
          <span className="mode-banner-meta">Snapshot · {snapshotLabel}</span>
        )}
      </div>
    </div>
  )
}
