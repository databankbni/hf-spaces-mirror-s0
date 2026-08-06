// model-resolution-rework — 301 redirects for changed model URLs.
//
// ~297 model routes change at the registry re-baseline (204 canonical_id
// flips root->leaf + 93 casing re-keys). Bookmarked / inbound links to the
// OLD route must 301 to the NEW one.
//
// WHY middleware and not `app/models/[...id]/route.ts`: a Route Handler
// (`route.ts`) cannot coexist with the existing `page.tsx` in the same App
// Router segment — Next.js treats that as a conflict. Middleware runs before
// routing, sees every `/models/*` request, and can issue a 301 with full
// control over the URL and query string. (Deviation from the playbook's
// suggested file path; same behaviour, correct Next.js mechanism.)
//
// CONTRACT (tested in tests/transformations/model-url-redirects.test.ts):
//   - 301 (permanent) so caches/search engines update.
//   - QUERY PARAMS PRESERVED across the redirect (e.g. ?version=...), so a
//     deep link to a specific variant survives.
//   - the model id round-trips through percent-encoding: the incoming path
//     segment is decoded by Next.js, we re-encode to the producer `route_id`
//     form (whole-id encoding, `/` -> %2F) to match the redirect-map keys.

import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

import { resolveModelRedirect } from "@/lib/model-url-redirects"

export const config = {
  // Only run on model detail routes. Static assets / api are untouched.
  matcher: ["/models/:path*"],
}

const MODELS_PREFIX = "/models/"

export function middleware(req: NextRequest): NextResponse | undefined {
  const { pathname } = req.nextUrl
  if (!pathname.startsWith(MODELS_PREFIX)) return undefined

  // Everything after `/models/`. Next.js has already percent-DECODED the
  // path, so `/models/anthropic%2Fclaude-3-haiku` arrives here as the
  // decoded `anthropic/claude-3-haiku`. Re-encode the whole id to the
  // producer `route_id` form to look up the map.
  const rawTail = pathname.slice(MODELS_PREFIX.length)
  if (!rawTail) return undefined

  const decoded = safeDecode(rawTail)
  const routeId = encodeURIComponent(decoded)

  const newRouteId = resolveModelRedirect(routeId)
  if (!newRouteId) return undefined

  // Build the target. encodeURIComponent gives the whole-id `%2F` form;
  // keep it as a single path segment under the [...id] catch-all so the
  // page resolves it exactly like a freshly-minted link.
  const target = req.nextUrl.clone()
  target.pathname = `${MODELS_PREFIX}${newRouteId}`
  // PRESERVE query params (e.g. ?version=20240620). `clone()` already copies
  // search; set it explicitly so intent is obvious and robust to refactors.
  target.search = req.nextUrl.search

  return NextResponse.redirect(target, 301)
}

function safeDecode(value: string): string {
  try {
    return decodeURIComponent(value)
  } catch {
    // Malformed percent-encoding — treat the raw value as already-decoded.
    return value
  }
}
