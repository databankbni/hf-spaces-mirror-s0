"use client"

import { useCallback, useEffect, useRef } from "react"

interface InfiniteScrollProps {
  hasMore: boolean
  onLoadMore: () => void
  rootMargin?: string
  className?: string
  loadingLabel?: string
  endLabel?: string
  totalLabel?: string
}

/**
 * Renders a sentinel that triggers `onLoadMore` whenever it scrolls into view.
 * The sentinel is also clickable (and acts as the "end" footer) for keyboard
 * users and as a visible affordance.
 */
export function InfiniteScrollSentinel({
  hasMore,
  onLoadMore,
  rootMargin = "600px",
  className,
  loadingLabel = "Loading more…",
  endLabel = "End of list",
  totalLabel,
}: InfiniteScrollProps) {
  const ref = useRef<HTMLDivElement | null>(null)
  const onLoadMoreRef = useRef(onLoadMore)

  useEffect(() => {
    onLoadMoreRef.current = onLoadMore
  }, [onLoadMore])

  useEffect(() => {
    const node = ref.current
    if (!node || !hasMore) return

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            onLoadMoreRef.current()
          }
        }
      },
      { rootMargin },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [hasMore, rootMargin])

  const handleClick = useCallback(() => {
    if (hasMore) onLoadMoreRef.current()
  }, [hasMore])

  return (
    <div
      ref={ref}
      onClick={handleClick}
      role={hasMore ? "button" : undefined}
      tabIndex={hasMore ? 0 : -1}
      onKeyDown={(e) => {
        if (hasMore && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault()
          onLoadMoreRef.current()
        }
      }}
      className={
        className ??
        "mt-8 flex items-center justify-center gap-3 border-t border-[color:var(--border-soft)] py-6 font-mono text-[10.5px] uppercase tracking-[0.18em] text-[color:var(--fg-subtle)]"
      }
      style={{ cursor: hasMore ? "pointer" : "default" }}
    >
      {hasMore ? (
        <>
          <span
            aria-hidden
            className="inline-block h-2 w-2 animate-pulse rounded-full bg-[color:var(--accent)]"
          />
          <span>{loadingLabel}</span>
        </>
      ) : (
        <>
          <span>{endLabel}</span>
          {totalLabel && (
            <>
              <span aria-hidden className="text-[color:var(--fg-subtle)]">·</span>
              <span>{totalLabel}</span>
            </>
          )}
        </>
      )}
    </div>
  )
}
