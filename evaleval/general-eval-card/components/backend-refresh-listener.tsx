"use client"

import { useEffect, useRef } from "react"

import type { BackendManifestStatus } from "@/lib/backend-artifacts"

const POLL_INTERVAL_MS = 30_000

async function fetchManifestStatus(signal: AbortSignal): Promise<BackendManifestStatus | null> {
  try {
    const response = await fetch("/api/backend-manifest", {
      cache: "no-store",
      signal,
    })

    if (!response.ok) {
      return null
    }

    return (await response.json()) as BackendManifestStatus
  } catch {
    return null
  }
}

export function BackendRefreshListener() {
  const initialSignatureRef = useRef<string | null>(null)
  const reloadingRef = useRef(false)

  useEffect(() => {
    let disposed = false

    const checkForRefresh = async () => {
      if (disposed || reloadingRef.current || document.hidden) {
        return
      }

      const controller = new AbortController()
      const status = await fetchManifestStatus(controller.signal)
      if (disposed || !status) {
        return
      }

      const currentSignature = status.currentManifestSignature
      if (!initialSignatureRef.current && currentSignature) {
        initialSignatureRef.current = currentSignature
        return
      }

      if (
        initialSignatureRef.current &&
        currentSignature &&
        currentSignature !== initialSignatureRef.current &&
        status.latestManifestSignature === currentSignature &&
        !status.refreshing
      ) {
        reloadingRef.current = true
        window.location.reload()
      }
    }

    const intervalId = window.setInterval(() => {
      void checkForRefresh()
    }, POLL_INTERVAL_MS)

    const handleVisibilityOrFocus = () => {
      void checkForRefresh()
    }

    void checkForRefresh()
    document.addEventListener("visibilitychange", handleVisibilityOrFocus)
    window.addEventListener("focus", handleVisibilityOrFocus)

    return () => {
      disposed = true
      window.clearInterval(intervalId)
      document.removeEventListener("visibilitychange", handleVisibilityOrFocus)
      window.removeEventListener("focus", handleVisibilityOrFocus)
    }
  }, [])

  return null
}