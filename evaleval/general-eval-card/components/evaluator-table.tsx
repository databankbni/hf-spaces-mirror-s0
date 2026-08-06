"use client"

import Link from "next/link"
import { ArrowUpRight, ChevronDown, ChevronUp, ChevronsUpDown } from "lucide-react"

import { VerifiedBadge } from "@/components/signals/verified-badge"
import { isRecognizedEvaluator, type EvaluatorGroup } from "@/lib/evaluators"
import { cn } from "@/lib/utils"

export type EvaluatorTableSortCol = "name" | "evals" | "verified"

interface EvaluatorTableProps {
  rows: EvaluatorGroup[]
  sortCol: EvaluatorTableSortCol
  sortDir: "asc" | "desc"
  onSort: (col: EvaluatorTableSortCol) => void
  /** When true, the verified filter is active — propagate it into the link. */
  verifiedOnly?: boolean
}

export function EvaluatorTable({ rows, sortCol, sortDir, onSort, verifiedOnly }: EvaluatorTableProps) {
  function SortIcon({ col }: { col: EvaluatorTableSortCol }) {
    if (sortCol !== col) return <ChevronsUpDown className="h-3 w-3 opacity-30" aria-hidden />
    return sortDir === "asc"
      ? <ChevronUp className="h-3 w-3" aria-hidden />
      : <ChevronDown className="h-3 w-3" aria-hidden />
  }

  function SortTh({
    col,
    children,
    className,
    style,
  }: {
    col: EvaluatorTableSortCol
    children: React.ReactNode
    className?: string
    style?: React.CSSProperties
  }) {
    const active = sortCol === col
    return (
      <th
        className={className}
        style={{
          ...style,
          cursor: "pointer",
          userSelect: "none",
          color: active ? "var(--fg)" : undefined,
        }}
        onClick={() => onSort(col)}
      >
        <span className={cn("inline-flex items-center gap-1", className?.includes("num") && "justify-end")}>
          {children}
          <SortIcon col={col} />
        </span>
      </th>
    )
  }

  // The detail route always shows the org's full profile — the verified-only
  // list filter is intentionally not carried across (it changed nothing for
  // grey/recognized orgs and only narrowed blue mixed orgs, while the detail
  // header already reports total + verified counts side by side).
  const hrefFor = (slug: string) => `/evaluators/${slug}`

  return (
    <div className="overflow-x-auto">
      <table className="ec-htable">
        <thead>
          <tr>
            <SortTh col="name" style={{ width: "55%" }}>Evaluator</SortTh>
            <SortTh col="evals" className="num">Evaluations reported</SortTh>
            {/* In verified-only mode every (eval, org) membership is already
                verified, so verifiedCount === evalCount for every row — the
                two columns are identical. Drop the redundant Verified column
                there and keep it only when the counts can differ. */}
            {!verifiedOnly && <SortTh col="verified" className="num">Verified</SortTh>}
            <th style={{ width: 90 }} />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.slug}>
              <td>
                <Link href={hrefFor(row.slug)} className="block min-w-0 group">
                  <div className="flex items-center gap-1.5">
                    <span className="font-semibold text-[14px] text-[color:var(--fg)] group-hover:text-[color:var(--accent)] transition-colors">
                      {row.name}
                    </span>
                    <VerifiedBadge
                      verified={row.isVerified}
                      recognized={isRecognizedEvaluator(row.name)}
                      size="sm"
                    />
                  </div>
                </Link>
              </td>
              <td className="num font-mono text-[13px]">
                {verifiedOnly ? (
                  <span className="inline-flex items-center gap-1 text-[color:var(--accent)]">
                    {row.evalCount.toLocaleString()}
                    <VerifiedBadge verified size="sm" withTooltip={false} />
                  </span>
                ) : (
                  row.evalCount.toLocaleString()
                )}
              </td>
              {!verifiedOnly && (
                <td className="num font-mono text-[13px]">
                  {row.verifiedCount > 0 ? (
                    <span
                      className="inline-flex items-center gap-1"
                      style={{ color: row.isVerified ? "var(--accent)" : "var(--fg-muted)" }}
                    >
                      {row.verifiedCount.toLocaleString()}
                      <VerifiedBadge
                        verified={row.isVerified}
                        recognized={isRecognizedEvaluator(row.name)}
                        size="sm"
                        withTooltip={false}
                      />
                    </span>
                  ) : (
                    <span className="text-[color:var(--fg-subtle)]">—</span>
                  )}
                </td>
              )}
              <td>
                <Link
                  href={hrefFor(row.slug)}
                  className="font-mono text-[10px] tracking-[0.12em] uppercase text-[color:var(--accent)] hover:text-[color:var(--accent-hover)] inline-flex items-center gap-1"
                >
                  Open
                  <ArrowUpRight className="h-3 w-3" aria-hidden />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
