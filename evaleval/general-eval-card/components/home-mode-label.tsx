"use client"

import { useAudienceMode } from "@/components/audience-mode-provider"

export function HomeModeLabel() {
  const { mode } = useAudienceMode()

  return <span>{mode === "research" ? "Research reader mode" : "Policy reader mode"}</span>
}