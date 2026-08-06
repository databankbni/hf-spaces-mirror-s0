"use client"

import { ArrowUpRight } from "lucide-react"
import { cn } from "@/lib/utils"
import type { EvalTag } from "@/lib/benchmark-schema"

export interface EvalNodeTableRow {
  id: string
  title: string
  kind: string
  kindLabel: string
  category: EvalTag
  familyLabel?: string
  suiteLabel?: string
  description: string
  modelsCount: number
  metricCount: number
  childCount: number
  isNavigable: boolean
  actionLabel: string
  domains: string[]
  completenessScore?: number
}

interface EvalNodeTableProps {
  rows: EvalNodeTableRow[]
  onOpen: (id: string) => void
}

const CATEGORY_DOT: Record<string, string> = {
  General: "bg-sky-400",
  Reasoning: "bg-violet-400",
  Agentic: "bg-amber-400",
  Safety: "bg-rose-400",
  Code: "bg-emerald-400",
  Math: "bg-indigo-400",
  Multilingual: "bg-teal-400",
}

export function EvalNodeTable({ rows, onOpen }: EvalNodeTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="ec-htable">
        <thead>
          <tr>
            <th style={{ width: "32%" }}>Node</th>
            <th>Lineage</th>
            <th>Kind</th>
            <th className="num">Children</th>
            <th className="num">Models</th>
            <th className="num">Metrics</th>
            <th style={{ width: "16%" }}>Completeness</th>
            <th style={{ width: 90 }} />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const completenessPct =
              row.completenessScore != null
                ? Math.round(row.completenessScore * 100)
                : null
            const dotClass = CATEGORY_DOT[row.category] ?? "bg-stone-400"

            return (
              <tr
                key={row.id}
                onClick={() => row.isNavigable && onOpen(row.id)}
                style={{ cursor: row.isNavigable ? "pointer" : "default" }}
                aria-disabled={!row.isNavigable}
              >
                <td>
                  <div className="flex items-start gap-2.5 min-w-0">
                    <span
                      className={cn(
                        "shrink-0 mt-1.5 h-2 w-2 rounded-full",
                        dotClass
                      )}
                      aria-hidden
                    />
                    <div className="min-w-0">
                      <div className="font-semibold text-[14px] text-[color:var(--fg)] truncate">
                        {row.title}
                      </div>
                      {row.description && (
                        <div className="mt-1 text-[12px] leading-[1.5] text-[color:var(--fg-muted)] line-clamp-2">
                          {row.description}
                        </div>
                      )}
                    </div>
                  </div>
                </td>
                <td className="text-[12px] text-[color:var(--fg-muted)]">
                  {row.familyLabel && (
                    <div className="font-mono uppercase tracking-[0.06em] text-[10px] text-[color:var(--fg-subtle)] truncate">
                      {row.familyLabel}
                    </div>
                  )}
                  {row.suiteLabel && (
                    <div className="text-[12px] text-[color:var(--fg-muted)] truncate">
                      {row.suiteLabel}
                    </div>
                  )}
                  {!row.familyLabel && !row.suiteLabel && (
                    <span className="text-[color:var(--fg-subtle)]">—</span>
                  )}
                </td>
                <td>
                  <span className="inline-flex items-center font-mono text-[10px] uppercase tracking-[0.12em] text-[color:var(--fg)] border border-[color:var(--border-soft)] bg-[color:var(--bg)] px-2 py-0.5">
                    {row.kindLabel}
                  </span>
                </td>
                <td className="num font-mono text-[13px]">
                  {row.childCount > 0 ? row.childCount.toLocaleString() : "—"}
                </td>
                <td className="num font-mono text-[13px]">
                  {row.modelsCount.toLocaleString()}
                </td>
                <td className="num font-mono text-[13px]">
                  {row.metricCount.toLocaleString()}
                </td>
                <td>
                  {completenessPct != null ? (
                    <div className="flex items-center gap-2">
                      <div className="relative h-1.5 flex-1 bg-[color:var(--bg-surface)]">
                        <div
                          className="absolute left-0 top-0 bottom-0 bg-[color:var(--fg)] motion-academic-progress"
                          style={{ width: `${completenessPct}%` }}
                        />
                      </div>
                      <span className="font-mono text-[11px] text-[color:var(--fg)] tabular-nums w-9 text-right">
                        {completenessPct}%
                      </span>
                    </div>
                  ) : (
                    <span className="font-mono text-[11px] text-[color:var(--fg-subtle)]">
                      —
                    </span>
                  )}
                </td>
                <td>
                  {row.isNavigable && (
                    <span
                      className="font-mono text-[10px] tracking-[0.12em] uppercase text-[color:var(--accent)] inline-flex items-center gap-1"
                    >
                      Open
                      <ArrowUpRight className="h-3 w-3" aria-hidden />
                    </span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
