import { ImageResponse } from "next/og"

export const runtime = "edge"
export const alt = "Evaluation Cards — a reporting layer over evaluation infrastructure"
export const size = { width: 1200, height: 630 }
export const contentType = "image/png"

// Brand mark URL. `ImageResponse` fetches `<img src>` at render time,
// so it needs an absolute URL — prefer NEXT_PUBLIC_SITE_URL (set on
// the Space), else fall back to the canonical remote.
const LOGO_URL =
  (process.env.NEXT_PUBLIC_SITE_URL?.trim().replace(/\/+$/, "") ?? "") + "/logo-square.png"
const FALLBACK_LOGO_URL = "https://evalevalai.com/assets/img/logo-square.png"

export default function OpenGraphImage() {
  const logoUrl = LOGO_URL.startsWith("http") ? LOGO_URL : FALLBACK_LOGO_URL
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          background: "#faf9f6",
          color: "#1a1916",
          fontFamily: "Inter, sans-serif",
          padding: "72px",
        }}
      >
        {/* Brand row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "16px",
          }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={logoUrl}
            width={56}
            height={56}
            alt=""
            style={{ borderRadius: "4px" }}
          />
          <div
            style={{
              fontSize: "26px",
              fontWeight: 700,
              letterSpacing: "-0.01em",
            }}
          >
            Evaluation Cards
          </div>
          <div
            style={{
              fontFamily: "monospace",
              fontSize: "14px",
              letterSpacing: "0.2em",
              textTransform: "uppercase",
              color: "#9c9a95",
              paddingLeft: "20px",
              marginLeft: "8px",
              borderLeft: "1px solid #e8e6e1",
              display: "flex",
              alignItems: "center",
              height: "32px",
            }}
          >
            Beta · EvalEval
          </div>
        </div>

        {/* Headline + lede */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "26px",
            flex: 1,
            justifyContent: "center",
            paddingTop: "8px",
          }}
        >
          <div
            style={{
              fontSize: "76px",
              lineHeight: 1.05,
              letterSpacing: "-0.035em",
              fontWeight: 700,
              display: "flex",
              flexDirection: "column",
            }}
          >
            <div style={{ display: "flex" }}>
              <span>A reporting&nbsp;</span>
              <span style={{ fontStyle: "italic", color: "#5bacd1" }}>layer</span>
              <span>&nbsp;over</span>
            </div>
            <div>evaluation infrastructure.</div>
          </div>
          <div
            style={{
              fontSize: "24px",
              lineHeight: 1.5,
              color: "#5c5a55",
              maxWidth: "920px",
            }}
          >
            A collection of reported model–benchmark results, organized under a five-level
            rollout hierarchy and four interpretive signals.
          </div>
        </div>

        {/* Footer strip */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            paddingTop: "26px",
            borderTop: "1px solid #1a1916",
            fontFamily: "monospace",
            fontSize: "15px",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "#5c5a55",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
            <span style={{ color: "#1a1916", fontWeight: 600 }}>Reproducibility</span>
            <span style={{ color: "#9c9a95" }}>·</span>
            <span style={{ color: "#1a1916", fontWeight: 600 }}>Completeness</span>
            <span style={{ color: "#9c9a95" }}>·</span>
            <span style={{ color: "#1a1916", fontWeight: 600 }}>Provenance</span>
            <span style={{ color: "#9c9a95" }}>·</span>
            <span style={{ color: "#1a1916", fontWeight: 600 }}>Comparability</span>
          </div>
          <div style={{ color: "#9c9a95" }}>evalcards.evalevalai.com</div>
        </div>
      </div>
    ),
    {
      ...size,
    },
  )
}
