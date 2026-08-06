// @ts-nocheck
// Dump current TS-adapter outputs for the cross-repo parity verifier.
//
// The `server-only` import on every lib file at line 1 throws under Node;
// the wrapper Python verifier preloads `scripts/server_only_hook.cjs`
// via NODE_OPTIONS before invoking this script.
//
// Reads a pipeline output directory (`output/`), runs each TS adapter
// against the corresponding JSON, and writes the expected payload set
// as JSON to stdout (or a file).
//
// Usage (from `general-eval-card/`):
//   pnpm tsx scripts/dump-adapter-outputs.mts \
//     --pipeline-output /Users/jchim/projects/evaleval/eval_cards_backend_pipeline/output \
//     --out /tmp/parity-expected.json
//
// Surfaces dumped: model_cards, model_cards_lite, eval_list, eval_list_lite,
// eval_summaries (per detail), model_summaries (per family),
// aggregate_eval_summaries (per suite), matrix_eval_summaries (per suite),
// developer_summaries, developers.
import { createWriteStream, readFileSync, readdirSync, writeFileSync } from "node:fs"
import { join } from "node:path"

import * as ModelDataMod from "@/lib/model-data"
import * as HfDataMod from "@/lib/hf-data"
import * as EvalProcessingMod from "@/lib/eval-processing"
import * as BenchmarkMetadataUtilsMod from "@/lib/benchmark-metadata-utils"

// Under `tsx`, the libs are CommonJS modules; ESM `import *` lifts the
// real exports onto the synthetic `default`. Pull them off there.
const ModelData: any = (ModelDataMod as any).default ?? ModelDataMod
const HfData: any = (HfDataMod as any).default ?? HfDataMod
const EvalProcessing: any =
  (EvalProcessingMod as any).default ?? EvalProcessingMod
const BenchmarkMetadataUtils: any =
  (BenchmarkMetadataUtilsMod as any).default ?? BenchmarkMetadataUtilsMod
const candidateBenchmarkKeys = BenchmarkMetadataUtils.candidateBenchmarkKeys

const hfModelCardToEvaluationCardData = ModelData.hfModelCardToEvaluationCardData
const hfEvalEntryToListItem = ModelData.hfEvalEntryToListItem
const hfEvalDetailToSummary = ModelData.hfEvalDetailToSummary
const hfDeveloperDetailToSummary = ModelData.hfDeveloperDetailToSummary
const aggregateBenchmarkSummaries = ModelData.aggregateBenchmarkSummaries
const buildSingleMetricSuiteMatrixSummary = ModelData.buildSingleMetricSuiteMatrixSummary
const flattenModelEvaluations = HfData.flattenModelEvaluations
// Mirror the request-time normalizer in `fetchModelCardsList` /
// `fetchModelCardsListLite` (lib/hf-data.ts:822, 827): every fetch runs
// `normalizeSingleModelCardEntry` to merge setup-alias variants
// ("prompt"/"fc"/"thinking") under one variant_key. Without this the
// dump's variant_count is the raw 6-variant count from disk, but the
// user-facing API returns the post-merge count (~2-3).
const normalizeSingleModelCardEntry = HfData.normalizeSingleModelCardEntry
const createModelFamilySummary = EvalProcessing.createModelFamilySummary

function parseArgs() {
  const args: Record<string, string> = {}
  for (let i = 2; i < process.argv.length; i++) {
    const arg = process.argv[i]
    if (arg.startsWith("--")) {
      const key = arg.slice(2)
      const next = process.argv[i + 1]
      if (next && !next.startsWith("--")) {
        args[key] = next
        i++
      } else {
        args[key] = "true"
      }
    }
  }
  return args
}

function readJSON<T>(path: string): T {
  return JSON.parse(readFileSync(path, "utf-8")) as T
}

function listJSONFiles(dir: string): string[] {
  try {
    return readdirSync(dir).filter((p) => p.endsWith(".json"))
  } catch {
    return []
  }
}

interface DumpedSurface {
  surface: string
  by_id: Record<string, unknown>
}

const args = parseArgs()
const pipelineRoot = args["pipeline-output"]
const outPath = args["out"]
if (!pipelineRoot) {
  console.error("Missing --pipeline-output <dir>")
  process.exit(2)
}

const modelCards = readJSON<Array<Record<string, any>>>(
  join(pipelineRoot, "model-cards.json")
)
const modelCardsLite = readJSON<Array<Record<string, any>>>(
  join(pipelineRoot, "model-cards-lite.json")
)
const evalList = readJSON<{ evals: Array<Record<string, any>> }>(
  join(pipelineRoot, "eval-list.json")
)
const evalListLite = readJSON<{ evals: Array<Record<string, any>> }>(
  join(pipelineRoot, "eval-list-lite.json")
)
const evalsDir = join(pipelineRoot, "evals")
const modelsDir = join(pipelineRoot, "models")

// Build a sync benchmark card lookup mirror of `lib/benchmark-metadata.ts`'s
// `readPipelineBenchmarkCards` — used for aggregate/matrix surfaces, which
// in the request-time TS path call the async `attachBenchmarkCardToSummary`.
// The pipeline parity layer (`scripts/parity_outputs.py:build_aggregate_eval_summaries`)
// uses a sync card_map; mirror that approach so the dump runs without
// network/async machinery.
const benchmarkMetadata = readJSON<Record<string, any>>(
  join(pipelineRoot, "benchmark-metadata.json")
)
const benchmarkCardMap = new Map<string, any>()
for (const card of Object.values(benchmarkMetadata)) {
  const cardObj = card as Record<string, any>
  const name = cardObj?.benchmark_details?.name
  if (!name) continue
  for (const key of candidateBenchmarkKeys(name)) {
    if (!benchmarkCardMap.has(key)) {
      benchmarkCardMap.set(key, cardObj)
    }
  }
}

function syncGetBenchmarkCard(name: string | undefined | null): any | null {
  if (!name) return null
  for (const key of candidateBenchmarkKeys(name)) {
    const card = benchmarkCardMap.get(key)
    if (card) return card
  }
  return null
}

// Sync mirror of `attachBenchmarkCardToSummary` (lib/model-data.ts). The
// async upstream awaits `getBenchmarkCard`; here we use the sync card map
// loaded from `benchmark-metadata.json` so dump-adapter-outputs stays
// fully sync (no fetch / `server-only` boundary).
function syncAttachBenchmarkCardToSummary(summary: any): any {
  if (summary?.benchmark_card) return summary
  const candidates = [
    summary?.evaluation_name,
    summary?.composite_benchmark_name,
    summary?.composite_benchmark_key,
  ]
  for (const candidate of candidates) {
    const card = syncGetBenchmarkCard(candidate)
    if (card) return { ...summary, benchmark_card: card }
  }
  return summary
}

const dumped: DumpedSurface[] = []

dumped.push({
  surface: "model_cards",
  by_id: Object.fromEntries(
    modelCards.map((card) => {
      const normalized = normalizeSingleModelCardEntry(card as any)
      const payload = hfModelCardToEvaluationCardData(normalized as any)
      // Key by the adapter-canonical `route_id` so it matches parquet's
      // scalar `model_route_id` column.
      return [payload.route_id, payload]
    })
  ),
})

// model_cards_lite — same adapter pipeline as model_cards, but reads the
// `-lite.json` source. Mirrors `getModelCardsLite()` in lib/model-data.ts.
dumped.push({
  surface: "model_cards_lite",
  by_id: Object.fromEntries(
    modelCardsLite.map((card) => {
      const normalized = normalizeSingleModelCardEntry(card as any)
      const payload = hfModelCardToEvaluationCardData(normalized as any)
      return [payload.route_id, payload]
    })
  ),
})

// Mirror the request-time filter in `getEvalListData` /
// `getEvalListLiteData` (lib/model-data.ts:1251, 1291): drop entries
// whose `source_data.hf_repo` starts with `example://`. Applied here so
// the parity verifier sees the same user-facing shape the parity emitter
// produces (`scripts/parity_outputs.py:_is_example_eval_entry`).
function isExampleEntry(entry: Record<string, any>): boolean {
  const repo = entry?.source_data?.hf_repo
  return typeof repo === "string" && repo.startsWith("example://")
}

dumped.push({
  surface: "eval_list",
  by_id: Object.fromEntries(
    (evalList.evals ?? [])
      .filter((entry) => !isExampleEntry(entry))
      .map((entry) => {
        const payload = hfEvalEntryToListItem(entry as any)
        return [payload.evaluation_id, payload]
      })
  ),
})

// eval_list_lite — same adapter as eval_list but reads from
// `eval-list-lite.json`; mirrors `getEvalListLiteData` in lib/model-data.ts
// (which also strips example entries).
dumped.push({
  surface: "eval_list_lite",
  by_id: Object.fromEntries(
    (evalListLite.evals ?? [])
      .filter((entry) => !isExampleEntry(entry))
      .map((entry) => {
        const payload = hfEvalEntryToListItem(entry as any)
        return [payload.evaluation_id, payload]
      })
  ),
})

// Sort eval-detail filenames by codepoint so iteration order matches
// Python's default string comparison on the parity side (which sorts
// `parity_outputs.build_aggregate_eval_summaries` inputs by
// `eval_summary_id`). `localeCompare` treats `_` as collation-ignorable
// at primary level, putting `foo_25.json` before `foo.json` — Python's
// codepoint sort orders them the other way. Plain `.sort()` (no
// compareFn) does the same codepoint comparison Python does.
const evalDetails: Array<Record<string, any>> = listJSONFiles(evalsDir)
  .slice()
  .sort()
  .map((file) => readJSON<Record<string, any>>(join(evalsDir, file)))

dumped.push({
  surface: "eval_summaries",
  by_id: Object.fromEntries(
    evalDetails.map((detail) => [
      detail.eval_summary_id,
      hfEvalDetailToSummary(detail as any),
    ])
  ),
})

// aggregate_eval_summaries — port of the `aggregate__<suite_key>` branch in
// `getEvalSummaryById` (lib/model-data.ts). The TS path runs each sub-eval
// through `hfEvalDetailToSummary`, attaches a benchmark card, then calls
// `aggregateBenchmarkSummaries(summaries, suiteKey)`. We mirror parity
// emitter `build_aggregate_eval_summaries` (parity_outputs.py:212-258):
//   - group by `benchmark_family_key || benchmark_parent_key`
//   - skip groups with fewer than 2 distinct sub-evals
// Keyed by `payload.evaluation_id` (= `aggregate__<suite_key>`).
{
  const aggregateGroups = new Map<string, Record<string, any>[]>()
  for (const detail of evalDetails) {
    const suiteKey =
      detail.benchmark_family_key || detail.benchmark_parent_key
    if (!suiteKey) continue
    if (!detail.eval_summary_id) continue
    const list = aggregateGroups.get(String(suiteKey)) ?? []
    list.push(detail)
    aggregateGroups.set(String(suiteKey), list)
  }

  const aggregateById: Record<string, any> = {}
  for (const [suiteKey, details] of aggregateGroups.entries()) {
    // De-dupe by eval_summary_id (parity also dedupes — first-write-wins).
    const seenIds = new Set<string>()
    const uniqueDetails: Record<string, any>[] = []
    for (const detail of details) {
      const id = detail.eval_summary_id
      if (seenIds.has(id)) continue
      seenIds.add(id)
      uniqueDetails.push(detail)
    }
    if (uniqueDetails.length < 2) continue

    const summaries = uniqueDetails.map((detail) => {
      const summary = hfEvalDetailToSummary(detail as any)
      return syncAttachBenchmarkCardToSummary(summary)
    })

    const aggregated = aggregateBenchmarkSummaries(summaries as any, suiteKey)
    if (!aggregated) continue
    aggregateById[aggregated.evaluation_id] = aggregated
  }

  dumped.push({
    surface: "aggregate_eval_summaries",
    by_id: aggregateById,
  })
}

// matrix_eval_summaries — port of the `matrix__<suite_key>` branch in
// `getEvalSummaryById`. Mirrors parity emitter `build_matrix_eval_summaries`
// (parity_outputs.py:261-281):
//   - skip details where `is_summary_score` is true
//   - group by `benchmark_family_key || benchmark_parent_key`
//   - call `buildSingleMetricSuiteMatrixSummary(details, suiteKey)`
// Keyed by `payload.evaluation_id` (= `matrix__<suite_key>`).
{
  const matrixGroups = new Map<string, Record<string, any>[]>()
  for (const detail of evalDetails) {
    if (detail.is_summary_score) continue
    const suiteKey =
      detail.benchmark_family_key || detail.benchmark_parent_key
    if (!suiteKey) continue
    const list = matrixGroups.get(String(suiteKey)) ?? []
    list.push(detail)
    matrixGroups.set(String(suiteKey), list)
  }

  const matrixById: Record<string, any> = {}
  for (const [suiteKey, details] of matrixGroups.entries()) {
    const result = buildSingleMetricSuiteMatrixSummary(details as any, suiteKey)
    if (!result) continue
    const attached = syncAttachBenchmarkCardToSummary(result)
    matrixById[attached.evaluation_id] = attached
  }

  dumped.push({
    surface: "matrix_eval_summaries",
    by_id: matrixById,
  })
}

const modelDetails: Array<Record<string, any>> = listJSONFiles(modelsDir).map((file) =>
  readJSON<Record<string, any>>(join(modelsDir, file))
)

dumped.push({
  surface: "model_summaries",
  by_id: Object.fromEntries(
    modelDetails.flatMap((detail) => {
      try {
        const evaluations = flattenModelEvaluations(detail as any)
        if (evaluations.length === 0) return []
        const payload = createModelFamilySummary(evaluations as any)
        return [[payload.model_route_id, payload]]
      } catch (error) {
        // The TS guard `assertSourceMetadata` throws when source_metadata
        // is missing on any model_result; surface as a parity-comparable
        // sentinel keyed by the canonical route id (lookup against the
        // canonical model_family_id avoids drift when the input file's
        // route_id was generated pre-canonicalization).
        const fallbackRoute = (detail.model_family_id ?? "").replace(/\//g, "__")
        return [[fallbackRoute || detail.model_route_id, { _adapter_error: String(error) }]]
      }
    })
  ),
})

// Developer surfaces — port of getDeveloperList / getDeveloperSummaryById.
// Both run hfDeveloperDetailToSummary against pipeline `developers/*.json`;
// the list endpoint then strips `models[]` to keep the index lightweight.
const developersDir = join(pipelineRoot, "developers")
const developerDetails: Array<Record<string, any>> = listJSONFiles(developersDir)
  .map((file) => readJSON<Record<string, any>>(join(developersDir, file)))
  .filter((detail) => detail && detail.developer && Array.isArray(detail.models))

const developerSummaries = developerDetails.map((detail) => hfDeveloperDetailToSummary(detail as any))

dumped.push({
  surface: "developer_summaries",
  by_id: Object.fromEntries(developerSummaries.map((s) => [s.route_id, s])),
})

dumped.push({
  surface: "developers",
  by_id: Object.fromEntries(
    developerSummaries.map((s) => {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { models, ...listEntry } = s
      return [listEntry.route_id, listEntry]
    })
  ),
})

// Stream surfaces individually — `JSON.stringify` of the full dump can
// exceed Node's max string length on production-scale corpora (~5.8k
// model_summaries with nested `evaluations_by_category`).
function streamSurface(handle: NodeJS.WritableStream, surface: DumpedSurface, isFirst: boolean) {
  if (!isFirst) handle.write(",")
  handle.write(`{"surface":${JSON.stringify(surface.surface)},"by_id":{`)
  let first = true
  for (const [key, value] of Object.entries(surface.by_id)) {
    if (!first) handle.write(",")
    first = false
    handle.write(JSON.stringify(key))
    handle.write(":")
    handle.write(JSON.stringify(value))
  }
  handle.write("}}")
}

async function emit(): Promise<void> {
  if (outPath) {
    const stream = createWriteStream(outPath)
    stream.write("[")
    dumped.forEach((surface, idx) => streamSurface(stream as any, surface, idx === 0))
    stream.write("]")
    await new Promise<void>((resolve) => {
      stream.end(() => resolve())
    })
    console.log(`Wrote ${dumped.length} surfaces to ${outPath}`)
  } else {
    dumped.forEach((surface, idx) =>
      streamSurface(process.stdout, surface, idx === 0)
    )
  }
}

await emit()
