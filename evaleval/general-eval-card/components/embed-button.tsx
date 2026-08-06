"use client"

import { type CSSProperties, useEffect, useMemo, useRef, useState } from "react"
import { Check, Code2, Copy, ExternalLink, X } from "lucide-react"

export interface EmbedVariant {
  id: string
  /** Display name in the variant picker (e.g. "Histogram", "Frontier"). */
  label: string
  /** Embed route for this variant. */
  embedPath: string
}

interface EmbedButtonProps {
  /** Path relative to the site root, e.g. `/embed/eval/leaderboard/mmlu`.
   *  Used when there is exactly one embeddable view. Use `variants` when
   *  the surface ships in multiple views (e.g. histogram vs. frontier). */
  embedPath?: string
  /** Multiple variants of the same surface — popover shows a small picker
   *  so users can choose which view to embed. */
  variants?: EmbedVariant[]
  /** Short label for the embeddable surface, shown in the popover header. */
  label: string
  /** Default iframe height in pixels (width is always 100% of the parent). */
  defaultHeight?: number
  /** Tighter affordance for plots with limited room. */
  size?: "sm" | "md"
  /** When `true`, position the button absolutely in the top-right of the
   *  nearest positioned ancestor. When `false` (default), render inline
   *  so callers can place it inside a flex header without overlap. */
  floating?: boolean
}

/**
 * Embed-this affordance pinned to the top-right of an embeddable surface.
 * Click → popover with a copyable iframe snippet + a "preview" link to
 * open the embed route in a new tab. Anchored absolutely; the parent
 * container should be `position: relative`.
 */
export function EmbedButton({
  embedPath,
  variants,
  label,
  defaultHeight = 480,
  size = "md",
  floating = false,
}: EmbedButtonProps) {
  const resolvedVariants: EmbedVariant[] = useMemo(() => {
    if (variants && variants.length > 0) return variants
    if (embedPath) return [{ id: "default", label, embedPath }]
    return []
  }, [variants, embedPath, label])
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const [height, setHeight] = useState(defaultHeight)
  const [activeVariantId, setActiveVariantId] = useState<string>(
    () => resolvedVariants[0]?.id ?? "default",
  )
  const activeVariant =
    resolvedVariants.find((v) => v.id === activeVariantId) ?? resolvedVariants[0]
  const popoverRef = useRef<HTMLDivElement | null>(null)
  const triggerRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    if (!open) return
    function onDocClick(e: MouseEvent) {
      const t = e.target as Node
      if (popoverRef.current?.contains(t)) return
      if (triggerRef.current?.contains(t)) return
      setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false)
    }
    document.addEventListener("mousedown", onDocClick)
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("mousedown", onDocClick)
      document.removeEventListener("keydown", onKey)
    }
  }, [open])

  // Build the snippet at render time so it picks up the deployed origin
  // when copied from the user's browser. Falls back to a relative URL
  // during SSR so initial markup stays stable.
  const activePath = activeVariant?.embedPath ?? ""
  const fullUrl =
    typeof window !== "undefined" && activePath
      ? new URL(activePath, window.location.origin).toString()
      : activePath
  const titleAttr =
    resolvedVariants.length > 1 && activeVariant
      ? `${label} — ${activeVariant.label}`
      : label
  const snippet = `<iframe src="${fullUrl}" width="100%" height="${height}" frameborder="0" style="border:1px solid #e5e5e5;border-radius:4px;" loading="lazy" title="${titleAttr}"></iframe>`

  async function copySnippet() {
    try {
      await navigator.clipboard.writeText(snippet)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch {
      // Fallback: select the textarea for manual copy
      const ta = popoverRef.current?.querySelector("textarea")
      if (ta instanceof HTMLTextAreaElement) {
        ta.select()
      }
    }
  }


  const wrapperStyle: CSSProperties = floating
    ? { position: "absolute", top: 8, right: 8, zIndex: 5 }
    : { position: "relative", display: "inline-block" }

  return (
    <div className="embed-button-root" style={wrapperStyle}>
      <button
        ref={triggerRef}
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          setOpen((v) => !v)
        }}
        className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border p-0 transition-colors"
        style={{
          color: open ? "var(--bg)" : "var(--fg-muted)",
          background: open ? "var(--fg)" : "var(--bg)",
          borderColor: open ? "var(--fg)" : "var(--border-soft)",
        }}
        title={`Embed ${label}`}
        aria-label={`Embed ${label}`}
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <Code2 className="h-3.5 w-3.5" aria-hidden />
      </button>

      {open && (
        <div
          ref={popoverRef}
          role="dialog"
          aria-label={`Embed ${label}`}
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            right: 0,
            width: "min(420px, calc(100vw - 32px))",
            background: "var(--bg)",
            border: "1px solid var(--fg)",
            boxShadow: "0 4px 20px rgba(0,0,0,0.08)",
            padding: 14,
            zIndex: 10,
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-baseline justify-between gap-3 mb-2">
            <div
              className="font-mono uppercase"
              style={{
                fontSize: 10,
                letterSpacing: "0.14em",
                color: "var(--fg)",
              }}
            >
              Embed · {label}
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close"
              style={{ color: "var(--fg-muted)" }}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          <p
            className="m-0 mb-3"
            style={{
              fontSize: 12,
              lineHeight: 1.5,
              color: "var(--fg-muted)",
            }}
          >
            Paste this iframe snippet anywhere HTML is allowed (blog post,
            Notion, Confluence, etc.). The embed updates automatically
            when the underlying data refreshes.
          </p>

          {resolvedVariants.length > 1 && (
            <div className="mb-3 flex flex-wrap items-center gap-1">
              <span
                className="font-mono uppercase mr-1"
                style={{
                  fontSize: 10,
                  letterSpacing: "0.12em",
                  color: "var(--fg-subtle)",
                }}
              >
                View
              </span>
              {resolvedVariants.map((v) => {
                const isActive = v.id === activeVariant?.id
                return (
                  <button
                    key={v.id}
                    type="button"
                    onClick={() => setActiveVariantId(v.id)}
                    className="inline-flex items-center font-mono uppercase border"
                    style={{
                      fontSize: 10,
                      letterSpacing: "0.1em",
                      padding: "3px 8px",
                      color: isActive ? "var(--bg)" : "var(--fg-muted)",
                      background: isActive ? "var(--fg)" : "var(--bg)",
                      borderColor: isActive ? "var(--fg)" : "var(--border-soft)",
                      borderRadius: 2,
                    }}
                  >
                    {v.label}
                  </button>
                )
              })}
            </div>
          )}

          <textarea
            readOnly
            value={snippet}
            spellCheck={false}
            rows={4}
            onFocus={(e) => e.currentTarget.select()}
            className="font-mono w-full"
            style={{
              fontSize: 11,
              lineHeight: 1.5,
              padding: "8px 10px",
              border: "1px solid var(--border-soft)",
              background: "var(--bg-warm)",
              color: "var(--fg)",
              resize: "vertical",
              borderRadius: 2,
            }}
          />

          <div className="mt-3 flex items-center gap-3">
            <label
              className="flex items-baseline gap-2 font-mono"
              style={{
                fontSize: 10,
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                color: "var(--fg-muted)",
              }}
            >
              Height
              <input
                type="number"
                min={120}
                max={2000}
                step={20}
                value={height}
                onChange={(e) => {
                  const next = Number(e.target.value)
                  if (Number.isFinite(next)) setHeight(Math.max(120, Math.min(2000, next)))
                }}
                className="font-mono tabular-nums"
                style={{
                  width: 64,
                  fontSize: 11,
                  padding: "2px 6px",
                  border: "1px solid var(--border-soft)",
                  background: "var(--bg)",
                  color: "var(--fg)",
                  borderRadius: 2,
                }}
              />
              <span style={{ color: "var(--fg-subtle)" }}>px</span>
            </label>

            <div className="flex-1" />

            <a
              href={activePath}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 font-mono uppercase"
              style={{
                fontSize: 10,
                letterSpacing: "0.12em",
                color: "var(--fg-muted)",
                textDecoration: "none",
              }}
              title="Open the embed in a new tab"
            >
              Preview
              <ExternalLink className="h-3 w-3" aria-hidden />
            </a>

            <button
              type="button"
              onClick={copySnippet}
              className="inline-flex items-center gap-1 font-mono uppercase"
              style={{
                fontSize: 10,
                letterSpacing: "0.12em",
                padding: "5px 10px",
                color: copied ? "var(--bg)" : "var(--bg)",
                background: copied ? "var(--accent)" : "var(--fg)",
                border: "1px solid",
                borderColor: copied ? "var(--accent)" : "var(--fg)",
                borderRadius: 2,
              }}
            >
              {copied ? (
                <>
                  <Check className="h-3 w-3" aria-hidden />
                  Copied
                </>
              ) : (
                <>
                  <Copy className="h-3 w-3" aria-hidden />
                  Copy
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
