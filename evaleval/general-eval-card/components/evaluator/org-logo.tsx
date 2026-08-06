"use client"

import { useCallback, useEffect, useRef, useState } from "react"

import { monogramFor, monogramHue } from "@/lib/evaluator-logo"
import { cn } from "@/lib/utils"

/**
 * OrgLogo — renders an evaluating org's brand mark inside a consistent square
 * plate, robust to the wildly inconsistent assets real orgs ship.
 *
 * The problem: some orgs have PR-ready square icons; most don't. We get 4:1
 * horizontal wordmarks, tall lockups, tiny favicons, transparent PNGs and SVGs
 * — every aspect ratio and resolution. We want a single, consistent on-page
 * footprint regardless.
 *
 * The strategy ("auto-square + auto-size"):
 *   1. Fixed SQUARE plate. Size is driven by the `--logo-size` CSS var (default
 *      72px) so a caller can make it responsive with one arbitrary class, e.g.
 *      `className="[--logo-size:64px] sm:[--logo-size:72px]"`. The mark never
 *      changes the plate's shape.
 *   2. `object-contain`, always — the mark is scaled to FIT, never cropped
 *      (object-cover) and never stretched (object-fill). No distortion, ever.
 *   3. Aspect-aware bounds. With object-contain alone, a wide wordmark shrinks
 *      to a tiny sliver in a square box. So we measure the loaded image's
 *      natural aspect and cap width/height per shape class (wide / tall /
 *      square) so each reaches a comparable OPTICAL size: a wordmark is allowed
 *      to span most of the plate width, a square icon keeps breathing room.
 *   4. Graceful fallbacks: no src, or a load error, or a degenerate 0×0 asset
 *      → a deterministic monogram tile on the same plate. The layout never
 *      collapses or shifts.
 *
 * Measuring handles cached images too (onLoad may not fire) via a ref check on
 * mount. The mark fades in once measured to avoid a first-paint size jump.
 */

type Fit = "square" | "wide" | "tall"

// Max width/height the mark may occupy inside the plate, as a fraction, per
// shape. Tuned so a 3.7:1 wordmark and a 1:1 icon feel like the same "weight".
const BOUNDS: Record<Fit, { maxW: number; maxH: number }> = {
  square: { maxW: 0.64, maxH: 0.64 },
  wide: { maxW: 0.9, maxH: 0.62 },
  tall: { maxW: 0.62, maxH: 0.86 },
}

function classifyAspect(aspect: number): Fit {
  if (!Number.isFinite(aspect) || aspect <= 0) return "square"
  if (aspect > 1.3) return "wide"
  if (aspect < 0.77) return "tall"
  return "square"
}

export function OrgLogo({
  name,
  src,
  className,
  rounded = "rounded-[4px]",
}: {
  name: string
  /** Brand mark URL, or null when none is known → monogram. */
  src: string | null
  /** Box sizing / `--logo-size` override, e.g. "[--logo-size:64px] sm:[--logo-size:72px]". */
  className?: string
  rounded?: string
}) {
  // "pending" until the image loads & is measured; "ok" once we have an aspect;
  // "error" if it fails / is degenerate → monogram.
  const [status, setStatus] = useState<"pending" | "ok" | "error">(src ? "pending" : "error")
  const [fit, setFit] = useState<Fit>("square")
  const imgRef = useRef<HTMLImageElement | null>(null)

  const measure = useCallback((img: HTMLImageElement) => {
    const { naturalWidth: w, naturalHeight: h } = img
    if (!w || !h) {
      setStatus("error") // degenerate asset → monogram
      return
    }
    setFit(classifyAspect(w / h))
    setStatus("ok")
  }, [])

  // Cached images can be `complete` before React attaches onLoad — measure on
  // mount if so. Re-runs when src changes.
  useEffect(() => {
    if (!src) {
      setStatus("error")
      return
    }
    setStatus("pending")
    const img = imgRef.current
    if (img && img.complete) {
      if (img.naturalWidth) measure(img)
      else setStatus("error")
    }
  }, [src, measure])

  const plateClass = cn(
    "relative flex shrink-0 items-center justify-center overflow-hidden border",
    "h-[var(--logo-size,72px)] w-[var(--logo-size,72px)] bg-[color:var(--logo-plate)] shadow-[var(--shadow-card)]",
    rounded,
    className,
  )
  const plateBorder = { borderColor: "var(--border-soft)" } as const

  if (status === "error") {
    return (
      <div className={plateClass} style={plateBorder}>
        <Monogram name={name} />
      </div>
    )
  }

  const { maxW, maxH } = BOUNDS[fit]
  return (
    <div className={plateClass} style={plateBorder}>
      <img
        ref={imgRef}
        src={src ?? undefined}
        alt={`${name} logo`}
        loading="eager"
        decoding="async"
        onLoad={(e) => measure(e.currentTarget)}
        onError={() => setStatus("error")}
        className={cn(
          "object-contain transition-opacity duration-200",
          status === "pending" ? "opacity-0" : "opacity-100",
        )}
        style={{ maxWidth: `${maxW * 100}%`, maxHeight: `${maxH * 100}%` }}
      />
    </div>
  )
}

/** Deterministic monogram tile — fills the plate; org name carried by an
 *  adjacent heading, so the glyph itself is aria-hidden. */
function Monogram({ name }: { name: string }) {
  const hue = monogramHue(name)
  return (
    <span
      aria-hidden="true"
      className="flex h-full w-full select-none items-center justify-center rounded-[3px] font-sans font-semibold leading-none"
      style={{
        color: `hsl(${hue} 32% 38%)`,
        backgroundColor: `hsl(${hue} 38% 92%)`,
        fontSize: "calc(var(--logo-size, 72px) * 0.34)",
      }}
    >
      {monogramFor(name)}
      <span className="sr-only">{name}</span>
    </span>
  )
}
