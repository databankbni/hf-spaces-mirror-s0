"use client"

import { useEffect, useState, type ReactNode } from "react"
import { AlertTriangle, ExternalLink, FlaskConical } from "lucide-react"
import { Term } from "@/components/term"
import { SignalTooltip } from "@/components/signals/signal-tooltip"
import type { ModelResultForBenchmark } from "@/lib/eval-processing"
import type { GenerationConfig, ScoreDetails } from "@/lib/benchmark-schema"

interface ResearcherReproducibilityCardProps {
  modelResult: ModelResultForBenchmark
  /**
   * Benchmark identifier used to pick the right per-eval row when fetching
   * enrichment from the model's full record. The eval-detail endpoint
   * synthesizes leaderboard rows without `generation_config`, so we top up
   * lazily on row expand from /api/eval-row-config.
   */
  benchmarkKey?: string
  evalName?: string
}

const KNOWN_DECODING_KEYS = ["temperature", "top_p", "top_k", "max_tokens", "seed", "reasoning"] as const

// Keys that belong to agentic eval setups, surfaced in their own group rather
// than dumped under "decoding" extras as raw JSON.
const KNOWN_AGENT_KEYS = [
  "agentic_eval_config",
  "max_attempts",
  "eval_limits",
  "eval_plan",
  "sandbox",
  "max_turns",
  "message_limit",
] as const

const KEY_LABEL: Record<string, string> = {
  temperature: "temperature",
  top_p: "top-p",
  top_k: "top-k",
  max_tokens: "max tokens",
  seed: "seed",
  reasoning: "reasoning mode",
  n: "samples per prompt",
  best_of: "best-of-N",
  num_samples: "samples per prompt",
  num_runs: "runs",
  n_shot: "n-shot",
  num_fewshot: "few-shot examples",
  fewshot: "few-shot examples",
  agentic_eval_config: "tools available",
  max_attempts: "max attempts",
  eval_limits: "eval limits",
  eval_plan: "eval plan",
  sandbox: "sandbox",
  max_turns: "max turns",
  message_limit: "message limit",
}

/**
 * Try to render a structured agentic config object as a short, readable
 * string. Falls back to null so the caller can use the generic formatter.
 */
function formatAgentValue(key: string, value: unknown): string | null {
  if (value == null) return null
  if (typeof value !== "object") return null

  if (key === "agentic_eval_config") {
    const tools = (value as { available_tools?: unknown }).available_tools
    if (Array.isArray(tools)) {
      const names = tools
        .map((t) => (t && typeof t === "object" ? (t as { name?: unknown }).name : null))
        .filter((n): n is string => typeof n === "string" && n.length > 0)
      if (names.length === 0) return "no tools"
      if (names.length <= 4) return `${names.length} tools: ${names.join(", ")}`
      return `${names.length} tools: ${names.slice(0, 4).join(", ")} +${names.length - 4}`
    }
  }

  if (key === "eval_limits") {
    const obj = value as Record<string, unknown>
    const parts: string[] = []
    for (const k of ["message_limit", "max_messages", "token_limit", "max_tokens"]) {
      if (typeof obj[k] === "number") parts.push(`${k.replace(/_/g, " ")}: ${obj[k]}`)
    }
    if (parts.length > 0) return parts.join(", ")
  }

  if (key === "eval_plan") {
    const name = (value as { name?: unknown }).name
    const steps = (value as { steps?: unknown }).steps
    if (typeof name === "string" && Array.isArray(steps)) return `${name} (${steps.length} step${steps.length === 1 ? "" : "s"})`
    if (typeof name === "string") return name
  }

  if (key === "sandbox") {
    const keys = Object.keys(value as Record<string, unknown>)
    if (keys.length === 0) return "default"
    return keys.join(", ")
  }

  return null
}

function pickFromAdditional(value: unknown, keys: string[]): unknown | undefined {
  if (!value || typeof value !== "object") return undefined
  const obj = value as Record<string, unknown>
  for (const k of keys) {
    if (obj[k] !== undefined && obj[k] !== null) return obj[k]
  }
  return undefined
}

/**
 * Renders any value as a short string for the parameter cards. Returns null
 * when the value is empty so the caller can render "Not disclosed" instead.
 */
function formatValue(value: unknown): string | null {
  if (value === undefined || value === null) return null
  if (typeof value === "boolean") return value ? "yes" : "no"
  if (typeof value === "number") return Number.isInteger(value) ? value.toString() : value.toFixed(3)
  if (typeof value === "string") {
    const trimmed = value.trim()
    return trimmed.length === 0 ? null : trimmed
  }
  try {
    return JSON.stringify(value)
  } catch {
    return null
  }
}

function ParamRow({
  label,
  value,
  termKey,
  hint,
}: {
  label: string
  value: ReactNode | null
  termKey?: string
  hint?: string
}) {
  const isMissing = value === null || value === undefined
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-dashed border-border/50 py-1.5 text-sm last:border-0">
      <span className="text-muted-foreground">
        {termKey ? <Term term={termKey}>{label}</Term> : label}
      </span>
      {isMissing ? (
        <SignalTooltip
          content={
            hint ??
            "This parameter wasn't reported by the source. Without it, the result may not be exactly reproducible."
          }
        >
          <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-700 dark:text-amber-300 cursor-help">
            <AlertTriangle className="h-3 w-3" /> Not disclosed
          </span>
        </SignalTooltip>
      ) : (
        <span className="font-medium tabular-nums">{value}</span>
      )}
    </div>
  )
}

interface FieldSpec {
  label: string
  value: string | null
  termKey?: string
  hint?: string
}

interface FieldGroup {
  title: string
  fields: FieldSpec[]
}

/**
 * Detailed reproducibility surface for researcher mode. Shown inside a
 * leaderboard row's expanded panel. Adaptive: when most fields aren't disclosed
 * (the common case today), it collapses to a compact "Limited disclosure"
 * summary showing only fields that *are* present, with a button to reveal the
 * full audit grid.
 */
export function ResearcherReproducibilityCard({
  modelResult,
  benchmarkKey,
  evalName,
}: ResearcherReproducibilityCardProps) {
  const [enrichedGen, setEnrichedGen] = useState<GenerationConfig | null>(null)
  const [enrichedScore, setEnrichedScore] = useState<ScoreDetails | null>(null)
  const [loading, setLoading] = useState(false)

  // Lazily top up generation_config / score_details from the model's full
  // record. The eval-detail leaderboard endpoint omits these fields; we only
  // pay the fetch cost when a researcher actually expands a row.
  useEffect(() => {
    const inlineGen = modelResult.result.generation_config
    const inlineScoreOk =
      modelResult.score_details.standard_error != null ||
      modelResult.score_details.confidence_interval != null ||
      modelResult.score_details.sample_size != null
    const hasInlineArgs =
      !!inlineGen &&
      typeof inlineGen === "object" &&
      "generation_args" in inlineGen &&
      Object.keys((inlineGen as { generation_args?: Record<string, unknown> }).generation_args ?? {}).length > 0
    if (hasInlineArgs && inlineScoreOk) return // nothing to fetch

    const modelId = modelResult.model_info.id
    if (!modelId) return

    const params = new URLSearchParams({ model_id: modelId })
    if (benchmarkKey) params.set("benchmark_key", benchmarkKey)
    if (evalName) params.set("eval_name", evalName)

    let cancelled = false
    setLoading(true)
    fetch(`/api/eval-row-config?${params.toString()}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (cancelled || !data) return
        if (data.generation_config) setEnrichedGen(data.generation_config as GenerationConfig)
        if (data.score_details) setEnrichedScore(data.score_details as ScoreDetails)
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [modelResult, benchmarkKey, evalName])

  const gen = modelResult.result.generation_config ?? enrichedGen ?? undefined
  const args = gen?.generation_args ?? {}
  const scoreDetails = {
    ...modelResult.score_details,
    sample_size: modelResult.score_details.sample_size ?? enrichedScore?.sample_size,
    standard_error: modelResult.score_details.standard_error ?? enrichedScore?.standard_error,
    confidence_interval:
      modelResult.score_details.confidence_interval ?? enrichedScore?.confidence_interval,
  }
  const additional =
    typeof gen?.additional_details === "object" && gen?.additional_details !== null
      ? (gen.additional_details as Record<string, unknown>)
      : null

  const argsKeys = Object.keys(args)
  const extraDecodingKeys = argsKeys.filter(
    (k) =>
      !KNOWN_DECODING_KEYS.includes(k as (typeof KNOWN_DECODING_KEYS)[number]) &&
      !KNOWN_AGENT_KEYS.includes(k as (typeof KNOWN_AGENT_KEYS)[number])
  )
  const agentKeysPresent = KNOWN_AGENT_KEYS.filter((k) => args[k] != null)
  const hasAgentSetup = agentKeysPresent.length > 0

  const shots = pickFromAdditional(additional, ["num_fewshot", "n_shot", "shots", "fewshot"])
  const samplesPerPrompt = pickFromAdditional(additional, ["n", "num_samples", "samples_per_prompt"]) ?? args["n"]
  const bestOf = pickFromAdditional(additional, ["best_of", "best_of_n"]) ?? args["best_of"]
  const numRuns = pickFromAdditional(additional, ["num_runs", "n_runs", "runs"])
  const scoringMethod = pickFromAdditional(additional, ["scoring", "scoring_method", "judge", "evaluator"])
  const evalLibrary = pickFromAdditional(additional, ["eval_library", "harness", "framework"])
  const evalLibraryVersion = pickFromAdditional(additional, ["eval_library_version", "harness_version"])
  const promptTemplate = gen?.prompt_template?.trim() || null

  const groups: FieldGroup[] = [
    {
      title: "Decoding",
      fields: [
        {
          label: "temperature",
          termKey: "temperature",
          value: formatValue(args.temperature),
          hint: "Temperature controls randomness. Without it, others can't recreate the same outputs.",
        },
        { label: "top-p", termKey: "top-p", value: formatValue(args.top_p) },
        { label: "top-k", termKey: "top-k", value: formatValue(args.top_k) },
        { label: "max tokens", value: formatValue(args.max_tokens) },
        { label: "seed", value: formatValue(args.seed) },
        ...extraDecodingKeys.map((k) => ({
          label: KEY_LABEL[k] ?? k.replace(/_/g, " "),
          value: formatValue(args[k]),
        })),
      ],
    },
    {
      title: "Sampling",
      fields: [
        {
          label: "few-shot examples",
          termKey: "few-shot",
          value: formatValue(shots),
          hint: "How many worked examples were included in the prompt before the question.",
        },
        {
          label: "samples per prompt",
          value: formatValue(samplesPerPrompt),
          hint: "Number of completions generated per question.",
        },
        {
          label: "best-of-N",
          termKey: "best-of-n",
          value: formatValue(bestOf),
          hint: "Whether the score reflects the best of multiple attempts (inflates results vs. single-attempt).",
        },
        {
          label: "runs averaged",
          value: formatValue(numRuns),
          hint: "How many evaluation runs were averaged to produce the reported number.",
        },
        {
          label: "test instances",
          value: formatValue(scoreDetails.sample_size),
          hint: "Number of items in the test set the model was scored on.",
        },
      ],
    },
    ...(hasAgentSetup
      ? [
          {
            title: "Agent setup",
            fields: agentKeysPresent.map((k) => ({
              label: KEY_LABEL[k] ?? k.replace(/_/g, " "),
              value: formatAgentValue(k, args[k]) ?? formatValue(args[k]),
              hint:
                k === "agentic_eval_config"
                  ? "Tools the agent could call during the run."
                  : k === "max_attempts"
                    ? "Maximum independent attempts the agent gets per task."
                    : k === "eval_limits"
                      ? "Hard caps the harness enforced on the run (messages, tokens, etc.)."
                      : k === "eval_plan"
                        ? "Solver/plan the harness used to drive the agent."
                        : k === "sandbox"
                          ? "Environment in which the agent ran (e.g. docker, local)."
                          : undefined,
            })),
          } as FieldGroup,
        ]
      : []),
    {
      title: "Scoring & uncertainty",
      fields: [
        {
          label: "scoring method",
          value: formatValue(scoringMethod),
          hint: "Exact match, LLM-as-judge, human grading, etc. Determines what 'correct' means.",
        },
        { label: "standard error", value: formatValue(scoreDetails.standard_error) },
        {
          label: "confidence interval",
          // The producer sometimes ships the wrapping object with all
          // three inner fields null (e.g. when only standard_error was
          // reported). Stringifying those produces "null–null (null%)";
          // collapse to "Not disclosed" instead.
          value: (() => {
            const ci = scoreDetails.confidence_interval
            if (!ci) return null
            const lower = formatValue(ci.lower)
            const upper = formatValue(ci.upper)
            if (lower === null || upper === null) return null
            const level = formatValue(ci.confidence_level)
            return level !== null
              ? `${lower}–${upper} (${level}%)`
              : `${lower}–${upper}`
          })(),
        },
        { label: "eval library", value: formatValue(evalLibrary) },
        { label: "library version", value: formatValue(evalLibraryVersion) },
      ],
    },
  ]

  // Mirror the signal-strip's required-fields allowlist (see
  // BenchmarkSignalsStrip · BASE_REQUIRED_FIELDS / AGENTIC_REQUIRED_FIELDS).
  // The signal scores reproducibility on temperature + max_tokens only
  // (plus eval_plan + eval_limits when agentic), so the per-row dropdown
  // showing all 15 fields was confusing — readers saw "0/15 disclosed"
  // here but a different ratio in the strip above. Restrict this surface
  // to the same labels so the two views agree.
  //
  // TODO(repro-allowlist): expand both views together once the corpus
  // populates more fields reliably.
  const requiredFieldLabels = new Set<string>(["temperature", "max tokens"])
  if (hasAgentSetup) {
    requiredFieldLabels.add("eval plan")
    requiredFieldLabels.add("eval limits")
  }
  const filteredGroups: FieldGroup[] = groups
    .map((g) => ({
      ...g,
      fields: g.fields.filter((f) => requiredFieldLabels.has(f.label)),
    }))
    .filter((g) => g.fields.length > 0)

  const totalFields = filteredGroups.reduce((n, g) => n + g.fields.length, 0)
  const disclosedFields = filteredGroups.reduce(
    (n, g) => n + g.fields.filter((f) => f.value !== null).length,
    0
  )
  const disclosureRatio = totalFields > 0 ? disclosedFields / totalFields : 0
  const disclosedGroups = filteredGroups
    .map((g) => ({ ...g, fields: g.fields.filter((f) => f.value !== null) }))
    .filter((g) => g.fields.length > 0)

  // If fewer than ~30% of fields are disclosed (and at least one is missing),
  // start in compact mode so the card isn't a wall of "Not disclosed".
  const shouldStartCompact = disclosureRatio < 0.3 && disclosedFields < totalFields
  const [showAll, setShowAll] = useState(!shouldStartCompact)
  const isCompact = shouldStartCompact && !showAll

  return (
    <section
      style={{
        padding: 16,
        border: "1px solid var(--border-soft)",
        background: "var(--bg)",
      }}
    >
      <header className="mb-3 flex items-start justify-between gap-3">
        <div className="flex items-start gap-2 min-w-0">
          <FlaskConical className="mt-0.5 h-4 w-4 shrink-0" style={{ color: "var(--fg-muted)" }} />
          <div className="min-w-0">
            <div
              className="font-mono uppercase mb-1"
              style={{ fontSize: 10, letterSpacing: "0.14em", color: "var(--fg-subtle)" }}
            >
              Reproducibility
            </div>
            <div className="text-[12px]" style={{ color: "var(--fg-muted)" }}>
              {isCompact
                ? disclosedFields === 0
                  ? "How this score was produced wasn't disclosed by the source."
                  : "Most reproducibility fields aren't documented by the source."
                : "Everything someone would need to re-run this evaluation. Missing fields are flagged."}
            </div>
          </div>
        </div>
        <span
          className="shrink-0 font-mono tabular-nums"
          style={{
            fontSize: 10,
            padding: "3px 8px",
            letterSpacing: "0.06em",
            border: "1px solid var(--border-soft)",
            background: "var(--bg-warm)",
            color: "var(--fg-muted)",
            textTransform: "uppercase",
          }}
        >
          {loading ? "loading…" : `${disclosedFields}/${totalFields} disclosed`}
        </span>
      </header>

      {isCompact ? (
        disclosedGroups.length > 0 ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {disclosedGroups.map((g) => (
              <div key={g.title}>
                <div
                  className="mb-2 font-mono uppercase"
                  style={{ fontSize: 10, letterSpacing: "0.14em", color: "var(--fg-subtle)" }}
                >
                  {g.title}
                </div>
                {g.fields.map((f) => (
                  <ParamRow key={f.label} label={f.label} termKey={f.termKey} value={f.value} hint={f.hint} />
                ))}
              </div>
            ))}
          </div>
        ) : null
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          {filteredGroups.map((g) => (
            <div key={g.title}>
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                {g.title}
              </div>
              {g.fields.map((f) => (
                <ParamRow key={f.label} label={f.label} termKey={f.termKey} value={f.value} hint={f.hint} />
              ))}
            </div>
          ))}
        </div>
      )}

      {shouldStartCompact && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="mt-3 inline-flex items-center font-mono uppercase underline-offset-4 hover:underline"
          style={{ fontSize: 10, letterSpacing: "0.12em", color: "var(--accent)" }}
        >
          {showAll
            ? "Hide undisclosed fields"
            : `Show all ${totalFields} checked fields`}
        </button>
      )}

      {/* Prompt-template block hidden until the corpus reliably reports
          it; see TODO(repro-allowlist) above. The signal score doesn't
          consider prompt_template either, so showing it here would
          re-introduce the disagreement we just fixed. */}

      {modelResult.source_metadata.source_url && (
        <div className="mt-3">
          <a
            href={modelResult.source_metadata.source_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 font-mono uppercase underline-offset-4 hover:underline"
            style={{ fontSize: 10, letterSpacing: "0.12em", color: "var(--accent)" }}
          >
            View original source <ExternalLink className="h-3 w-3" />
          </a>
        </div>
      )}
    </section>
  )
}
