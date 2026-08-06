import type {
  BackendManifestStatus,
  ComparisonIndex,
  CorpusAggregates,
  EvalHierarchy,
  OrgMetadata,
  PeerRanksMap,
} from "@/lib/backend-artifacts"
import { decorateHierarchyDerivedTags } from "@/lib/benchmark-tags"
import type { BenchmarkEvaluationCardData } from "@/components/benchmark-evaluation-card"
import type { HFEvalDetail } from "@/lib/hf-data"
import type {
  BenchmarkCard,
  BenchmarkEvalListItem,
  BenchmarkEvalSummary,
  ModelEvaluationSummary,
} from "@/lib/eval-processing"

export interface EvalListResponse {
  evals: BenchmarkEvalListItem[]
  totalModels: number
}

export interface DeveloperListItem {
  developer: string
  route_id: string
  model_count: number
  benchmark_count: number
  evaluation_count: number
  popular_evals: Array<{
    benchmark: string
    model_count: number
  }>
}

export interface DeveloperSummaryResponse {
  developer: string
  route_id: string
  model_count: number
  benchmark_count: number
  evaluation_count: number
  popular_evals: Array<{
    benchmark: string
    model_count: number
  }>
  models: BenchmarkEvaluationCardData[]
}

async function fetchJson<T>(input: string): Promise<T> {
  const response = await fetch(input)

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }

  return response.json() as Promise<T>
}

export function fetchModelCards() {
  return fetchJson<BenchmarkEvaluationCardData[]>("/api/model-cards-lite")
}

export function fetchEvalList() {
  return fetchJson<EvalListResponse>("/api/eval-list-lite")
}

export function fetchModelSummary(modelId: string) {
  return fetchJson<ModelEvaluationSummary>(
    `/api/model-summary?id=${encodeURIComponent(modelId)}`
  )
}

export function fetchEvalSummary(evalId: string) {
  return fetchJson<BenchmarkEvalSummary>(
    `/api/eval-summary?id=${encodeURIComponent(evalId)}`
  )
}

export function fetchEvalDetail(evalId: string) {
  return fetchJson<HFEvalDetail>(
    `/api/eval-detail?id=${encodeURIComponent(evalId)}`
  )
}

export function fetchDevelopers() {
  return fetchJson<DeveloperListItem[]>("/api/developers")
}

export function fetchDeveloperSummary(developerId: string) {
  return fetchJson<DeveloperSummaryResponse>(
    `/api/developer-summary?id=${encodeURIComponent(developerId)}`
  )
}

export function fetchBenchmarkMetadata() {
  return fetchJson<Record<string, BenchmarkCard>>("/api/benchmark-metadata")
}

export function fetchBackendManifest() {
  return fetchJson<BackendManifestStatus>("/api/backend-manifest")
}

export function fetchEvalHierarchy() {
  return fetchJson<EvalHierarchy>("/api/eval-hierarchy").then(decorateHierarchyDerivedTags)
}

export function fetchComparisonIndex() {
  return fetchJson<ComparisonIndex>("/api/comparison-index")
}

export function fetchCorpusAggregates() {
  return fetchJson<CorpusAggregates>("/api/corpus-aggregates")
}

export function fetchPeerRanks() {
  return fetchJson<PeerRanksMap>("/api/peer-ranks")
}

export function fetchOrganizations() {
  return fetchJson<Record<string, OrgMetadata>>("/api/org-metadata")
}
