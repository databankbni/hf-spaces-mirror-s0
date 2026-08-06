"use client"

import Link from "next/link"
import { ArrowUpRight, ChevronDown, ChevronUp, ChevronsUpDown } from "lucide-react"

import type { DeveloperListItem } from "@/lib/dashboard-data-client"
import { cn, routeIdToPath } from "@/lib/utils"

export type DeveloperTableSortCol =
  | "name"
  | "models"
  | "benchmarks"
  | "results"

interface DeveloperTableProps {
  rows: DeveloperListItem[]
  sortCol: DeveloperTableSortCol
  sortDir: "asc" | "desc"
  onSort: (col: DeveloperTableSortCol) => void
}

export function DeveloperTable({ rows, sortCol, sortDir, onSort }: DeveloperTableProps) {
  function SortIcon({ col }: { col: DeveloperTableSortCol }) {
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
    col: DeveloperTableSortCol
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

  return (
    <div className="overflow-x-auto">
      <table className="ec-htable">
        <thead>
          <tr>
            <SortTh col="name" style={{ width: "32%" }}>Developer</SortTh>
            <SortTh col="models" className="num">Models</SortTh>
            <SortTh col="benchmarks" className="num">Benchmarks</SortTh>
            <SortTh col="results" className="num">Reported results</SortTh>
            <th style={{ width: 90 }} />
          </tr>
        </thead>
        <tbody>
          {rows.map((dev) => {
            return (
              <tr key={dev.route_id}>
                <td>
                  <Link
                    href={`/developers/${routeIdToPath(dev.route_id)}`}
                    className="block min-w-0 group"
                  >
                    <div className="font-semibold text-[14px] text-[color:var(--fg)] group-hover:text-[color:var(--accent)] transition-colors">
                      {dev.developer}
                    </div>
                  </Link>
                </td>
                <td className="num font-mono text-[13px]">
                  {dev.model_count.toLocaleString()}
                </td>
                <td className="num font-mono text-[13px]">
                  {dev.benchmark_count.toLocaleString()}
                </td>
                <td className="num font-mono text-[13px]">
                  {dev.evaluation_count.toLocaleString()}
                </td>
                <td>
                  <Link
                    href={`/developers/${routeIdToPath(dev.route_id)}`}
                    className="font-mono text-[10px] tracking-[0.12em] uppercase text-[color:var(--accent)] hover:text-[color:var(--accent-hover)] inline-flex items-center gap-1"
                  >
                    Open
                    <ArrowUpRight className="h-3 w-3" aria-hidden />
                  </Link>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
