"use client"

import type { ReactNode } from "react"
import { useAudienceMode } from "@/components/audience-mode-provider"

interface ModeSwitchProps {
  research?: ReactNode
  policy?: ReactNode
}

/**
 * Renders different content per audience mode. Use this instead of inline
 * `mode === "research"` checks so that call sites stay readable and the
 * two branches stay obviously parallel.
 */
export function ModeSwitch({ research, policy }: ModeSwitchProps) {
  const { mode } = useAudienceMode()
  return <>{mode === "research" ? research ?? null : policy ?? null}</>
}

/**
 * Hook variant for cases where ModeSwitch can't be used (e.g. choosing
 * between two non-JSX values like a className or a number).
 */
export function useModeValue<T>(values: { research: T; policy: T }): T {
  const { mode } = useAudienceMode()
  return mode === "research" ? values.research : values.policy
}
