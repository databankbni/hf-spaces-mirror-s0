import type React from "react"

/**
 * Minimal layout for embed routes — no Navigation, no AudienceModeProvider
 * audience bar. Designed for iframe embedding on third-party sites.
 * Pages under /embed/* render a single self-contained surface
 * (leaderboard, distribution, frontier, etc.) at the size the parent
 * iframe allocates.
 *
 * A small EvalEval brand mark sits in the top-left corner of every
 * embed and links out to the canonical Evaluation Cards site, so embed
 * viewers can always trace the data back to the source.
 */
export default function EmbedLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <div
      className="embed-shell"
      style={{
        minHeight: "100dvh",
        background: "var(--bg)",
        color: "var(--fg)",
        padding: "16px",
      }}
    >
      <a
        href="https://evalcards.evalevalai.com/"
        target="_blank"
        rel="noopener noreferrer"
        className="font-mono"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 12,
          color: "var(--fg)",
          textDecoration: "none",
          fontSize: 12,
          lineHeight: 1,
        }}
        title="Open Evaluation Cards"
      >
        <img
          src="https://evalevalai.com/assets/img/logo-square.png"
          alt=""
          width={20}
          height={20}
          style={{ display: "block", borderRadius: 3 }}
        />
        <span style={{ fontWeight: 600 }}>Evaluation Cards</span>
        <span
          className="uppercase"
          style={{
            fontSize: 9,
            letterSpacing: "0.16em",
            color: "var(--fg-subtle)",
          }}
        >
          · EvalEval
        </span>
      </a>
      {children}
    </div>
  )
}
