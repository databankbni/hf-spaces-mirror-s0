"use client"

import { useId } from "react"

import {
  PARAM_RANGE_MARKERS,
  PARAM_RANGE_MAX_INDEX,
  PARAM_RANGE_VALUES,
  formatParamBoundLabel,
} from "@/lib/param-range"

export type ParamRangeVariant = "default" | "inline" | "promo"

interface ParamRangePickerProps {
  /** Index into PARAM_RANGE_VALUES for the lower handle (0 = "< 1B"). */
  minStep: number
  /** Index into PARAM_RANGE_VALUES for the upper handle (max = "> 500B"). */
  maxStep: number
  onMinChange: (next: number) => void
  onMaxChange: (next: number) => void
  /**
   * `default` — Variant A: bracketed range with a labelled rail and a boxed
   * mono readout, suitable for use as the headline call-out at the top of a
   * leaderboard.
   *
   * `inline` — Variant B: a single-line picker with no boxed readout, sized
   * to drop into a hairline toolbar alongside Sort and Filter pickers.
   *
   * `promo` — Variant C: warm-background framed slider with a left accent
   * rule. Use when the slider actively reframes a chart/matrix below it.
   */
  variant?: ParamRangeVariant
  /** Headline shown to the left of the slider (default & promo variants). */
  headline?: string
  /** Sub-text shown under the headline (default & promo variants). */
  subline?: string
  /** Callback to reset both handles to the open range. When provided, a
   *  Reset affordance is rendered next to the readout while the slider
   *  is constrained. */
  onReset?: () => void
  /** When defined, renders a small "Show models without known size" pill
   *  next to the readout. The toggle is independent of the slider — when
   *  off, models with no detected size are filtered out regardless of
   *  where the handles are. */
  showUnknownSize?: boolean
  onShowUnknownSizeChange?: (next: boolean) => void
  className?: string
}

/**
 * Themed dual-handle parameter-range picker. Shape and colour come from the
 * design system: hairline rail, square outline thumbs, mono uppercase tick
 * labels above the rail, and a boxed mono readout for the explicit bounds.
 *
 * The two `<input type="range">` elements provide native dragging + arrow-key
 * a11y. The visual rail/fill/ticks/thumbs are absolutely-positioned overlays;
 * the inputs themselves are kept transparent except for their thumbs (see
 * `.param-range-input` in globals.css).
 */
export function ParamRangePicker({
  minStep,
  maxStep,
  onMinChange,
  onMaxChange,
  variant = "default",
  headline = "Parameter range",
  subline = "Narrow the matrix to comparable model sizes.",
  onReset,
  showUnknownSize,
  onShowUnknownSizeChange,
  className,
}: ParamRangePickerProps) {
  const minId = useId()
  const maxId = useId()

  const isInline = variant === "inline"
  const isPromo = variant === "promo"

  const minPercent = (minStep / PARAM_RANGE_MAX_INDEX) * 100
  const maxPercent = (maxStep / PARAM_RANGE_MAX_INDEX) * 100
  const isConstrained = minStep > 0 || maxStep < PARAM_RANGE_MAX_INDEX

  const track = (
    <div className="pr-track-wrap">
      <div className="pr-ticks" aria-hidden>
        {PARAM_RANGE_MARKERS.map((marker, idx) => {
          const isFirst = idx === 0
          const isLast = idx === PARAM_RANGE_MARKERS.length - 1
          const active = marker.step === minStep || marker.step === maxStep
          return (
            <div
              key={marker.label}
              className={`pr-tick${active ? " on" : ""}`}
              style={{
                left: `${(marker.step / PARAM_RANGE_MAX_INDEX) * 100}%`,
              }}
            >
              <span
                style={{
                  transform: isFirst
                    ? "translateX(0)"
                    : isLast
                    ? "translateX(-100%)"
                    : "translateX(-50%)",
                  marginLeft: 0,
                }}
              >
                {marker.label}
              </span>
            </div>
          )
        })}
      </div>

      <div className="pr-rail" />
      <div
        className="pr-fill"
        style={{
          left: `${minPercent}%`,
          width: `${Math.max(maxPercent - minPercent, 0)}%`,
        }}
      />

      {/* Hidden inter-bucket micro-ticks to give the rail a metered feel */}
      <div className="pr-microticks" aria-hidden>
        {PARAM_RANGE_VALUES.map((_, stepIndex) => (
          <span
            key={`pr-micro-${stepIndex}`}
            style={{ left: `${(stepIndex / PARAM_RANGE_MAX_INDEX) * 100}%` }}
          />
        ))}
      </div>

      {/* Native inputs provide a11y + drag; we hide them visually and rely
          on the .param-range-input thumb styling for the visible handles. */}
      <input
        id={minId}
        type="range"
        min={0}
        max={PARAM_RANGE_MAX_INDEX}
        step={1}
        value={minStep}
        onChange={(event) => {
          const next = Number(event.target.value)
          onMinChange(Math.min(next, maxStep))
        }}
        className="param-range-input"
        aria-label={`Minimum ${headline.toLowerCase()}`}
      />
      <input
        id={maxId}
        type="range"
        min={0}
        max={PARAM_RANGE_MAX_INDEX}
        step={1}
        value={maxStep}
        onChange={(event) => {
          const next = Number(event.target.value)
          onMaxChange(Math.max(next, minStep))
        }}
        className="param-range-input"
        aria-label={`Maximum ${headline.toLowerCase()}`}
      />
    </div>
  )

  const resetBtn = onReset && isConstrained ? (
    <button
      type="button"
      onClick={onReset}
      className="pr-reset"
      aria-label="Reset parameter range"
    >
      Reset
    </button>
  ) : null

  const unknownToggle =
    onShowUnknownSizeChange != null ? (
      <button
        type="button"
        onClick={() => onShowUnknownSizeChange(!showUnknownSize)}
        className={`pr-unknown-toggle${showUnknownSize ? " on" : ""}`}
        aria-pressed={Boolean(showUnknownSize)}
        title="Models without a reported parameter count"
      >
        <span className="pr-unknown-toggle-box" aria-hidden>
          {showUnknownSize ? "✓" : ""}
        </span>
        Unknown size
      </button>
    ) : null

  const readout = (
    <div className="pr-readout-cell">
      <div className={`pr-readout${isInline ? " inline" : ""}`}>
        <span>{formatParamBoundLabel(minStep, "min")}</span>
        <span className="arrow">{isInline ? "–" : "→"}</span>
        <span>{formatParamBoundLabel(maxStep, "max")}</span>
      </div>
      {unknownToggle}
      {resetBtn}
    </div>
  )

  if (isInline) {
    return (
      <div className={`pr-slider inline${className ? ` ${className}` : ""}`}>
        <span className="pr-label inline-label">
          <strong>{headline}</strong>
        </span>
        {track}
        {readout}
      </div>
    )
  }

  if (isPromo) {
    return (
      <div className={`pr-promo${className ? ` ${className}` : ""}`}>
        <div className="pr-promo-head">
          <span className="kicker">{headline}</span>
          <p>{subline}</p>
        </div>
        <div className="pr-slider pr-slider-track-only">
          {track}
          {readout}
        </div>
      </div>
    )
  }

  // Default (Variant A)
  return (
    <div className={`pr-slider${className ? ` ${className}` : ""}`}>
      <div className="pr-label">
        <strong>{headline}</strong>
        {subline}
      </div>
      {track}
      {readout}
    </div>
  )
}
