import { ImageResponse } from "next/og"

import { OG_CONTENT_TYPE, OG_SIZE, ellipsize, resolveBrandLogoUrl } from "@/app/api/og/_shared"
import { getModelSummaryById } from "@/lib/data-backend"
import { routeIdFromSegments } from "@/lib/utils"

export const runtime = "nodejs"

/**
 * Dynamic OpenGraph image for a model page. Reaches into the same
 * DuckDB-backed model summary the route handler uses so the unfurled
 * card identifies the specific model rather than rendering the
 * generic site card. Co-located under /api/og/ rather than as an
 * `opengraph-image.tsx` sibling of the page because Next.js 15 rejects
 * metadata files inside catch-all (`[...id]`) folders.
 */
export async function GET(
  request: Request,
  context: { params: Promise<{ id: string | string[] }> },
) {
  const { id } = await context.params
  const routeId = routeIdFromSegments(id)

  let modelName = "Model"
  let developer: string | null = null
  let benchmarkCount: number | null = null

  try {
    const summary = await getModelSummaryById(routeId)
    if (summary) {
      modelName = summary.model_info?.name ?? modelName
      developer = summary.model_info?.developer ?? null
      const categories = summary.evaluations_by_tag ?? {}
      const seen = new Set<string>()
      let total = 0
      for (const items of Object.values(categories)) {
        for (const item of items ?? []) {
          total += 1
          const key = (item as { benchmark?: string; evaluation_id?: string }).benchmark
            ?? (item as { evaluation_id?: string }).evaluation_id
          if (key) seen.add(key)
        }
      }
      benchmarkCount = seen.size > 0 ? seen.size : total > 0 ? total : null
    }
  } catch {
    // Fall through to the generic card.
  }

  const logoUrl = resolveBrandLogoUrl(request)
  const displayName = ellipsize(modelName, 64)

  const response = new ImageResponse(
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
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={logoUrl}
            width={56}
            height={56}
            alt=""
            style={{ borderRadius: "4px" }}
          />
          <div style={{ fontSize: "26px", fontWeight: 700, letterSpacing: "-0.01em" }}>
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
            Model card
          </div>
        </div>

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "20px",
            flex: 1,
            justifyContent: "center",
            paddingTop: "8px",
          }}
        >
          <div
            style={{
              fontFamily: "monospace",
              fontSize: "16px",
              letterSpacing: "0.2em",
              textTransform: "uppercase",
              color: "#5bacd1",
              fontWeight: 600,
            }}
          >
            {developer ?? "Model"}
          </div>
          <div
            style={{
              fontSize: "88px",
              lineHeight: 1.02,
              letterSpacing: "-0.04em",
              fontWeight: 700,
              maxWidth: "1060px",
              wordBreak: "break-word",
            }}
          >
            {displayName}
          </div>
          {benchmarkCount != null && (
            <div style={{ fontSize: "26px", color: "#5c5a55", lineHeight: 1.4 }}>
              {`Reported on ${benchmarkCount.toLocaleString("en-US")} ${benchmarkCount === 1 ? "benchmark" : "benchmarks"}.`}
            </div>
          )}
        </div>

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
          <div style={{ color: "#9c9a95" }}>Evaluation Cards</div>
        </div>
      </div>
    ),
    OG_SIZE,
  )
  response.headers.set("content-type", OG_CONTENT_TYPE)
  response.headers.set("cache-control", "public, max-age=3600, s-maxage=86400")
  return response
}
