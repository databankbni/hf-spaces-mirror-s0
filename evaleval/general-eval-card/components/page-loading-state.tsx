"use client"

// TODO: check if deprecated. No references in app/, components/, lib/, or
// tests/ — could be intended for a future page/route, or safe to delete.

import { useEffect, useMemo, useState } from "react"

import { cn } from "@/lib/utils"

export interface PageLoadingStage {
  label: string
  done: boolean
}

interface PageLoadingStateProps {
  title: string
  description?: string
  stages: PageLoadingStage[]
  className?: string
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function getTargetProgress(completedStages: number, totalStages: number) {
  const start = 12
  const ceiling = 94

  if (totalStages <= 0) {
    return start
  }

  const stageWidth = (ceiling - start) / totalStages
  const hardTarget = start + completedStages * stageWidth

  if (completedStages >= totalStages) {
    return 100
  }

  return Math.min(ceiling, hardTarget + Math.min(stageWidth * 0.35, 12))
}

export function PageLoadingState({ title, description, stages, className }: PageLoadingStateProps) {
  const safeStages = stages.length > 0 ? stages : [{ label: "Loading", done: false }]

  const { completedStages, currentStageLabel, targetProgress } = useMemo(() => {
    const completed = safeStages.filter((stage) => stage.done).length
    const currentStage = safeStages.find((stage) => !stage.done)?.label ?? "Finalizing"

    return {
      completedStages: completed,
      currentStageLabel: currentStage,
      targetProgress: getTargetProgress(completed, safeStages.length),
    }
  }, [safeStages])

  const [displayProgress, setDisplayProgress] = useState(() => clamp(targetProgress, 0, 100))

  useEffect(() => {
    setDisplayProgress((current) => {
      if (targetProgress < current) {
        return clamp(targetProgress, 0, 100)
      }

      return current
    })
  }, [targetProgress])

  useEffect(() => {
    if (Math.abs(displayProgress - targetProgress) < 0.5) {
      if (displayProgress !== targetProgress) {
        setDisplayProgress(targetProgress)
      }
      return
    }

    const interval = window.setInterval(() => {
      setDisplayProgress((current) => {
        const difference = targetProgress - current
        if (Math.abs(difference) < 0.5) {
          return targetProgress
        }

        const increment =
          difference > 18 ? 6 : difference > 10 ? 4 : difference > 4 ? 2 : 1

        return clamp(current + increment, 0, targetProgress)
      })
    }, 110)

    return () => {
      window.clearInterval(interval)
    }
  }, [displayProgress, targetProgress])

  const progressStyle = {
    background: `conic-gradient(from 180deg, hsl(var(--primary)) 0deg ${displayProgress * 3.6}deg, hsl(var(--border)) ${displayProgress * 3.6}deg 360deg)`,
  }

  return (
    <div className={cn("flex min-h-[20rem] items-center justify-center px-4", className)}>
      <section className="flex w-full max-w-md flex-col items-center gap-5 rounded-[1.75rem] border border-border/60 bg-background/95 px-6 py-8 text-center shadow-[0_24px_70px_-52px_rgba(15,23,42,0.5)] backdrop-blur">
        <div className="relative flex h-28 w-28 items-center justify-center rounded-full" style={progressStyle}>
          <div className="flex h-[5.4rem] w-[5.4rem] items-center justify-center rounded-full border border-border/60 bg-background text-2xl font-semibold tracking-tight text-foreground tabular-nums">
            {Math.round(displayProgress)}%
          </div>
        </div>

        <div className="space-y-1.5">
          <h2 className="text-xl font-semibold tracking-tight text-foreground sm:text-2xl">{title}</h2>
          {description ? (
            <p className="text-sm leading-6 text-muted-foreground">{description}</p>
          ) : null}
        </div>

        <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-muted-foreground">
          {currentStageLabel} · {completedStages}/{safeStages.length} ready
        </p>
      </section>
    </div>
  )
}