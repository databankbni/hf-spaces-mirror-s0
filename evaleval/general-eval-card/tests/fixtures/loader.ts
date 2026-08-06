import { readFileSync, readdirSync } from "fs"
import { fileURLToPath } from "url"
import path from "path"

import manifest from "./manifest.json"

const FIXTURES_DIR = path.dirname(fileURLToPath(import.meta.url))

export type FixtureGroup = "evals" | "models" | "developers" | "model_cards"

const GROUP_DIRS: Record<FixtureGroup, string> = {
  evals: "evals",
  models: "models",
  developers: "developers",
  model_cards: "model-cards",
}

export interface FixtureEntry {
  id: string
  why: string
}

export function fixtureEntries(group: FixtureGroup): FixtureEntry[] {
  return (manifest as Record<FixtureGroup, FixtureEntry[]>)[group]
}

export function loadFixture<T>(group: FixtureGroup, id: string): T {
  const filePath = path.join(FIXTURES_DIR, GROUP_DIRS[group], `${id}.json`)
  return JSON.parse(readFileSync(filePath, "utf8")) as T
}

export function loadAllFixtures<T>(group: FixtureGroup): Array<{ id: string; why: string; data: T }> {
  return fixtureEntries(group).map((entry) => ({
    id: entry.id,
    why: entry.why,
    data: loadFixture<T>(group, entry.id),
  }))
}

export function listLiveCacheFiles(group: FixtureGroup): string[] {
  const dir = path.resolve(FIXTURES_DIR, "..", "..", ".cache", "hf-data", group)
  try {
    return readdirSync(dir).filter((f) => f.endsWith(".json"))
  } catch {
    return []
  }
}

export function loadLiveCacheFile<T>(group: FixtureGroup, fileName: string): T {
  const filePath = path.resolve(FIXTURES_DIR, "..", "..", ".cache", "hf-data", group, fileName)
  return JSON.parse(readFileSync(filePath, "utf8")) as T
}

// Walks every model_result row inside an HFModelDetail's hierarchy_by_category.
// Used by both the fixture contracts and the live-cache drift checks. Generic
// in the result type so callers can pass a precise type from lib/hf-data.ts.
export function* walkHierarchyResults<TResult>(
  detail: HierarchyDetail<TResult>,
  fixtureId: string
): Generator<{ result: TResult; path: string }> {
  for (const [categoryKey, nodes] of Object.entries(detail.hierarchy_by_category ?? {})) {
    for (const [nodeIdx, node] of (nodes ?? []).entries()) {
      yield* walkNode<TResult>(node, `${fixtureId}.hierarchy_by_category.${categoryKey}[${nodeIdx}]`)
    }
  }
}

interface HierarchyDetail<TResult> {
  hierarchy_by_category?: Record<string, HierarchyNode<TResult>[]>
}

interface HierarchyNode<TResult> {
  metrics?: Array<{ model_results?: TResult[] }>
  subtasks?: HierarchyNode<TResult>[]
}

function* walkNode<TResult>(
  node: HierarchyNode<TResult>,
  basePath: string
): Generator<{ result: TResult; path: string }> {
  for (const [metricIdx, metric] of (node.metrics ?? []).entries()) {
    for (const [resultIdx, result] of (metric.model_results ?? []).entries()) {
      yield {
        result,
        path: `${basePath}.metrics[${metricIdx}].model_results[${resultIdx}]`,
      }
    }
  }
  for (const [subtaskIdx, subtask] of (node.subtasks ?? []).entries()) {
    yield* walkNode<TResult>(subtask, `${basePath}.subtasks[${subtaskIdx}]`)
  }
}
