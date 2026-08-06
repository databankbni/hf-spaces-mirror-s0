"use client"

import { Play } from "lucide-react"

import { useQuickStart } from "@/components/quick-start"
import { cn } from "@/lib/utils"

export function ReplayIntroButton({ className }: { className?: string }) {
  const { open } = useQuickStart()
  return (
    <button type="button" onClick={open} className={cn("btn-ec outline", className)}>
      <Play className="h-3.5 w-3.5" aria-hidden />
      Replay the intro
    </button>
  )
}
