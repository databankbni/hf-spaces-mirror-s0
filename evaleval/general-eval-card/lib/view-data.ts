import "server-only"

import fs from "node:fs"
import path from "node:path"
import { getConnection } from "@/lib/duckdb"
import { fetchHeadline } from "@/lib/sidecars"
import {
  type BenchmarkCard,
  type BenchmarkEvaluation,
  type EvaluationCardData,
  type EvaluationResult,
  type GenerationConfig,
  type MetricConfig,
  type ModelInfo,
  type ModelEvaluationSummary,
  type ModelVariantSummary,
  type ScoreDetails,
  type SourceData,
  type SourceMetadata,
} from "@/lib/benchmark-schema"
import type { DeveloperListEntry, RowAnnotations } from "@/lib/backend-artifacts"
import type {
  BenchmarkEvalListItem,
  BenchmarkEvalSummary,
  ModelResultForBenchmark,
} from "@/lib/eval-processing"
import { dedupeLeaderboardRowsByModelIdentity } from "@/lib/eval-processing"

type Row = Record<string, any>

let readRowsSequence = 0
let readRowsQueue: Promise<unknown> = Promise.resolve()

const MODEL_CARD_COLUMNS = `
  id, model_key, route_id, model_name, model_id, canonical_model_name, developer,
  evaluations_count, benchmarks_count, variant_count,
  derived_tags AS tags, tag_stats, latest_timestamp,
  evaluator_count, evaluator_names, source_type_count, source_types,
  evidence_count, missing_generation_config_count,
  third_party_eval_count, independent_verification_ratio,
  reproducibility_status, eval_libraries, latest_source_name,
  params_billions, benchmark_names, score_summary,
  reproducibility_summary, provenance_summary, comparability_summary,
  top_scores, source_urls, detail_urls,
  model_url, release_date,
  architecture, params, inference_engine, inference_platform
`

// The composite/family/slice taxonomy replaced the legacy
// `composite_benchmark_key` /
// `composite_benchmark_name` columns with `composite_slug` /
// `composite_display_name`. The `family_id` / `family_display_name` /
// `is_slice` columns are the canonical identity surface; we still
// alias the composite_* legacy names for backward compat with
// consumers that haven't migrated yet. Mapping:
//   composite_benchmark_key/name → composite_slug/display_name
//     (the leaderboard, e.g. "wasp"/"WASP" — what the eval-detail
//     "Composite" label shows)
const EVAL_LIST_COLUMNS = `
  evaluation_id, evaluation_name, canonical_display_name,
  benchmark_id,
  composite_slug, composite_display_name,
  family_id, family_display_name, is_slice,
  parent_benchmark_id,
  composite_slug AS composite_benchmark_key,
  composite_display_name AS composite_benchmark_name,
  family_display_name AS benchmark_family_name,
  derived_tags,
  CAST(to_json(metric_config) AS VARCHAR) AS metric_config,
  models_count, evaluator_names, verified_evaluator_names, source_types,
  latest_source_name, third_party_ratio,
  missing_generation_config_count, best_model, worst_model,
  avg_score, avg_score_norm, has_card, CAST(to_json(benchmark_card) AS VARCHAR) AS benchmark_card,
  is_aggregated, CAST(to_json(aggregate_sources) AS VARCHAR) AS aggregate_sources, CAST(to_json(tags) AS VARCHAR) AS tags,
  metrics_count, metric_names, CAST(to_json(instance_data) AS VARCHAR) AS instance_data, top_score,
  subtasks_count, is_summary_score,
  CAST(to_json(root_metrics) AS VARCHAR) AS root_metrics,
  CAST(to_json(subtasks) AS VARCHAR) AS subtasks,
  CAST(to_json(leaderboard_metrics) AS VARCHAR) AS leaderboard_metrics,
  CAST(to_json(reproducibility_summary) AS VARCHAR) AS reproducibility_summary,
  CAST(to_json(provenance_summary) AS VARCHAR) AS provenance_summary,
  CAST(to_json(comparability_summary) AS VARCHAR) AS comparability_summary,
  CAST(to_json(source_data) AS VARCHAR) AS source_data
`

// The deployed Space returns 500s ("Invalid Error: don't know what
// type:") on every eval-results / model-summary query because the
// DuckDB Node binding on linux-x64 can't materialise certain complex
// column types in the upstream parquet (nested JSON inside
// structs, MAP, and STRUCT[]). Wrap every non-primitive column with
// `to_json(...)` so the binding only ever sees VARCHAR per row;
// `parseMaybeJson` undoes the wrap in JS before downstream code
// reads the shapes.
const MODEL_CELL_JOIN_COLUMNS = `
  r.evaluation_id,
  r.metric_summary_id,
  r.benchmark_id,
  r.metric_id,
  r.model_key,
  CAST(to_json(r.model_info) AS VARCHAR) AS model_info,
  r.metric_display_name,
  r.metric_unit,
  r.lower_is_better,
  CAST(to_json(r.derived_tags) AS VARCHAR) AS derived_tags,
  r.score,
  CAST(to_json(r.score_details) AS VARCHAR) AS score_details,
  CAST(r.evaluation_timestamp AS VARCHAR) AS evaluation_timestamp,
  CAST(to_json(r.generation_config) AS VARCHAR) AS generation_config,
  CAST(to_json(r.source_metadata) AS VARCHAR) AS source_metadata,
  CAST(to_json(r.source_data) AS VARCHAR) AS source_data,
  CAST(to_json(r.eval_library) AS VARCHAR) AS eval_library,
  CAST(to_json(r.evalcards_annotations) AS VARCHAR) AS evalcards_annotations,
  r.is_multi_source,
  r.first_party_only,
  r.coverage_cell,
  r.completeness_score,
  r.instance_file_path,
  r.is_verified_evaluator,
  e.evaluation_name AS eval_evaluation_name,
  e.canonical_display_name AS eval_canonical_display_name,
  e.family_id AS eval_family_id,
  e.family_display_name AS eval_family_display_name,
  e.is_slice AS eval_is_slice,
  e.parent_benchmark_id AS eval_parent_benchmark_id,
  e.composite_display_name AS eval_composite_benchmark_name,
  CAST(to_json(e.derived_tags) AS VARCHAR) AS eval_derived_tags,
  CAST(to_json(e.metric_config) AS VARCHAR) AS eval_metric_config,
  CAST(to_json(e.source_data) AS VARCHAR) AS eval_source_data,
  e.is_summary_score AS eval_is_summary_score
`

// parent_benchmark_display_name is additive (2026-06 producer): the actual
// display name of a slice row's parent benchmark, NULL for non-slice rows.
// Distinct from composite_display_name, which for cross-benchmark suites is
// the SUITE label. Older snapshots don't carry the column, and a missing
// column binder-errors the whole query, so callers probe `evalsViewHas
// ParentDisplayName()` and splice in a NULL alias when absent.
function evalListColumns(hasParentDisplayName: boolean) {
  return `${EVAL_LIST_COLUMNS},
  ${hasParentDisplayName
    ? "parent_benchmark_display_name"
    : "CAST(NULL AS VARCHAR) AS parent_benchmark_display_name"}`
}

function modelCellJoinColumns(hasParentDisplayName: boolean) {
  return `${MODEL_CELL_JOIN_COLUMNS},
  ${hasParentDisplayName
    ? "e.parent_benchmark_display_name"
    : "CAST(NULL AS VARCHAR)"} AS eval_parent_benchmark_display_name`
}

const EVAL_CELL_JOIN_COLUMNS = `
  r.evaluation_id,
  r.metric_summary_id,
  r.benchmark_id,
  r.metric_id,
  r.model_key,
  r.model_route_id,
  CAST(to_json(r.model_info) AS VARCHAR) AS model_info,
  r.metric_display_name,
  r.metric_unit,
  r.lower_is_better,
  CAST(to_json(r.derived_tags) AS VARCHAR) AS derived_tags,
  r.score,
  CAST(to_json(r.score_details) AS VARCHAR) AS score_details,
  CAST(r.evaluation_timestamp AS VARCHAR) AS evaluation_timestamp,
  CAST(to_json(r.generation_config) AS VARCHAR) AS generation_config,
  CAST(to_json(r.source_metadata) AS VARCHAR) AS source_metadata,
  CAST(to_json(r.source_data) AS VARCHAR) AS source_data,
  r.source_record_url,
  r.eee_record_url,
  CAST(to_json(r.eval_library) AS VARCHAR) AS eval_library,
  CAST(to_json(r.aggregate_components) AS VARCHAR) AS aggregate_components,
  CAST(to_json(r.evalcards_annotations) AS VARCHAR) AS evalcards_annotations,
  r.is_multi_source,
  r.first_party_only,
  r.coverage_cell,
  r.completeness_score,
  r.instance_file_path,
  r.is_verified_evaluator,
  e.evaluation_name AS eval_evaluation_name,
  e.canonical_display_name AS eval_canonical_display_name,
  e.family_id AS eval_family_id,
  e.family_display_name AS eval_family_display_name,
  e.is_slice AS eval_is_slice,
  e.parent_benchmark_id AS eval_parent_benchmark_id,
  e.composite_display_name AS eval_composite_benchmark_name,
  CAST(to_json(e.derived_tags) AS VARCHAR) AS eval_derived_tags,
  CAST(to_json(e.metric_config) AS VARCHAR) AS eval_metric_config,
  CAST(to_json(e.source_data) AS VARCHAR) AS eval_source_data,
  e.is_summary_score AS eval_is_summary_score
`

// Matches an ASCII signed integer (no decimals, no leading zeros aside from
// "0" itself). Used to detect BIGINT columns that `getRowObjectsJson()`
// serialises as strings — the JSON form does this inconsistently per
// value (numbers within int32 range stay numeric, larger ones become
// strings), so consumers see a mixed-type field and `sum + value`
// silently concatenates instead of adding.
const BIGINT_STRING = /^-?(?:0|[1-9]\d*)$/

function queryLogSnippet(sql: string) {
  return sql.replace(/\s+/g, " ").slice(0, 1200)
}

function shouldLogQuery(sql: string) {
  return sql.includes("eval_results_view")
}

function normalizeDuckDBValue(value: unknown): unknown {
  if (typeof value === "bigint") {
    return Number(value)
  }

  // Recover BIGINT-encoded numeric strings back to numbers, but only
  // when the value round-trips safely (so 64-bit ints that exceed
  // Number.MAX_SAFE_INTEGER stay as strings instead of silently losing
  // precision).
  if (typeof value === "string" && BIGINT_STRING.test(value)) {
    const numeric = Number(value)
    if (Number.isSafeInteger(numeric)) return numeric
  }

  if (value instanceof Date) {
    return value.toISOString()
  }

  if (value instanceof Map) {
    return Object.fromEntries(
      Array.from(value.entries()).map(([key, mapValue]) => [String(key), normalizeDuckDBValue(mapValue)])
    )
  }

  if (Array.isArray(value)) {
    return value.map(normalizeDuckDBValue)
  }

  if (value && typeof value === "object") {
    const duckValue = value as {
      constructor?: { name?: string }
      entries?: unknown
      items?: unknown
      scale?: unknown
      value?: unknown
      toString?: () => string
    }
    const constructorName = duckValue.constructor?.name ?? ""

    if (constructorName === "DuckDBStructValue" && duckValue.entries && typeof duckValue.entries === "object") {
      return normalizeDuckDBValue(duckValue.entries)
    }

    if (
      (constructorName === "DuckDBListValue" || constructorName === "DuckDBArrayValue") &&
      Array.isArray(duckValue.items)
    ) {
      return duckValue.items.map(normalizeDuckDBValue)
    }

    if (constructorName === "DuckDBMapValue" && Array.isArray(duckValue.entries)) {
      return Object.fromEntries(
        duckValue.entries.map((entry) => {
          const pair = entry as { key: unknown; value: unknown }
          return [String(pair.key), normalizeDuckDBValue(pair.value)]
        })
      )
    }

    if (constructorName === "DuckDBDecimalValue" && typeof duckValue.toString === "function") {
      return Number(duckValue.toString())
    }

    if (constructorName.startsWith("DuckDB") && typeof duckValue.toString === "function") {
      return duckValue.toString()
    }

    return Object.fromEntries(
      Object.entries(value).map(([key, objectValue]) => [key, normalizeDuckDBValue(objectValue)])
    )
  }

  return value
}

interface ReadRowsOptions {
  contextLabel?: string
}

async function readRows<T = Row>(
  sql: string,
  params: unknown[] = [],
  options: ReadRowsOptions = {},
): Promise<T[]> {
  const runQuery = async () => {
    const connection = await getConnection()
    const queryId = ++readRowsSequence
    const logThisQuery = shouldLogQuery(sql)
    const sqlSnippet = queryLogSnippet(sql)
    const contextSuffix = options.contextLabel ? ` [${options.contextLabel}]` : ""

    if (logThisQuery) {
      console.warn(
        `[view-data] query#${queryId}${contextSuffix} start params=${params.length} — SQL: ${sqlSnippet}`
      )
    }

    // HF Spaces runs a single shared DuckDB connection. Serialising
    // runAndRead/readAll prevents overlapping readers on that connection,
    // which can otherwise trip linux-only binding failures during model/eval
    // detail loads.
    let reader
    try {
      reader = params.length > 0
        ? await connection.runAndRead(sql, params as any[])
        : await connection.runAndRead(sql)

      if (logThisQuery) {
        let columnSchema = "<unavailable>"
        try {
          columnSchema = JSON.stringify(reader.columnNameAndTypeObjectsJson())
        } catch (introspectErr) {
          columnSchema = `<introspect-failed: ${
            introspectErr instanceof Error ? introspectErr.message : String(introspectErr)
          }>`
        }

        console.warn(
          `[view-data] query#${queryId}${contextSuffix} runAndRead ok columnCount=${reader.columnCount} ` +
            `columns=${columnSchema}`
        )
      }
    } catch (err) {
      const msg = err instanceof Error ? `${err.name}: ${err.message}` : String(err)
      console.error(`[view-data] query#${queryId}${contextSuffix} runAndRead failed (${msg}) — SQL: ${sqlSnippet}`)
      throw err
    }

    try {
      await reader.readAll()
      const rows = reader.getRowObjectsJson().map((row) => normalizeDuckDBValue(row) as T)

      if (logThisQuery) {
        console.warn(`[view-data] query#${queryId}${contextSuffix} readAll ok rows=${rows.length}`)
      }

      return rows
    } catch (err) {
      const msg = err instanceof Error ? `${err.name}: ${err.message}` : String(err)
      let columnSchema: string = "<unavailable>"
      try {
        columnSchema = JSON.stringify(reader.columnNameAndTypeObjectsJson())
      } catch (introspectErr) {
        columnSchema = `<introspect-failed: ${
          introspectErr instanceof Error ? introspectErr.message : String(introspectErr)
        }>`
      }
      console.error(
        `[view-data] query#${queryId}${contextSuffix} readAll/getRows failed (${msg}) — columnCount=${reader.columnCount} ` +
          `columns=${columnSchema} — SQL: ${sqlSnippet}`
      )
      throw err
    }
  }

  const scheduled = readRowsQueue.then(runQuery, runQuery)
  readRowsQueue = scheduled.then(() => undefined, () => undefined)
  return scheduled
}

function asNumber(value: unknown, fallback = 0) {
  if (typeof value === "number" && Number.isFinite(value)) return value
  if (typeof value === "bigint") return Number(value)
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return fallback
}

function optionalNumber(value: unknown) {
  if (value == null) return undefined
  const parsed = asNumber(value, Number.NaN)
  return Number.isFinite(parsed) ? parsed : undefined
}

function asString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback
}

function optionalString(value: unknown) {
  return typeof value === "string" && value.length > 0 ? value : undefined
}

// Some parquet columns ship JSON-typed fields nested inside structs
// that the DuckDB Node binding can't materialise (crashes the entire
// query with "don't know what type:"). For those columns the SELECT
// wraps the value in `to_json(...)` so the binding sees a single
// VARCHAR; this helper undoes the wrap. If the value is already an
// object (legacy snapshots without the to_json wrap, or local dev
// where the binding handled the type), pass it through unchanged.
function parseMaybeJson(value: unknown): unknown {
  if (typeof value !== "string") return value
  if (value === "" || value === "null") return null
  try {
    return JSON.parse(value)
  } catch {
    return value
  }
}

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? value as T[] : []
}

// derived_tags arrives as a native list (models_view: VARCHAR[]) or a
// JSON-encoded string (evals_view / eval_results_view: VARCHAR). Coerce
// either into a string[].
function coerceTags(value: unknown): string[] {
  let current: unknown = value

  for (let depth = 0; depth < 3; depth += 1) {
    if (Array.isArray(current)) {
      return current.filter((t): t is string => typeof t === "string")
    }

    if (typeof current !== "string" || current.length === 0) {
      return []
    }

    try {
      current = JSON.parse(current)
    } catch {
      return []
    }
  }

  return []
}

// tag_stats is a JSON column ({tag: count}); coerce string-or-object into
// a plain Record<string, number>.
function coerceTagStats(value: unknown): Record<string, number> {
  let obj: unknown = value
  if (typeof value === "string" && value.length > 0) {
    try { obj = JSON.parse(value) } catch { return {} }
  }
  if (obj && typeof obj === "object" && !Array.isArray(obj)) {
    const out: Record<string, number> = {}
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      out[k] = Number(v) || 0
    }
    return out
  }
  return {}
}

// Model-card rows carry `tags` (derived_tags AS tags) and `tag_stats`
// straight off the parquet; normalise their runtime shapes.
function finalizeModelCard(row: Row): EvaluationCardData {
  return {
    ...row,
    tags: coerceTags(row.tags),
    tag_stats: coerceTagStats(row.tag_stats),
  } as EvaluationCardData
}

function sourceMetadataFromRow(row: Row): SourceMetadata {
  const sm = parseMaybeJson(row.source_metadata)
  if (sm && typeof sm === "object") {
    return sm as SourceMetadata
  }

  return {
    source_type: "documentation",
    source_organization_name: asString(row.latest_source_name, "Unknown"),
    evaluator_relationship: "other",
  }
}

function sourceDataFromRow(row: Row): BenchmarkEvaluation["source_data"] {
  const sourceData = parseMaybeJson(row.source_data) ?? parseMaybeJson(row.eval_source_data)
  if (sourceData) {
    return sourceData as BenchmarkEvaluation["source_data"]
  }

  return {
    dataset_name: asString(row.eval_evaluation_name ?? row.evaluation_name ?? row.benchmark_id, "Unknown dataset"),
  } satisfies SourceData
}

function scoreDetailsFromRow(row: Row): ScoreDetails {
  const parsed = parseMaybeJson(row.score_details)
  const details = parsed && typeof parsed === "object"
    ? parsed as Partial<ScoreDetails>
    : {}
  const score = asNumber(details.score ?? row.score)

  return {
    ...details,
    score,
  } as ScoreDetails
}

function metricConfigFromRow(row: Row): MetricConfig {
  const config = (parseMaybeJson(row.metric_config) ?? parseMaybeJson(row.eval_metric_config) ?? {}) as Partial<MetricConfig>
  const scoreType = config.score_type === "binary" || config.score_type === "discrete"
    ? config.score_type
    : "continuous"

  return {
    evaluation_description: asString(
      config.evaluation_description ??
        row.metric_description ??
        row.metric_display_name ??
        row.eval_evaluation_name ??
        row.evaluation_name,
      ""
    ),
    lower_is_better: Boolean(row.lower_is_better ?? config.lower_is_better ?? false),
    score_type: scoreType,
    min_score: optionalNumber(config.min_score ?? row.min_score),
    max_score: optionalNumber(config.max_score ?? row.max_score),
    unit: optionalString(row.metric_unit ?? config.unit),
  }
}

function modelInfoFromModelRow(row: Row): ModelInfo {
  return {
    name: asString(row.model_name ?? row.model_family_name ?? row.model_id ?? row.model_key, "Unknown model"),
    id: asString(row.model_key ?? row.model_id ?? row.id ?? row.route_id, "unknown-model"),
    developer: optionalString(row.developer),
    inference_platform: optionalString(row.inference_platform),
    inference_engine: optionalString(row.inference_engine),
    architecture: optionalString(row.architecture),
    parameter_count: optionalString(row.params),
    release_date: optionalString(row.release_date),
    model_url: optionalString(row.model_url),
    additional_details: {
      params_billions: row.params_billions,
    },
    modalities: {
      input: asArray<string>(row.input_modalities),
      output: asArray<string>(row.output_modalities),
    },
  }
}

// The view emits the group-level signal verdicts as flat columns
// (is_multi_source / first_party_only / completeness_score — uniform across
// the (model, benchmark, metric) group, see stage J), not inside the
// evalcards_annotations struct. Fold them into the annotation blocks the
// spec'd types declare so every annotations consumer sees one shape.
function withGroupSignals(
  annotations: RowAnnotations | undefined,
  row: Row
): RowAnnotations | undefined {
  if (!annotations) return annotations
  return {
    ...annotations,
    provenance: annotations.provenance
      ? {
          ...annotations.provenance,
          is_multi_source:
            row.is_multi_source == null
              ? annotations.provenance.is_multi_source
              : Boolean(row.is_multi_source),
          first_party_only:
            row.first_party_only == null
              ? annotations.provenance.first_party_only
              : Boolean(row.first_party_only),
          coverage_cell:
            row.coverage_cell == null
              ? annotations.provenance.coverage_cell
              : (String(row.coverage_cell) as "both" | "self" | "third"),
        }
      : annotations.provenance,
    reporting_completeness:
      row.completeness_score == null
        ? annotations.reporting_completeness
        : { completeness_score: Number(row.completeness_score) },
  }
}

function resultFromCell(row: Row): EvaluationResult {
  const scoreDetails = scoreDetailsFromRow(row)
  // model_info / generation_config / source_metadata / ... all arrive
  // JSON-encoded — CELL_JOIN_COLUMNS wraps every non-primitive column
  // in to_json() + CAST AS VARCHAR to dodge the binding's
  // "don't know what type:" crash. parseMaybeJson reverses the wrap;
  // it passes through unchanged when the value is already an object
  // (legacy snapshots / future binding fixes).
  const generationConfig = parseMaybeJson(row.generation_config) as GenerationConfig | undefined
  const annotations = withGroupSignals(
    parseMaybeJson(row.evalcards_annotations) as RowAnnotations | undefined,
    row
  )

  return {
    evaluation_name: asString(row.metric_display_name ?? row.eval_evaluation_name ?? row.metric_id, "Score"),
    display_name: optionalString(row.metric_display_name),
    canonical_display_name: optionalString(row.metric_display_name),
    metric_summary_id: optionalString(row.metric_summary_id),
    metric_key: optionalString(row.metric_id),
    evaluation_timestamp: asString(row.evaluation_timestamp, ""),
    source_data: sourceDataFromRow(row),
    metric_config: metricConfigFromRow(row),
    score_details: scoreDetails,
    generation_config: generationConfig,
    detailed_evaluation_results_url: optionalString(row.instance_file_path),
    evalcards: annotations ? { annotations } : undefined,
    // Per-result verification flag (eval_results_view.is_verified_evaluator).
    // Coerced to a strict boolean; absent on pre-rollout snapshots →
    // undefined → treated as unverified by the UI.
    is_verified_evaluator:
      row.is_verified_evaluator == null ? undefined : Boolean(row.is_verified_evaluator),
  }
}

function reshapeCellToModelResult(row: Row): ModelResultForBenchmark {
  const scoreDetails = scoreDetailsFromRow(row)
  // Every wrapped column needs parseMaybeJson to come back to its
  // object shape — see CELL_JOIN_COLUMNS for the wrapping sites.
  const modelInfo = parseMaybeJson(row.model_info)
  const aggregateComponents = parseMaybeJson(row.aggregate_components)

  return {
    model_info: (modelInfo ?? modelInfoFromModelRow(row)) as ModelInfo,
    model_route_id: optionalString(row.model_route_id),
    // model-resolution-rework: server-provided group id for routing fallback.
    model_group_id: optionalString(row.model_group_id),
    score: scoreDetails.score,
    score_details: scoreDetails,
    evaluation_timestamp: asString(row.evaluation_timestamp, ""),
    source_metadata: sourceMetadataFromRow(row),
    source_data: sourceDataFromRow(row),
    source_record_url: optionalString(row.source_record_url),
    eee_record_url: optionalString(row.eee_record_url),
    aggregate_components: asArray<NonNullable<ModelResultForBenchmark["aggregate_components"]>[number]>(
      aggregateComponents
    ),
    result: resultFromCell(row),
  }
}

function reshapeCellToBenchmarkEvaluation(row: Row): BenchmarkEvaluation {
  const result = resultFromCell(row)
  const modelInfo = parseMaybeJson(row.model_info)
  const evalLibrary = parseMaybeJson(row.eval_library)
  const generationConfig = parseMaybeJson(row.generation_config)

  return {
    schema_version: "1.0",
    eval_summary_id: optionalString(row.evaluation_id),
    evaluation_id: asString(row.evaluation_id ?? row.benchmark_id, "unknown-evaluation"),
    retrieved_timestamp: asString(row.evaluation_timestamp, ""),
    benchmark: optionalString(row.eval_evaluation_name ?? row.benchmark_id),
    display_name: optionalString(row.eval_evaluation_name),
    canonical_display_name: optionalString(row.eval_canonical_display_name),
    derived_tags: coerceTags(row.eval_derived_tags ?? row.derived_tags),
    family_id: optionalString(row.eval_family_id),
    benchmark_family_name: optionalString(row.eval_family_display_name),
    parent_benchmark_id: optionalString(row.eval_parent_benchmark_id),
    parent_benchmark_display_name: optionalString(row.eval_parent_benchmark_display_name),
    // Prefer the real parent display name; older snapshots only ship the
    // composite/suite label, which mislabels cross-benchmark suites.
    benchmark_parent_name:
      optionalString(row.eval_parent_benchmark_display_name) ??
      optionalString(row.eval_composite_benchmark_name),
    benchmark_leaf_name: optionalString(row.eval_evaluation_name),
    is_slice: Boolean(row.eval_is_slice),
    is_summary_score: Boolean(row.eval_is_summary_score ?? row.is_summary_score),
    source_data: sourceDataFromRow(row),
    source_metadata: sourceMetadataFromRow(row),
    eval_library: evalLibrary as BenchmarkEvaluation["eval_library"],
    model_info: (modelInfo ?? modelInfoFromModelRow(row)) as ModelInfo,
    generation_config: generationConfig as BenchmarkEvaluation["generation_config"],
    evaluation_results: [result],
  }
}

function modelSummaryFromRows(modelRow: Row, cellRows: Row[]): ModelEvaluationSummary {
  // An evaluation can carry several tags, so it appears under each of its
  // tags (multi-membership), unlike the old single-category grouping.
  const evaluationsByTag: Record<string, BenchmarkEvaluation[]> = {}
  for (const cellRow of cellRows) {
    const evaluation = reshapeCellToBenchmarkEvaluation(cellRow)
    const tags = evaluation.derived_tags && evaluation.derived_tags.length > 0
      ? evaluation.derived_tags
      : ["general"]
    for (const tag of tags) {
      (evaluationsByTag[tag] ??= []).push(evaluation)
    }
  }

  const tagsCovered = coerceTags(modelRow.tags ?? modelRow.derived_tags)
  const modelInfo = (modelRow.model_info ?? modelInfoFromModelRow(modelRow)) as ModelInfo
  const totalEvaluations = asNumber(modelRow.total_evaluations ?? modelRow.evaluations_count)
  const lastUpdated = asString(modelRow.last_updated ?? modelRow.latest_timestamp, "")
  const rawModelIds = asArray<string>(modelRow.raw_model_ids)

  const core = {
    model_info: modelInfo,
    evaluations_by_tag: evaluationsByTag,
    total_evaluations: totalEvaluations,
    last_updated: lastUpdated,
    tags_covered: tagsCovered.length > 0 ? tagsCovered : Object.keys(evaluationsByTag),
    reproducibility_summary: modelRow.reproducibility_summary,
    provenance_summary: modelRow.provenance_summary,
    comparability_summary: modelRow.comparability_summary,
  }

  const variants = asArray<Row>(modelRow.variants).map((variant, index) => ({
    ...core,
    ...variant,
    variant_id: asString(variant.variant_id ?? variant.variant_key, `variant-${index}`),
    variant_key: asString(variant.variant_key, `variant-${index}`),
    // Carry the GROUP's encoded route onto every variant. comparison-index /
    // peer-ranks are keyed by the group route_id, and the model detail page
    // renders the selected VARIANT as its summary — without this the variant
    // has no model_route_id and the page falls back to a non-matching id, so
    // peer-comparison charts find no scores.
    model_route_id: asString(modelRow.model_route_id ?? modelRow.route_id, modelRow.route_id),
    variant_label: asString(variant.variant_label ?? variant.variant_display_name, "Default"),
    variant_display_name: asString(variant.variant_display_name ?? variant.variant_label ?? modelRow.model_name, modelRow.model_name),
    raw_model_ids: asArray<string>(variant.raw_model_ids),
    family_id: asString(variant.family_id ?? modelRow.model_group_id, modelRow.model_group_id),
    family_name: asString(variant.family_name ?? modelRow.model_family_name, modelRow.model_family_name),
    total_evaluations: asNumber(variant.total_evaluations ?? totalEvaluations),
    last_updated: asString(variant.last_updated ?? lastUpdated, lastUpdated),
    tags_covered: coerceTags(variant.tags_covered ?? variant.derived_tags).length > 0
      ? coerceTags(variant.tags_covered ?? variant.derived_tags)
      : core.tags_covered,
    model_info: {
      ...modelInfo,
      name: asString(variant.variant_display_name ?? variant.variant_label ?? modelInfo.name, modelInfo.name),
    },
  })) as ModelVariantSummary[]

  return {
    ...core,
    model_group_id: asString(modelRow.model_group_id ?? modelRow.model_key ?? modelRow.model_id, modelRow.model_key ?? modelRow.model_id),
    model_route_id: asString(modelRow.model_route_id ?? modelRow.route_id, modelRow.route_id),
    model_family_name: asString(modelRow.model_family_name ?? modelRow.model_name, modelRow.model_name),
    raw_model_ids: rawModelIds.length > 0 ? rawModelIds : [asString(modelRow.model_key ?? modelRow.model_id, "")].filter(Boolean),
    // model-resolution-rework (additive, nullable). The summary builder
    // reads `SELECT *` from models_view, so these columns flow through
    // once the producer view layer emits them (post-M9). Until then
    // optionalString yields undefined and the UI conditionally omits them.
    lineage_origin_model_id: optionalString(modelRow.lineage_origin_model_id),
    resolution_source: optionalString(modelRow.resolution_source),
    resolution_granularity: optionalString(modelRow.resolution_granularity),
    variants,
  }
}

// Probe (once per process) whether the loaded snapshot's evals_view carries
// the additive parent_benchmark_display_name column, so projections degrade
// to a NULL alias on older snapshots instead of binder-erroring the query.
let evalsViewParentDisplayNameCache: boolean | undefined
async function evalsViewHasParentDisplayName(): Promise<boolean> {
  if (evalsViewParentDisplayNameCache === undefined) {
    try {
      const columns = await readRows<{ column_name: string }>("DESCRIBE evals_view")
      evalsViewParentDisplayNameCache = columns.some(
        (column) => column.column_name === "parent_benchmark_display_name"
      )
    } catch {
      // Probe failed (e.g. connection init blip) — don't cache, so the next
      // request re-probes; the data query that follows surfaces the real
      // error if the connection is genuinely broken.
      return false
    }
  }
  return evalsViewParentDisplayNameCache
}

async function getModelEvaluationRows(modelKey: string): Promise<Row[]> {
  const hasParentDisplayName = await evalsViewHasParentDisplayName()
  // model_key is the producer's addressable identifier — non-null for both
  // resolved and unresolved models (the latter fall back to the raw source
  // name). Querying by model_id alone would silently miss unresolved models.
  return readRows<Row>(
    `SELECT ${modelCellJoinColumns(hasParentDisplayName)}
     FROM eval_results_view r
     LEFT JOIN evals_view e ON r.evaluation_id = e.evaluation_id
     WHERE r.model_key = ?
       AND r.score IS NOT NULL
     ORDER BY r.percentile DESC NULLS LAST`,
    [modelKey],
    { contextLabel: `model_key=${modelKey}` }
  )
}

export async function getModelCards(): Promise<EvaluationCardData[]> {
  const rows = await readRows<Row>(
    `SELECT ${MODEL_CARD_COLUMNS}
     FROM models_view
     ORDER BY latest_timestamp DESC NULLS LAST`
  )
  return rows.map(finalizeModelCard)
}

export async function getModelCardsLite(): Promise<EvaluationCardData[]> {
  const rows = await readRows<Row>(
    `SELECT ${MODEL_CARD_COLUMNS}
     FROM models_view
     ORDER BY benchmarks_count DESC NULLS LAST, evaluations_count DESC NULLS LAST, model_name ASC`
  )
  return rows.map(finalizeModelCard)
}

export async function getEvalListData(): Promise<{
  evals: BenchmarkEvalListItem[]
  totalModels: number
}> {
  const hasParentDisplayName = await evalsViewHasParentDisplayName()
  const [evalRows, countRows] = await Promise.all([
    readRows<BenchmarkEvalListItem & { benchmark_card?: unknown }>(
      `SELECT ${evalListColumns(hasParentDisplayName)}
       FROM evals_view
       ORDER BY evaluation_name ASC`
    ),
    readRows<{ n: number }>("SELECT COUNT(*) AS n FROM models_view"),
  ])

  // benchmark_card is JSON-encoded at the SQL layer; parse it, and coerce
  // derived_tags, before handing rows to consumers that expect object shapes.
  const decoded = evalRows.map((row) => ({
    ...row,
    derived_tags: coerceTags(row.derived_tags),
    metric_config: parseMaybeJson(row.metric_config),
    benchmark_card: parseMaybeJson(row.benchmark_card),
    aggregate_sources: parseMaybeJson(row.aggregate_sources),
    tags: parseMaybeJson(row.tags),
    instance_data: parseMaybeJson(row.instance_data),
    root_metrics: parseMaybeJson(row.root_metrics),
    subtasks: parseMaybeJson(row.subtasks),
    leaderboard_metrics: parseMaybeJson(row.leaderboard_metrics),
    reproducibility_summary: parseMaybeJson(row.reproducibility_summary),
    provenance_summary: parseMaybeJson(row.provenance_summary),
    comparability_summary: parseMaybeJson(row.comparability_summary),
    source_data: parseMaybeJson(row.source_data),
  })) as unknown as BenchmarkEvalListItem[]

  return {
    evals: decoded,
    totalModels: asNumber(countRows[0]?.n),
  }
}

export async function getEvalListLiteData(): Promise<{
  evals: BenchmarkEvalListItem[]
  totalModels: number
}> {
  return getEvalListData()
}

export async function getEvalList() {
  const { evals } = await getEvalListData()
  return evals
}

export async function getDashboardData() {
  const [models, evals] = await Promise.all([
    getModelCards(),
    getEvalList(),
  ])
  return { models, evals }
}

export async function getModelSummaryById(routeId: string): Promise<ModelEvaluationSummary | null> {
  // Lookups use the addressable identifier (`model_key`/`route_id`/
  // `model_route_id`/`model_group_id`) so unresolved models — whose
  // `model_id` is NULL — are still findable. `model_id` is kept in the
  // OR chain as a back-compat fallback for old links.
  //
  // Three slug shapes flow into this route handler:
  //   - URL-encoded form (canonical, e.g. `google%2Fgemini-3-pro`) —
  //     Next.js already decodes path params before they reach here, so
  //     `routeId` lands as `google/gemini-3-pro`.
  //   - Plain canonical id with `/` (same shape after Next.js decode).
  //   - Legacy `__`-separated form (e.g. `google__gemini-3-pro`) — the
  //     old client-side family route computation emitted this; bookmarks
  //     may still use it. Convert `__` → `/` for lookup.
  const dunder = routeId.includes("__") ? routeId.replace(/__/g, "/") : routeId
  const rows = await readRows<Row>(
    `SELECT *
     FROM models_view
     WHERE model_key = ? OR route_id = ? OR model_route_id = ? OR model_group_id = ? OR model_id = ?
        OR model_key = ? OR model_id = ?
     LIMIT 1`,
    [routeId, routeId, routeId, routeId, routeId, dunder, dunder],
    { contextLabel: `model_lookup=${routeId}` }
  )
  let modelRow = rows[0]
  if (!modelRow) {
    // The id may be a FOLDED raw id — a dated snapshot / older-cased / variant
    // spelling the producer collapsed into a group (e.g.
    // `mistralai/mistral-medium-2505` folds into `mistralai/mistral-medium`).
    // Such ids exist only inside the owning group row's `raw_model_ids` list,
    // never as their own row, so resolve them to that group. Case-insensitive,
    // since raw_model_ids preserve HF casing. This makes every inbound model
    // link/bookmark resolve to a real page instead of 404-ing.
    const byRaw = await readRows<Row>(
      `SELECT *
       FROM models_view
       WHERE list_contains(list_transform(raw_model_ids, x -> lower(x)), lower(?))
          OR list_contains(list_transform(raw_model_ids, x -> lower(x)), lower(?))
       LIMIT 1`,
      [routeId, dunder]
    )
    modelRow = byRaw[0]
  }
  if (!modelRow) return null

  const cellRows = await getModelEvaluationRows(asString(modelRow.model_key ?? modelRow.model_id, routeId))
  return modelSummaryFromRows(modelRow, cellRows)
}

// Build-time precomputed multi-metric / per-slice matrix produced by
// `scripts/build-eval-matrices.mjs`. Read once on first request and
// cached in module scope — the file is image-baked so this is a single
// disk read per server start. When the file is missing (local dev where
// nobody ran `pnpm build-eval-matrices` yet), we fall through and the
// summary degrades to single-metric exactly like before.
type MatrixEntry = {
  leaderboard_rows: Array<{ model_route_id: string; values: Record<string, number | null>; verified?: Record<string, boolean> }>
  subtask_metrics: Array<Record<string, unknown>>
}

let evalMatrixCache: Record<string, MatrixEntry> | null | undefined
function loadEvalMatrices(): Record<string, MatrixEntry> | null {
  if (evalMatrixCache !== undefined) return evalMatrixCache
  try {
    const matrixPath = path.join(process.cwd(), "data", "eval-matrices.json")
    const text = fs.readFileSync(matrixPath, "utf8")
    const parsed = JSON.parse(text) as { evals?: Record<string, MatrixEntry> }
    evalMatrixCache = parsed.evals ?? {}
  } catch {
    evalMatrixCache = null
  }
  return evalMatrixCache
}

export async function getEvalSummaryById(evalId: string): Promise<BenchmarkEvalSummary | null> {
  // Use the same aliased projection as EVAL_LIST_COLUMNS so the legacy
  // `composite_benchmark_*` / `benchmark_family_*` consumer fields are
  // populated. A bare `SELECT *` returns the raw v2 column names which
  // leaves the legacy fields NULL on the deserialised summary.
  const evalRows = await readRows<Row>(
    `SELECT ${evalListColumns(await evalsViewHasParentDisplayName())}
     FROM evals_view
     WHERE evaluation_id = ?
     LIMIT 1`,
    [evalId],
    { contextLabel: `eval_lookup=${evalId}` }
  )
  const evalRow = evalRows[0]
  if (!evalRow) return null

  let cellRows = await readRows<Row>(
    `SELECT ${EVAL_CELL_JOIN_COLUMNS}
     FROM eval_results_view r
     LEFT JOIN evals_view e ON r.evaluation_id = e.evaluation_id
     WHERE r.evaluation_id = ?
       AND r.metric_id = (SELECT primary_metric_id FROM evals_view WHERE evaluation_id = ?)
       AND r.score IS NOT NULL
     ORDER BY r.position ASC NULLS LAST`,
    [evalId, evalId],
    { contextLabel: `eval_id=${evalId} primary_metric` }
  )

  if (cellRows.length === 0) {
    cellRows = await readRows<Row>(
      `SELECT ${EVAL_CELL_JOIN_COLUMNS}
       FROM eval_results_view r
       LEFT JOIN evals_view e ON r.evaluation_id = e.evaluation_id
       WHERE r.evaluation_id = ?
         AND r.score IS NOT NULL
       ORDER BY r.position ASC NULLS LAST`,
      [evalId],
      { contextLabel: `eval_id=${evalId} fallback` }
    )
  }

  const summary = {
    ...evalRow,
    derived_tags: coerceTags(evalRow.derived_tags),
    metric_config: parseMaybeJson(evalRow.metric_config),
    // benchmark_card arrives JSON-encoded (the parquet schema nests a
    // JSON-typed field — see CELL_JOIN_COLUMNS / EVAL_LIST_COLUMNS).
    benchmark_card: parseMaybeJson(evalRow.benchmark_card),
    aggregate_sources: parseMaybeJson(evalRow.aggregate_sources),
    tags: parseMaybeJson(evalRow.tags),
    instance_data: parseMaybeJson(evalRow.instance_data),
    root_metrics: parseMaybeJson(evalRow.root_metrics),
    subtasks: parseMaybeJson(evalRow.subtasks),
    leaderboard_metrics: parseMaybeJson(evalRow.leaderboard_metrics),
    reproducibility_summary: parseMaybeJson(evalRow.reproducibility_summary),
    provenance_summary: parseMaybeJson(evalRow.provenance_summary),
    comparability_summary: parseMaybeJson(evalRow.comparability_summary),
    source_data: parseMaybeJson(evalRow.source_data),
    model_results: cellRows.map(reshapeCellToModelResult),
  } as unknown as BenchmarkEvalSummary

  // Splice in precomputed multi-metric leaderboard_rows and subtask
  // leaderboard_metrics from data/eval-matrices.json. Models in the matrix
  // but not in cellRows (zero-coverage primary metric) are also surfaced
  // so a user can still see per-slice or non-primary scores. The base row
  // shape comes from any matching cellRow when one exists.
  const matrices = loadEvalMatrices()
  const matrix = matrices?.[evalId]
  if (matrix) {
    const baseRowByRoute = new Map<string, ModelResultForBenchmark>()
    for (const result of summary.model_results) {
      if (result.model_route_id) {
        baseRowByRoute.set(result.model_route_id, result)
      }
    }

    const leaderboardRows = matrix.leaderboard_rows
      .map((row) => {
        const base = baseRowByRoute.get(row.model_route_id)
        if (!base) return null
        return {
          model_info: base.model_info,
          model_route_id: row.model_route_id,
          model_group_id: base.model_group_id,
          evaluation_timestamp: base.evaluation_timestamp,
          source_metadata: base.source_metadata,
          source_data: base.source_data,
          values: row.values,
          verified: row.verified,
          metrics_present: Object.values(row.values).filter(
            (v): v is number => typeof v === "number" && Number.isFinite(v),
          ).length,
        }
      })
      .filter((row): row is NonNullable<typeof row> => row !== null)

    if (leaderboardRows.length > 0) {
      summary.leaderboard_rows = dedupeLeaderboardRowsByModelIdentity(leaderboardRows)
    }
    if (matrix.subtask_metrics.length > 0) {
      const existing = (summary.leaderboard_metrics ?? []) as Array<{
        column_key: string
        scope?: string
      }>
      const seen = new Set(existing.map((m) => m.column_key))
      // Root metrics already present from the snapshot. The matrix precompute
      // emits an aggregate slice (`accuracy::overall`) for every measure, whose
      // values are byte-identical to the root metric (`accuracy`). Those would
      // double every column — root "Accuracy" plus a redundant "Accuracy ·
      // overall" twin — so drop a trivial-aggregate slice when its base measure
      // already exists as a root metric. Genuine slices (`score::gaming`) are
      // kept; only overall/all/total/default aggregates are pruned.
      const rootKeys = new Set(
        existing.filter((m) => m.scope !== "subtask").map((m) => m.column_key),
      )
      const TRIVIAL_AGGREGATE = /^(overall|all|total|default)$/i
      const isRedundantAggregate = (columnKey: string) => {
        const parts = columnKey.split("::")
        if (parts.length < 2) return false
        const slice = parts[parts.length - 1]
        const base = parts.slice(0, -1).join("::")
        return TRIVIAL_AGGREGATE.test(slice) && rootKeys.has(base)
      }
      const merged = [
        ...existing,
        ...matrix.subtask_metrics.filter(
          (m): m is typeof m & { column_key: string } =>
            typeof m.column_key === "string" &&
            !seen.has(m.column_key) &&
            !isRedundantAggregate(m.column_key),
        ),
      ]
      summary.leaderboard_metrics =
        merged as unknown as BenchmarkEvalSummary["leaderboard_metrics"]
    }
  }

  // Fallback for single-metric leaderboards with no precomputed matrix
  // entry (e.g. big-bench-hard): the matrix block above only populates
  // `leaderboard_rows` when a matrix exists, but consumers like the
  // embed leaderboard read exclusively from that field. Synthesize one
  // row per `model_results` entry using the primary metric's column_key
  // as the values key, so the data is present regardless of whether
  // build-time precomputation ran for this eval.
  const hasRows = (summary.leaderboard_rows?.length ?? 0) > 0
  if (!hasRows && (summary.model_results?.length ?? 0) > 0) {
    const primaryMetric = (summary.leaderboard_metrics ?? []).find(
      (m): m is typeof m & { column_key: string } =>
        typeof (m as { column_key?: unknown }).column_key === "string"
        && (m as { scope?: string }).scope !== "subtask",
    )
    const columnKey = primaryMetric?.column_key
      ?? (summary.leaderboard_metrics ?? [])[0]?.column_key
      ?? "score"
    summary.leaderboard_rows = summary.model_results
      .filter((mr) => Number.isFinite(mr.score) && mr.model_route_id)
      .map((mr) => ({
        model_info: mr.model_info,
        model_route_id: mr.model_route_id,
        model_group_id: mr.model_group_id,
        evaluation_timestamp: mr.evaluation_timestamp,
        source_metadata: mr.source_metadata,
        source_data: mr.source_data,
        values: { [columnKey]: mr.score as number },
        verified: mr.result?.is_verified_evaluator
          ? { [columnKey]: true }
          : undefined,
        metrics_present: 1,
      })) as BenchmarkEvalSummary["leaderboard_rows"]
  }

  // Belt-and-suspenders: when leaderboard_rows arrived from the parquet
  // pre-baked (no matrix) the same two-source duplication can appear, so
  // dedup whatever is set on the summary before returning.
  if (summary.leaderboard_rows && summary.leaderboard_rows.length > 1) {
    summary.leaderboard_rows = dedupeLeaderboardRowsByModelIdentity(summary.leaderboard_rows)
  }

  return summary
}

export async function getDeveloperList(): Promise<DeveloperListEntry[]> {
  const headline = await fetchHeadline()
  return [...(headline.developers ?? [])].sort((a, b) => a.developer.localeCompare(b.developer))
}

function decodeLoose(value: string): string {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

export async function getDeveloperSummaryById(routeId: string) {
  const developers = await getDeveloperList()
  // `route_id` is stored pre-percent-encoded for names with spaces/parens
  // (e.g. "Mistral AI" -> "Mistral%20AI"), but the incoming routeId arrives
  // already decoded (routeIdFromSegments only round-trips %2F). Compare on the
  // decoded form so those developers' detail pages resolve. Exact match is
  // tried first as a fast path.
  const target = decodeLoose(routeId)
  const developer =
    developers.find((entry) => entry.route_id === routeId) ??
    developers.find((entry) => decodeLoose(entry.route_id) === target)
  if (!developer) return null

  const modelRows = await readRows<Row>(
    `SELECT ${MODEL_CARD_COLUMNS}
     FROM models_view
     WHERE developer = ?
     ORDER BY benchmarks_count DESC NULLS LAST, evaluations_count DESC NULLS LAST, model_name ASC`,
    [developer.developer]
  )

  return {
    ...developer,
    models: modelRows.map(finalizeModelCard),
  }
}

export async function getBenchmarkMetadataMap(): Promise<Record<string, BenchmarkCard>> {
  const rows = await readRows<Row>(
    `SELECT evaluation_id, evaluation_name,
            family_id AS composite_benchmark_key,
            benchmark_id,
            benchmark_card
     FROM evals_view
     WHERE benchmark_card IS NOT NULL`
  )
  const result: Record<string, BenchmarkCard> = {}

  for (const row of rows) {
    const card = parseMaybeJson(row.benchmark_card) as BenchmarkCard | null | undefined
    if (!card) continue

    const keys = [
      row.evaluation_id,
      row.evaluation_name,
      row.composite_benchmark_key,
      row.benchmark_id,
      card.benchmark_details?.name,
    ].filter((key): key is string => typeof key === "string" && key.length > 0)

    for (const key of keys) {
      result[key] = card
    }
  }

  return result
}
