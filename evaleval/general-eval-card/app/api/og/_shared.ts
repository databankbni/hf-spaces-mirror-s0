/**
 * Helpers shared between the dynamic OpenGraph image routes
 * (/api/og/models/[...id] and /api/og/evals/[...id]).  The route
 * handlers run on the node runtime because they query the same
 * DuckDB backend the rest of the app uses; this file just collects
 * the common chrome (size, content-type, brand mark URL resolution)
 * so the per-entity handlers can focus on the entity content.
 */

export const OG_SIZE = { width: 1200, height: 630 } as const
export const OG_CONTENT_TYPE = "image/png"

/**
 * Absolute URL for the brand-mark image used inside the generated card.
 * `ImageResponse`'s `<img src="…" />` needs a fetchable URL because the
 * renderer worker downloads the bytes at render time. In production the
 * Space hosts the file at `<origin>/logo-square.png`; for local dev we
 * fall back to localhost so headless preview hits something real.
 */
export function resolveBrandLogoUrl(request: Request): string {
  const fromEnv = process.env.NEXT_PUBLIC_SITE_URL?.trim().replace(/\/+$/, "")
  const origin = fromEnv || new URL(request.url).origin
  return `${origin}/logo-square.png`
}

/**
 * Truncate a long display name so it doesn't overflow the 1200×630 card
 * frame. Adds an ellipsis when truncated.
 */
export function ellipsize(value: string, max: number): string {
  if (value.length <= max) return value
  return `${value.slice(0, max - 1).trimEnd()}…`
}
