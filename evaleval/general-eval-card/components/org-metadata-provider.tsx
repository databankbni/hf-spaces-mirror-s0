"use client"

import { createContext, useContext, useMemo } from "react"

import { evaluatorSlugFor, type OrgMetaMap } from "@/lib/evaluators"

/**
 * Makes the per-org registry metadata (from the organizations.json sidecar)
 * available app-wide, keyed by normalizeOrgKey(displayName). It carries each
 * org's stable canonical `id`, which is what evaluator URLs are slugged from —
 * so renaming an org's display name never changes its /evaluators/<slug> URL.
 *
 * Fetched once server-side in the root layout and handed down as a plain
 * (serializable) object, so the slug is correct on first render with no flash.
 */
const OrgMetadataContext = createContext<OrgMetaMap>({})

export function OrgMetadataProvider({
  value,
  children,
}: {
  value: OrgMetaMap
  children: React.ReactNode
}) {
  return <OrgMetadataContext.Provider value={value ?? {}}>{children}</OrgMetadataContext.Provider>
}

/** Raw display→metadata map (homepage url, logo, canonical id). */
export function useOrgMetadata(): OrgMetaMap {
  return useContext(OrgMetadataContext)
}

/**
 * Returns the canonical, rename-stable slug function bound to the current org
 * metadata. Use this everywhere an /evaluators/<slug> link is built so the
 * whole app agrees on one URL per org.
 */
export function useEvaluatorSlug(): (name: string) => string {
  const orgMeta = useContext(OrgMetadataContext)
  return useMemo(() => (name: string) => evaluatorSlugFor(name, orgMeta), [orgMeta])
}
