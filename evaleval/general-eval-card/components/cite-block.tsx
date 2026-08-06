"use client"

import { useState } from "react"
import { Check, Copy } from "lucide-react"

/** A labeled, copy-pasteable BibTeX block. */
export function CiteBlock({ bibtex, label = "BibTeX" }: { bibtex: string; label?: string }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(bibtex)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch {
      // clipboard unavailable — the text is still selectable in the <pre>.
    }
  }

  return (
    <div className="border border-[color:var(--border-soft)]">
      <div className="flex items-center justify-between border-b border-[color:var(--border-soft)] bg-[color:var(--bg-warm)] px-4 py-2.5">
        <span className="kicker">{label}</span>
        <button
          type="button"
          onClick={copy}
          className="inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-[color:var(--fg-muted)] transition-colors hover:text-[color:var(--fg)]"
        >
          {copied ? (
            <>
              <Check className="h-3.5 w-3.5 text-[color:var(--accent)]" aria-hidden />
              Copied
            </>
          ) : (
            <>
              <Copy className="h-3.5 w-3.5" aria-hidden />
              Copy
            </>
          )}
        </button>
      </div>
      <pre className="m-0 overflow-x-auto p-4 font-mono text-[12px] leading-[1.6] text-[color:var(--fg)]">
        <code>{bibtex}</code>
      </pre>
    </div>
  )
}
