import knownIssuesData from "@/metadata/benchmark_known_issues.json"

export interface KnownIssue {
  title: string
  summary: string
  severity: "info" | "warning" | "critical"
  source_url?: string
  published?: string
}

const RAW_ISSUES = (knownIssuesData as { issues?: Record<string, KnownIssue[]> }).issues ?? {}

function normalizeKey(value: string): string {
  return value
    .toLowerCase()
    .trim()
    .replace(/[\s_\-/]+/g, " ")
    .replace(/\s+/g, " ")
}

const NORMALIZED_LOOKUP = new Map<string, KnownIssue[]>()
for (const [rawKey, issues] of Object.entries(RAW_ISSUES)) {
  if (!Array.isArray(issues) || issues.length === 0) continue
  NORMALIZED_LOOKUP.set(normalizeKey(rawKey), issues)
  // Also index a hyphenated variant since some benchmark keys use dashes
  NORMALIZED_LOOKUP.set(normalizeKey(rawKey).replace(/\s+/g, "-"), issues)
}

/**
 * Look up curated known issues for a benchmark by trying any of the supplied
 * names/keys (e.g. evaluation_name, composite_benchmark_key, family_key).
 * Returns the first matching list, or an empty array if nothing is recorded.
 */
export function getKnownIssues(...candidates: Array<string | undefined | null>): KnownIssue[] {
  for (const candidate of candidates) {
    if (!candidate) continue
    const key = normalizeKey(candidate)
    const direct = NORMALIZED_LOOKUP.get(key)
    if (direct) return direct
    // Try collapsed (no spaces/dashes) form too, since some sources mash names together
    const collapsed = key.replace(/\s+/g, "")
    for (const [registered, issues] of NORMALIZED_LOOKUP) {
      if (registered.replace(/\s+/g, "") === collapsed) return issues
    }
  }
  return []
}
