import type { DifferingSetupField, ReportingCompleteness } from "@/lib/backend-artifacts"

const FIELD_PREFIXES = [
  "autobenchmarkcard.",
  "eee_eval.",
  "evalcards.",
]

const TOKEN_OVERRIDES: Record<string, string> = {
  api: "API",
  ai: "AI",
  eee: "EEE",
  hf: "HF",
  id: "ID",
  llm: "LLM",
  url: "URL",
}

function titleCaseSegment(segment: string) {
  return segment
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((token) => TOKEN_OVERRIDES[token.toLowerCase()] ?? `${token.charAt(0).toUpperCase()}${token.slice(1).toLowerCase()}`)
    .join(" ")
}

export function formatPercent(value: number | null | undefined, digits = 0) {
  if (value == null || !Number.isFinite(value)) {
    return "N/A"
  }

  return `${(value * 100).toFixed(digits)}%`
}

export function formatSignalNumber(value: number | null | undefined, digits = 3) {
  if (value == null || !Number.isFinite(value)) {
    return "N/A"
  }

  if (Math.abs(value) >= 100) {
    return value.toFixed(1).replace(/\.0$/, "")
  }

  return value.toFixed(digits).replace(/0+$/, "").replace(/\.$/, "")
}

export function formatFieldLabel(path: string) {
  let next = path
  for (const prefix of FIELD_PREFIXES) {
    if (next.startsWith(prefix)) {
      next = next.slice(prefix.length)
      break
    }
  }

  return next
    .split(".")
    .filter(Boolean)
    .map(titleCaseSegment)
    .join(" / ")
}

export function formatMissingField(field: string) {
  return titleCaseSegment(field)
}

export function formatSignalValue(value: unknown) {
  if (value == null) {
    return "(unspecified)"
  }

  if (typeof value === "string") {
    return value
  }

  if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint") {
    return String(value)
  }

  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

export function formatDifferingFields(fields: DifferingSetupField[], limit = 2) {
  if (fields.length === 0) {
    return "setup fields"
  }

  const labels = fields.slice(0, limit).map((item) => formatMissingField(item.field))
  const remainder = fields.length - labels.length
  return remainder > 0 ? `${labels.join(", ")} +${remainder}` : labels.join(", ")
}

export function getCompletenessPopulatedCount(completeness: ReportingCompleteness) {
  if (completeness.field_scores.length === 0) {
    return Math.round(completeness.completeness_score * completeness.total_fields_evaluated)
  }

  return Math.round(
    completeness.field_scores.reduce((sum, field) => sum + field.score, 0)
  )
}
