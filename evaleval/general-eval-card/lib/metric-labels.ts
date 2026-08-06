/**
 * Shared helpers for turning a leaderboard metric record into a short,
 * human-readable label. The upstream pipeline frequently leaves
 * display_name blank (e.g. inspect_evals/avg_full_score) or sets every
 * metric's display_name to a generic "Score", so naive label resolution
 * collapses distinct metrics into duplicate chips. These helpers walk
 * the fallback chain (display_name → metric_name → metric_id →
 * column_key tail) and humanise underscores.
 */

function compactizePath(value: string): string {
  const parts = value
    .split("/")
    .map((part) => part.trim())
    .filter(Boolean)
  return parts[parts.length - 1] ?? value
}

export function getMetricChipLabel(metric: {
  display_name?: string | null
  metric_name?: string | null
  metric_id?: string | null
  column_key?: string | null
}): string {
  const candidates = [
    metric.display_name,
    metric.metric_name,
    metric.metric_id,
    metric.column_key,
  ]
  for (const c of candidates) {
    if (c && String(c).trim()) {
      return compactizePath(String(c)).replace(/_/g, " ")
    }
  }
  return "Metric"
}
