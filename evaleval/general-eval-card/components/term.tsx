"use client"

import type { ReactNode } from "react"
import { lookupTerm } from "@/lib/glossary"
import { SignalTooltip } from "@/components/signals/signal-tooltip"

interface TermProps {
  /**
   * Glossary key to look up. Defaults to the visible text.
   */
  term?: string
  children: ReactNode
  /**
   * Override the tooltip body. If omitted, glossary entry is used.
   */
  explain?: ReactNode
  className?: string
}

export function Term({ term, children, explain, className }: TermProps) {
  const key = term ?? (typeof children === "string" ? children : undefined)
  const entry = key ? lookupTerm(key) : undefined

  const content = explain ?? (entry ? (
    <span className="block space-y-1">
      <span className="block">{entry.short}</span>
      {entry.long ? <span className="block text-muted-foreground">{entry.long}</span> : null}
    </span>
  ) : null)

  if (!content) {
    return <span className={className}>{children}</span>
  }

  return (
    <SignalTooltip content={content}>
      <span
        className={
          "underline decoration-dotted decoration-muted-foreground/60 underline-offset-4 cursor-help " +
          (className ?? "")
        }
      >
        {children}
      </span>
    </SignalTooltip>
  )
}
