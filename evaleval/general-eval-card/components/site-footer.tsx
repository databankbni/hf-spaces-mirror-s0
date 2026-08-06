"use client"

import Link from "next/link"

import { useQuickStart } from "@/components/quick-start"

export function SiteFooter() {
  const { open } = useQuickStart()

  return (
    <footer className="border-t border-[color:var(--border-soft)] bg-[color:var(--bg-warm)]">
      <div className="mx-auto flex w-full max-w-[96rem] flex-col gap-3 px-4 py-6 sm:flex-row sm:items-center sm:justify-between sm:px-8">
        <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-[color:var(--fg-subtle)]">
          Evaluation Cards · EvalEval Coalition
        </span>
        <nav className="flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-[11px] uppercase tracking-[0.12em] text-[color:var(--fg-muted)]">
          <Link href="/about" className="transition-colors hover:text-[color:var(--fg)]">
            About
          </Link>
          <Link href="/help" className="transition-colors hover:text-[color:var(--fg)]">
            Help
          </Link>
          <Link
            href="/help#how-to-contribute"
            className="transition-colors hover:text-[color:var(--fg)]"
          >
            How to contribute
          </Link>
          <Link
            href="/about#how-to-cite"
            className="transition-colors hover:text-[color:var(--fg)]"
          >
            How to cite
          </Link>
          <Link href="/feedback" className="transition-colors hover:text-[color:var(--fg)]">
            Feedback
          </Link>
          <a
            href="https://arxiv.org/abs/2606.09809"
            target="_blank"
            rel="noreferrer"
            className="transition-colors hover:text-[color:var(--fg)]"
          >
            Paper
          </a>
          <button
            type="button"
            onClick={open}
            className="uppercase tracking-[0.12em] transition-colors hover:text-[color:var(--fg)]"
          >
            Replay intro
          </button>
        </nav>
      </div>
    </footer>
  )
}
