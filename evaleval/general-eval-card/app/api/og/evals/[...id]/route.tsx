import { ImageResponse } from "next/og"

import { OG_CONTENT_TYPE, OG_SIZE, ellipsize, resolveBrandLogoUrl } from "@/app/api/og/_shared"
import { getEvalSummaryById } from "@/lib/data-backend"
import { routeIdFromSegments } from "@/lib/utils"

export const runtime = "nodejs"

function formatScore(value: number, unit: string | null): string {
  const isPercentish = !unit || /percent|proportion|accuracy|score|pass@|exact|f1|%/i.test(unit)
  if (isPercentish) {
    const v = Math.abs(value) <= 1 ? value * 100 : value
    return `${v.toFixed(1)}%`
  }
  return value.toFixed(3).replace(/0+$/g, "").replace(/\.$/, "")
}

/**
 * Dynamic OpenGraph image for an eval/benchmark page. Pulls the
 * canonical benchmark name, category, model count, and top result out
 * of the eval summary so the unfurl identifies the specific benchmark.
 */
export async function GET(
  request: Request,
  context: { params: Promise<{ id: string | string[] }> },
) {
  const { id } = await context.params
  const evalId = routeIdFromSegments(id)

  let evalName = "Benchmark"
  let category: string | null = null
  let modelsCount: number | null = null
  let topModelName: string | null = null
  let topScore: number | null = null
  let unit: string | null = null

  try {
    const summary = await getEvalSummaryById(evalId)
    if (summary) {
      evalName =
        summary.canonical_display_name ??
        summary.evaluation_name ??
        summary.composite_display_name ??
        evalName
      category = summary.derived_tags?.[0] ?? null
      modelsCount = summary.models_count ?? null
      topModelName = summary.best_model?.name ?? null
      topScore = summary.best_model?.score ?? null
      unit = summary.metric_config?.unit ?? null
    }
  } catch {
    // Fall through to the generic card.
  }

  const logoUrl = resolveBrandLogoUrl(request)
  const displayName = ellipsize(evalName, 64)

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
            Benchmark
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
          {category && (
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
              {category}
            </div>
          )}
          <div
            style={{
              fontSize: "82px",
              lineHeight: 1.02,
              letterSpacing: "-0.04em",
              fontWeight: 700,
              maxWidth: "1060px",
              wordBreak: "break-word",
            }}
          >
            {displayName}
          </div>
          {(modelsCount != null || topModelName) && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "8px",
                fontSize: "24px",
                color: "#5c5a55",
                lineHeight: 1.4,
              }}
            >
              {modelsCount != null && (
                <div>
                  {`${modelsCount.toLocaleString("en-US")} ${modelsCount === 1 ? "model evaluated" : "models evaluated"}`}
                </div>
              )}
              {topModelName && topScore != null && Number.isFinite(topScore) && (
                <div style={{ display: "flex", alignItems: "baseline", gap: "10px" }}>
                  <span>Top:</span>
                  <span style={{ color: "#1a1916", fontWeight: 600 }}>{topModelName}</span>
                  <span style={{ color: "#5bacd1", fontWeight: 600 }}>
                    {formatScore(topScore, unit)}
                  </span>
                </div>
              )}
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
