"use client"

import type { ReactNode } from "react"
import * as TooltipPrimitive from "@radix-ui/react-tooltip"

import { cn } from "@/lib/utils"

export function SignalTooltip({
  children,
  content,
  contentClassName,
}: {
  children: ReactNode
  content: ReactNode
  /** Per-instance overrides for the tooltip box (e.g. tighter one-line copy). */
  contentClassName?: string
}) {
  return (
    <TooltipPrimitive.Provider delayDuration={150}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            side="top"
            align="center"
            sideOffset={8}
            className={cn(
              "z-50 max-w-80 rounded-md border border-border/70 bg-popover px-3 py-2 text-xs leading-5 text-popover-foreground shadow-lg",
              contentClassName,
            )}
          >
            {content}
            <TooltipPrimitive.Arrow className="fill-popover" />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  )
}
