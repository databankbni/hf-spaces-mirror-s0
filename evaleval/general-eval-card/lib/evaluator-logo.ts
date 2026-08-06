/**
 * Org-logo helpers for the evaluator page.
 *
 * Logos + homepage URLs are sourced from the registry (canonical_orgs) and
 * delivered to the frontend via the organizations.json sidecar — see
 * lib/dashboard-data-client.fetchOrganizations(). The evaluator page looks an
 * org up by normalizeOrgKey(name); the mark is rendered through <OrgLogo/>,
 * which auto-squares + auto-sizes any aspect ratio and falls back to the
 * name-derived monogram when the registry has no logo for the org.
 */

/**
 * Monogram initials for the logo-less fallback. Drops common org-suffix noise
 * ("AI", "Institute", "Inc"…), takes the first letter of up to two significant
 * words, and falls back to the first two characters for single-word names.
 */
const STOP_WORDS = new Set([
  "ai",
  "the",
  "of",
  "for",
  "and",
  "institute",
  "inc",
  "labs",
  "lab",
  "research",
])

export function monogramFor(name: string): string {
  const words = name
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .split(/\s+/)
    .filter(Boolean)
  const significant = words.filter((w) => !STOP_WORDS.has(w.toLowerCase()))
  const pool = significant.length > 0 ? significant : words
  if (pool.length === 0) return "?"
  if (pool.length === 1) {
    return pool[0].slice(0, 2).toUpperCase()
  }
  return (pool[0][0] + pool[1][0]).toUpperCase()
}

/**
 * Deterministic warm hue for a monogram tile, derived from the name so the
 * same org always gets the same colour. Tuned to sit quietly against the warm
 * neutral palette (low saturation, mid lightness).
 */
export function monogramHue(name: string): number {
  let h = 0
  for (let i = 0; i < name.length; i++) {
    h = (h * 31 + name.charCodeAt(i)) % 360
  }
  return h
}

/**
 * Normalise an org/evaluator name to the key used by the organizations.json
 * sidecar. MUST stay in sync with the pipeline's `_normalize_org_key`
 * (eval_cards_backend_pipeline/.../sidecars.py) so the frontend's lookup keys
 * match the producer's. The evaluator page uses this to find an org's homepage
 * URL + logo from the sidecar map.
 */
export function normalizeOrgKey(name: string): string {
  return name.trim().toLowerCase().replace(/\s+/g, " ")
}
