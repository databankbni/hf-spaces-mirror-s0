/**
 * Shared constants for the dual-handle parameter range picker used to filter
 * leaderboards by model size. The bucket list is fine-grained enough that
 * users can land on a meaningful midpoint, but the visible tick labels are a
 * smaller subset matching the design (1B / 8B / 12B / 32B / 128B / >500B).
 */
export const PARAM_RANGE_VALUES = [
  1, 2, 3, 4, 6, 8, 10, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 500,
] as const

export const PARAM_RANGE_MAX_INDEX = PARAM_RANGE_VALUES.length - 1

/** Tick labels rendered above the rail. The `step` field is the index into
 *  `PARAM_RANGE_VALUES` at which the label sits — used to position it. */
export const PARAM_RANGE_MARKERS = [
  { label: "< 1B", step: 0 },
  { label: "8B", step: PARAM_RANGE_VALUES.indexOf(8) },
  { label: "12B", step: PARAM_RANGE_VALUES.indexOf(12) },
  { label: "32B", step: PARAM_RANGE_VALUES.indexOf(32) },
  { label: "128B", step: PARAM_RANGE_VALUES.indexOf(128) },
  { label: "> 500B", step: PARAM_RANGE_MAX_INDEX },
] as const

export function formatParamBoundLabel(step: number, bound: "min" | "max"): string {
  if (bound === "min" && step <= 0) return "< 1B"
  if (bound === "max" && step >= PARAM_RANGE_MAX_INDEX) return "> 500B"
  const value = PARAM_RANGE_VALUES[step]
  return value != null ? `${value}B` : "—"
}

/** Converts a slider step to a numeric param-billions filter, or null if the
 *  bound is at the open end (no filter applies). */
export function paramStepToNumeric(step: number, bound: "min" | "max"): number | null {
  if (bound === "min" && step <= 0) return null
  if (bound === "max" && step >= PARAM_RANGE_MAX_INDEX) return null
  return PARAM_RANGE_VALUES[step] ?? null
}

/** Best-effort extraction of `<X>B` parameter counts from a free-text field
 *  (typically a model name like "Llama-3.1 70B Instruct"). Returns null if no
 *  size token is present. Shared so all leaderboards detect parameters in the
 *  same way and the slider visibility is consistent. */
export function parseParamsBillionsFromText(value: string | null | undefined): number | null {
  if (!value) return null
  const normalized = value.trim().toLowerCase()
  if (!normalized) return null
  const compact = normalized.replace(/,/g, "")
  const tokenMatch = compact.match(
    /(\d+(?:\.\d+)?)\s*(trillion|tn|t|billion|bn|b|million|mn|m|thousand|k)\b/,
  )
  if (tokenMatch) {
    const amount = Number.parseFloat(tokenMatch[1])
    if (!Number.isFinite(amount)) return null
    const unit = tokenMatch[2]
    if (unit === "trillion" || unit === "tn" || unit === "t") return amount * 1000
    if (unit === "billion" || unit === "bn" || unit === "b") return amount
    if (unit === "million" || unit === "mn" || unit === "m") return amount / 1000
    if (unit === "thousand" || unit === "k") return amount / 1_000_000
  }
  const numeric = Number.parseFloat(compact)
  return Number.isFinite(numeric) ? numeric : null
}

export function parseParamsBillionsFromModelName(modelName: string | null | undefined): number | null {
  if (!modelName) return null
  const sizeTokens = Array.from(modelName.matchAll(/\b(\d+(?:\.\d+)?)\s*([tmbk])\b/gi))
  if (sizeTokens.length === 0) return null
  const lastToken = sizeTokens[sizeTokens.length - 1]
  const numericValue = Number.parseFloat(lastToken[1])
  if (!Number.isFinite(numericValue)) return null
  const unit = lastToken[2].toLowerCase()
  if (unit === "t") return numericValue * 1000
  if (unit === "b") return numericValue
  if (unit === "m") return numericValue / 1000
  if (unit === "k") return numericValue / 1_000_000
  return null
}
