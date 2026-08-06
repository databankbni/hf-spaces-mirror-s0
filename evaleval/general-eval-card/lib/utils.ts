import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Convert a backend route id (literal `%2F` slug form, e.g.
 * `openai%2Fgpt-4o`, `helm-capabilities%2Fmmlu-pro`) into the
 * human-readable path form (`openai/gpt-4o`) used in URLs.
 *
 * Pages mount via catch-all routes (`[...id]`) so multi-segment paths
 * resolve cleanly. The inverse — `params.id[]` → backend id form — is
 * `routeIdFromSegments`.
 */
export function routeIdToPath(id: string | null | undefined): string {
  if (!id) return ""
  return id.replace(/%2F/g, "/")
}

/**
 * Reconstruct the backend `%2F`-encoded id from a Next.js catch-all
 * params value. Accepts either the raw `string[]` from `useParams()`
 * or a pre-joined string for safety. Empty arrays produce "".
 */
export function routeIdFromSegments(value: string | string[] | undefined): string {
  if (value == null) return ""
  const joined = Array.isArray(value) ? value.join("/") : value
  return joined.replace(/\//g, "%2F")
}

/**
 * Build the backend `%2F`-encoded route id form from a plain canonical
 * model id (`org/name`). Matches the producer's `route_id` /
 * `model_route_id` encoding (RFC 3986 percent-encoding of the whole id),
 * so the result can be fed straight into `routeIdToPath` for a URL path.
 *
 * This is the model-resolution-rework replacement for the old
 * client-side family-route computation (since removed): the
 * group/leaf id is now server-provided (`model_group_id`), and we only
 * need to encode it for routing — never re-derive it.
 */
export function routeIdFromModelId(id: string | null | undefined): string {
  if (!id) return ""
  return encodeURIComponent(id.trim())
}

/**
 * Title-case a benchmark / family / eval label that arrives in slug or
 * snake-case form. Example inputs and outputs:
 *   `gdm_intercode_ctf` → `GDM Intercode CTF`
 *   `vals ai gpqa`      → `Vals AI GPQA`
 *   `mmlu-pro`          → `MMLU-Pro`
 *
 * Common AI-eval acronyms are upper-cased; everything else is title-cased.
 * No-op when the input already looks like prose (any character has its
 * canonical case position — i.e. there's at least one upper-case letter
 * mid-word) so we don't mangle "MMLU-Pro" or "RewardBench Chat".
 */
const BENCHMARK_NAME_ACRONYMS = new Set([
  "ai", "ml", "llm", "llms", "nlp", "rl", "qa", "vqa", "vlm", "mt", "cv",
  "api", "cli", "sql", "io", "ui", "ux",
  "gpt", "ctf", "cve", "gdm", "mmlu", "gpqa", "bbh", "hle", "gsm8k", "aime",
  "ifeval", "ifbench", "humaneval", "mbpp", "gaia", "scicode", "agentharm",
  "csqa", "boolq", "openbookqa", "narrativeqa", "naturalquestions", "imdb",
  "piqa", "triviaqa", "truthfulqa", "musr", "math", "mgsm", "mmmu", "medqa",
  "legalbench", "bbq",
])

export function humanizeBenchmarkName(value: string | null | undefined): string {
  if (!value) return ""
  let s = value.trim()
  try { s = decodeURIComponent(s) } catch {}
  // Already prose? Any non-leading uppercase letter implies it's
  // already been display-formatted — leave it alone.
  if (/[a-z][A-Z]/.test(s)) return s
  return s
    .split(/[_\-\s]+/)
    .filter(Boolean)
    .map((word) => {
      const lower = word.toLowerCase()
      if (BENCHMARK_NAME_ACRONYMS.has(lower)) return word.toUpperCase()
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
    })
    .join(" ")
}

/**
 * Render an `evaluation_id` for human eyes.
 *
 * Backend evaluation_ids are RFC 3986 percent-encoded so they're safe
 * as URL path segments — `wasp%2Fjudgebench-coding` for the (composite,
 * benchmark) pair `wasp/judgebench-coding`. The encoded form is fine for
 * routes and React keys, but reads as nonsense in research-view labels.
 *
 * `humanizeEvaluationId` decodes the slug and falls back to the input
 * when decoding fails (malformed sequences, etc.) so it's always safe
 * to drop in at a render site.
 */
export function humanizeEvaluationId(value: string | null | undefined): string {
  if (!value) return ""
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

/**
 * Format an evaluation timestamp as `YYYY-MM-DD` for table cells.
 *
 * Accepts the two shapes the backend emits:
 *   - ISO date-time strings (`"2026-04-29T00:00:00Z"`)
 *   - Unix-epoch numerics as strings (`"1777496278.157"`)
 *
 * Returns `"Unknown"` when the value is missing or unparseable. Lossy
 * by design — the `Updated` column shows the date only, not time.
 *
 * Day-precision timestamps are interpreted in UTC (`toISOString()`)
 * rather than the local zone so a `2026-04-29T00:00:00Z` value renders
 * as `2026-04-29` everywhere instead of slipping to `2026-04-28` west of
 * UTC.
 */
export function formatDateISO(ts: string | null | undefined): string {
  if (!ts || !String(ts).trim()) return "Unknown"
  const raw = String(ts)
  const numeric = Number(raw)
  const parsed =
    !Number.isNaN(numeric) && !raw.includes("-")
      ? new Date(numeric * 1000)
      : new Date(raw)
  if (Number.isNaN(parsed.getTime())) return "Unknown"
  return parsed.toISOString().slice(0, 10)
}
