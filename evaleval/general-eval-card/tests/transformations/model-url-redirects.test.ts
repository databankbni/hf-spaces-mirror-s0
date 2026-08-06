import { describe, expect, it } from "vitest"

import {
  buildRedirectsFromModelsView,
  routeId,
  serializeRedirectModule,
  type ModelsViewRow,
} from "@/lib/model-url-redirects-build"
import { resolveModelRedirect } from "@/lib/model-url-redirects"
import { routeIdFromModelId, routeIdToPath } from "@/lib/utils"

// model-resolution-rework — executable spec for the model-URL redirect layer.
//
// Covers the two CRITICAL contract points the playbook calls out:
//   1. percent-encode / round-trip of model ids (RFC 3986, `/` -> %2F).
//   2. query-param preservation across the 301 (asserted via the middleware's
//      target-URL construction, replicated here to stay node-only / no Next
//      runtime).

// ---------------------------------------------------------------------------
// Percent-encoding round-trip
// ---------------------------------------------------------------------------

describe("route id percent-encoding round-trips", () => {
  const ids = [
    "anthropic/claude-3.5-sonnet-20240620",
    "meta/Llama-3.1-8B",
    "01-ai/Yi-1.5-34B",
    "EleutherAI/pythia-6.9b",
    "ByteDance-Seed/Seed-OSS-36B-Instruct",
    "openai/gpt-4o",
    "mistralai/mistral-7b-instruct-v0.3",
  ]

  it.each(ids)("encode→decode is identity for %s", (id) => {
    const encoded = routeIdFromModelId(id)
    // No bare slashes survive encoding (single-segment route id form).
    expect(encoded).not.toContain("/")
    // Full round-trip back to the original id.
    expect(decodeURIComponent(encoded)).toBe(id)
  })

  it("routeIdToPath turns the encoded form back into a slash path", () => {
    const encoded = routeIdFromModelId("anthropic/claude-3.5-sonnet-20240620")
    expect(encoded).toBe("anthropic%2Fclaude-3.5-sonnet-20240620")
    expect(routeIdToPath(encoded)).toBe("anthropic/claude-3.5-sonnet-20240620")
  })

  it("routeIdFromModelId trims and tolerates empty/nullish", () => {
    expect(routeIdFromModelId("  openai/gpt-4o  ")).toBe("openai%2Fgpt-4o")
    expect(routeIdFromModelId(undefined)).toBe("")
    expect(routeIdFromModelId(null)).toBe("")
    expect(routeIdFromModelId("")).toBe("")
  })

  it("casing is preserved through encoding (HF ids are case-sensitive)", () => {
    expect(routeIdFromModelId("meta/Llama-3.1-8B")).toBe("meta%2FLlama-3.1-8B")
    expect(routeIdFromModelId("meta/llama-3.1-8b")).not.toBe(
      routeIdFromModelId("meta/Llama-3.1-8B"),
    )
  })
})

// ---------------------------------------------------------------------------
// buildRedirectsFromModelsView — map construction from the warehouse
// ---------------------------------------------------------------------------

describe("buildRedirectsFromModelsView", () => {
  it("maps a folded raw spelling to its owning group route", () => {
    const rows: ModelsViewRow[] = [
      {
        model_route_id: "mistralai%2Fmistral-medium",
        model_id: "mistralai/mistral-medium",
        route_id: "mistralai%2Fmistral-medium",
        model_key: "mistralai/mistral-medium",
        model_group_id: "mistralai/mistral-medium",
        raw_model_ids: ["mistralai/mistral-medium-2505", "mistralai/Mistral-Medium"],
      },
    ]
    const { redirects } = buildRedirectsFromModelsView(rows)
    expect(redirects.get(routeId("mistralai/mistral-medium-2505"))).toBe("mistralai%2Fmistral-medium")
    expect(redirects.get(routeId("mistralai/Mistral-Medium"))).toBe("mistralai%2Fmistral-medium")
  })

  it("never redirects an addressable id — no group->leaf hijack", () => {
    const rows: ModelsViewRow[] = [
      {
        model_route_id: "mistralai%2Fmistral-medium",
        model_id: "mistralai/mistral-medium",
        // the group's own id appearing in its raw list must NOT become a redirect
        raw_model_ids: ["mistralai/mistral-medium"],
      },
    ]
    const { redirects } = buildRedirectsFromModelsView(rows)
    expect(redirects.size).toBe(0)
  })

  it("every redirect target is an addressable model_route_id", () => {
    const rows: ModelsViewRow[] = [
      { model_route_id: "org%2Fgroup-a", model_id: "org/group-a", raw_model_ids: ["org/snap-1"] },
      { model_route_id: "org%2Fgroup-b", model_id: "org/group-b", raw_model_ids: ["org/snap-2"] },
    ]
    const { redirects } = buildRedirectsFromModelsView(rows)
    const addressable = new Set(rows.map((r) => r.model_route_id))
    for (const target of redirects.values()) {
      expect(addressable.has(target)).toBe(true)
    }
  })

  it("excludes (does not arbitrarily pick) a spelling that fans out to multiple groups", () => {
    const rows: ModelsViewRow[] = [
      { model_route_id: "org%2Fgroup-a", model_id: "org/group-a", raw_model_ids: ["org/shared"] },
      { model_route_id: "org%2Fgroup-b", model_id: "org/group-b", raw_model_ids: ["org/shared"] },
    ]
    const { redirects, ambiguous } = buildRedirectsFromModelsView(rows)
    expect(redirects.has(routeId("org/shared"))).toBe(false)
    expect(ambiguous.get(routeId("org/shared"))?.size).toBe(2)
  })

  it("is idempotent when the same spelling appears repeatedly", () => {
    const rows: ModelsViewRow[] = [
      { model_route_id: "org%2Fg", model_id: "org/g", raw_model_ids: ["org/snap", "org/snap"] },
    ]
    const { redirects } = buildRedirectsFromModelsView(rows)
    expect(redirects.size).toBe(1)
    expect(redirects.get(routeId("org/snap"))).toBe("org%2Fg")
  })
})

// ---------------------------------------------------------------------------
// serializeRedirectModule — generated source shape
// ---------------------------------------------------------------------------

describe("serializeRedirectModule", () => {
  it("produces sorted, parseable entries derived from the warehouse", () => {
    const map = new Map([
      ["b%2Fx", "b%2Fy"],
      ["a%2Fx", "a%2Fy"],
    ])
    const src = serializeRedirectModule(map, { source: "warehouse/test" })
    expect(src).toContain("Derived from the warehouse")
    // sorted: a before b
    expect(src.indexOf('"a%2Fx"')).toBeLessThan(src.indexOf('"b%2Fx"'))
    expect(src).toContain("export const MODEL_URL_REDIRECTS")
    expect(src).toContain("export function resolveModelRedirect")
  })
})

// ---------------------------------------------------------------------------
// Redirect target construction — query-param preservation (CRITICAL)
// ---------------------------------------------------------------------------
//
// Replicates the middleware target-building logic against a real URL so we
// assert the 301 contract without booting the Next runtime.

function buildRedirectTarget(incomingUrl: string): { url: URL; status: number } | null {
  const url = new URL(incomingUrl)
  const MODELS_PREFIX = "/models/"
  if (!url.pathname.startsWith(MODELS_PREFIX)) return null
  const rawTail = url.pathname.slice(MODELS_PREFIX.length)
  if (!rawTail) return null
  let decoded: string
  try {
    decoded = decodeURIComponent(rawTail)
  } catch {
    decoded = rawTail
  }
  const incomingRouteId = encodeURIComponent(decoded)
  const newRouteId = resolveModelRedirect(incomingRouteId)
  if (!newRouteId) return null
  const target = new URL(url.toString())
  target.pathname = `${MODELS_PREFIX}${newRouteId}`
  target.search = url.search // preserve query params
  return { url: target, status: 301 }
}

describe("redirect target construction (middleware contract)", () => {
  // A known folded-spelling -> group redirect from the generated map: the dated
  // snapshot folds into the moving group pointer.
  const OLD = "anthropic/claude-3-haiku-20240307"
  const NEW = "anthropic/claude-3-haiku"

  it("the generated map contains the expected folded-spelling -> group redirect", () => {
    expect(resolveModelRedirect(routeId(OLD))).toBe(routeId(NEW))
  })

  it("redirects an old encoded URL to the new one with 301", () => {
    const res = buildRedirectTarget(`https://x.test/models/${routeId(OLD)}`)
    expect(res).not.toBeNull()
    expect(res!.status).toBe(301)
    expect(res!.url.pathname).toBe(`/models/${routeId(NEW)}`)
  })

  it("PRESERVES query params across the redirect", () => {
    const res = buildRedirectTarget(`https://x.test/models/${routeId(OLD)}?version=20240307&foo=bar`)
    expect(res).not.toBeNull()
    expect(res!.url.search).toBe("?version=20240307&foo=bar")
    expect(res!.url.searchParams.get("version")).toBe("20240307")
    expect(res!.url.searchParams.get("foo")).toBe("bar")
  })

  it("preserves an empty query string (no spurious ?)", () => {
    const res = buildRedirectTarget(`https://x.test/models/${routeId(OLD)}`)
    expect(res!.url.search).toBe("")
  })

  it("handles the decoded (slash) path form too — round-trips to the same redirect", () => {
    // Next.js may hand us the decoded path; the lookup re-encodes it.
    const res = buildRedirectTarget(`https://x.test/models/${OLD}?version=v1`)
    expect(res).not.toBeNull()
    expect(res!.url.pathname).toBe(`/models/${routeId(NEW)}`)
    expect(res!.url.searchParams.get("version")).toBe("v1")
  })

  it("returns null (no redirect) for an unknown model route", () => {
    const res = buildRedirectTarget("https://x.test/models/unknown%2Fmodel-xyz")
    expect(res).toBeNull()
  })
})
