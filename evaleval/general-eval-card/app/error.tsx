"use client"

import { useEffect } from "react"

/**
 * Top-level error boundary for every route under app/. Next.js renders
 * this when a server component throws or a client render exception
 * escapes the closest boundary. Replaces the bare default
 * "Application error: a client-side exception has occurred" overlay
 * with a recoverable affordance so a transient backend hiccup (cold
 * parquet cache, slow first query) doesn't strand the reader on an
 * unfriendly screen.
 */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    if (typeof window !== "undefined" && "console" in window) {
      console.error("[route-error]", error)
    }
  }, [error])

  return (
    <div
      style={{
        minHeight: "60vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px",
      }}
    >
      <div
        style={{
          maxWidth: 460,
          width: "100%",
          padding: "28px 28px 24px",
          border: "1px solid var(--border-soft)",
          background: "var(--bg)",
        }}
      >
        <div
          className="font-mono uppercase"
          style={{
            fontSize: 10,
            letterSpacing: "0.18em",
            color: "var(--fg-subtle)",
            marginBottom: 14,
          }}
        >
          Something went wrong
        </div>
        <p
          style={{
            margin: 0,
            color: "var(--fg)",
            fontSize: 15,
            lineHeight: 1.55,
          }}
        >
          We couldn't load this view. The data backend may still be
          warming up: most cold-start hiccups clear within a few
          seconds.
        </p>
        <div
          style={{
            display: "flex",
            gap: 10,
            marginTop: 20,
            flexWrap: "wrap",
          }}
        >
          <button type="button" className="btn-ec" onClick={() => reset()}>
            Try again
          </button>
          <a href="/" className="btn-ec outline">
            Back to home
          </a>
        </div>
        {error.digest && (
          <div
            className="font-mono"
            style={{
              marginTop: 18,
              fontSize: 10,
              color: "var(--fg-subtle)",
              wordBreak: "break-all",
            }}
          >
            ref: {error.digest}
          </div>
        )}
      </div>
    </div>
  )
}
