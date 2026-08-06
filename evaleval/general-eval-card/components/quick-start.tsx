"use client"

import { createContext, useContext, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  ArrowRight,
  BarChart3,
  BookOpen,
  Boxes,
  FlaskConical,
  Layers,
  MessageSquare,
  ShieldQuestion,
} from "lucide-react"

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog"
import { cn } from "@/lib/utils"

const STORAGE_KEY = "eval-cards-onboarding-seen"

interface QuickStartContextValue {
  /** Open the welcome tour (used by the footer + Help page "replay" links). */
  open: () => void
}

const QuickStartContext = createContext<QuickStartContextValue | null>(null)

interface Slide {
  icon: React.ComponentType<{ className?: string }>
  kicker: string
  title: string
  body: string
  /** Optional in-slide call-to-action link (e.g. the Beta feedback slide). */
  link?: { href: string; label: string }
}

const SLIDES: Slide[] = [
  {
    icon: BookOpen,
    kicker: "Welcome",
    title: "What this is",
    body: "Evaluation Cards collects how AI models have been tested across lots of benchmarks. A single score rarely tells you much on its own, so we give you everything you need to read one: the evaluation results, the benchmark's metadata, how the run was set up, and our interpretive signals. And unlike any other artifact out there, you can see those results reported side by side, which makes them easy to compare.",
  },
  {
    icon: Layers,
    kicker: "Reader modes",
    title: "Two ways to read",
    body: "Use the toggle in the top bar to switch views. Research shows the methodology: the settings, the configs, and what's missing. Summary keeps it plain. Either way you're looking at the same data.",
  },
  {
    icon: BarChart3,
    kicker: "Signals",
    title: "Four things we check",
    body: "Each result is scored on four things: whether it can be reproduced, how complete it is, where it came from, and whether it's fair to compare with other scores. Together they tell you how much to trust a number.",
  },
  {
    icon: Boxes,
    kicker: "Models",
    title: "The Models tab",
    body: "This is every model we track. Search or sort by developer, size, or release date, open one to see its full page, and pick up to four to compare.",
  },
  {
    icon: FlaskConical,
    kicker: "Evaluations",
    title: "The Evaluations tab",
    body: "Here you'll find the benchmarks, grouped from broad families down to single metrics. Filter by risk area or agentic tasks, and open any benchmark to see what it tests, where it falls short, and who's reported results on it.",
  },
  {
    icon: MessageSquare,
    kicker: "Beta",
    title: "We're in Beta — tell us what you think",
    body: "Evaluation Cards is new and still evolving. Found a bug, want a feature, or hit something confusing? We'd genuinely love to hear it. You can reach the feedback form from any page via Feedback in the top bar.",
    link: { href: "/feedback", label: "Send feedback" },
  },
  {
    icon: ShieldQuestion,
    kicker: "How we handle gaps",
    title: "We don't fill in the blanks",
    body: "If something wasn't reported, we leave it blank instead of guessing or estimating. A missing safety test tells you something too, so we'd rather show the gap than hide it.",
  },
]

export function QuickStartProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  const pathname = usePathname()

  // Auto-open on a visitor's first time, mirroring the audience-mode pattern.
  useEffect(() => {
    // Embed surfaces never get the tour. Two independent guards:
    //  1. Route-based — anything under /embed/* is a self-contained card meant
    //     for iframing, so the tour must not appear even if the URL is opened
    //     directly as a top-level tab (e.g. a "preview" link).
    //  2. Frame-based — when iframed, storage partitioning means the seen-flag
    //     can't persist, so the tour would replay on every load.
    if (pathname?.startsWith("/embed")) return
    if (window.self !== window.top) return
    try {
      if (!window.localStorage.getItem(STORAGE_KEY)) {
        setOpen(true)
      }
    } catch {
      // localStorage unavailable (e.g. privacy mode) — skip the tour silently.
    }
  }, [pathname])

  const markSeen = () => {
    try {
      window.localStorage.setItem(STORAGE_KEY, "1")
    } catch {
      // ignore
    }
  }

  const handleOpenChange = (next: boolean) => {
    setOpen(next)
    if (!next) markSeen()
  }

  const value = useMemo<QuickStartContextValue>(() => ({ open: () => setOpen(true) }), [])

  return (
    <QuickStartContext.Provider value={value}>
      {children}
      <QuickStartDialog open={open} onOpenChange={handleOpenChange} />
    </QuickStartContext.Provider>
  )
}

export function useQuickStart(): QuickStartContextValue {
  const context = useContext(QuickStartContext)
  if (!context) {
    throw new Error("useQuickStart must be used within a QuickStartProvider")
  }
  return context
}

function QuickStartDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (next: boolean) => void
}) {
  const [step, setStep] = useState(0)

  // Reset to the first slide whenever the dialog is (re)opened.
  useEffect(() => {
    if (open) setStep(0)
  }, [open])

  const slide = SLIDES[step]
  const Icon = slide.icon
  const isLast = step === SLIDES.length - 1

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="gap-0 p-0 sm:max-w-[480px]">
        <div className="p-7">
          <div className="mb-5 flex h-11 w-11 items-center justify-center border border-[color:var(--border-soft)] bg-[color:var(--bg-warm)]">
            <Icon className="h-5 w-5 text-[color:var(--accent)]" />
          </div>
          <div className="kicker mb-2">{slide.kicker}</div>
          <DialogTitle className="text-[22px] font-semibold tracking-[-0.01em] text-[color:var(--fg)]">
            {slide.title}
          </DialogTitle>
          <DialogDescription className="mt-2.5 text-[15px] leading-[1.65] text-[color:var(--fg-muted)]">
            {slide.body}
          </DialogDescription>

          {slide.link && (
            <div className="mt-5">
              <Link
                href={slide.link.href}
                className="btn-ec"
                onClick={() => onOpenChange(false)}
              >
                {slide.link.label}
                <ArrowRight className="h-3.5 w-3.5" aria-hidden />
              </Link>
            </div>
          )}

          {isLast && (
            <div className="mt-5 flex flex-wrap gap-2.5">
              <Link href="/models" className="btn-ec" onClick={() => onOpenChange(false)}>
                Explore models
                <ArrowRight className="h-3.5 w-3.5" aria-hidden />
              </Link>
              <Link href="/evals" className="btn-ec outline" onClick={() => onOpenChange(false)}>
                Explore evaluations
                <ArrowRight className="h-3.5 w-3.5" aria-hidden />
              </Link>
            </div>
          )}
        </div>

        {/* Footer: progress dots + navigation */}
        <div className="flex items-center justify-between border-t border-[color:var(--border-soft)] px-7 py-4">
          <div className="flex items-center gap-1.5" aria-hidden>
            {SLIDES.map((_, i) => (
              <span
                key={i}
                className={cn(
                  "h-1.5 w-1.5 rounded-full transition-colors",
                  i === step ? "bg-[color:var(--fg)]" : "bg-[color:var(--border-strong)]"
                )}
              />
            ))}
          </div>

          <div className="flex items-center gap-2">
            {step > 0 ? (
              <button
                type="button"
                className="btn-ec ghost"
                onClick={() => setStep((s) => Math.max(0, s - 1))}
              >
                Back
              </button>
            ) : (
              <button type="button" className="btn-ec ghost" onClick={() => onOpenChange(false)}>
                Skip
              </button>
            )}

            {isLast ? (
              <Link href="/help" className="btn-ec" onClick={() => onOpenChange(false)}>
                Open the full guide
                <ArrowRight className="h-3.5 w-3.5" aria-hidden />
              </Link>
            ) : (
              <button
                type="button"
                className="btn-ec"
                onClick={() => setStep((s) => Math.min(SLIDES.length - 1, s + 1))}
              >
                Next
                <ArrowRight className="h-3.5 w-3.5" aria-hidden />
              </button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
