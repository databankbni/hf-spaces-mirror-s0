import { useEffect, useState, useCallback } from 'react'

/**
 * useFontScale — accessibility font-size control (1 / 2 / 3).
 *
 *   1 = current IFODA size (16px / 400) — default
 *   2 = larger + medium weight (19px / 500)
 *   3 = largest + bold     (23px / 700)
 *
 * Persists to localStorage and exposes a `cycle()` helper for the
 * single-button UI in the TopBar. The actual font-size and font-weight
 * are set as CSS variables on `<html>` so the whole document scales.
 */

const STORAGE_KEY = 'ifoda.fontScale'
const VALID = [1, 2, 3]

const PRESETS = {
  1: { size: '16px', weight: 400, lineHeight: 1.5 },
  2: { size: '19px', weight: 500, lineHeight: 1.55 },
  3: { size: '23px', weight: 700, lineHeight: 1.6 },
}

function readStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const n = raw == null ? 1 : parseInt(raw, 10)
    return VALID.includes(n) ? n : 1
  } catch {
    return 1
  }
}

export function useFontScale() {
  const [scale, setScale] = useState(readStored)

  useEffect(() => {
    const preset = PRESETS[scale] || PRESETS[1]
    const root = document.documentElement
    root.style.setProperty('--ifoda-font-size', preset.size)
    root.style.setProperty('--ifoda-font-weight', String(preset.weight))
    root.style.setProperty('--ifoda-line-height', String(preset.lineHeight))
    root.dataset.fontScale = String(scale)
    try { localStorage.setItem(STORAGE_KEY, String(scale)) } catch {}
  }, [scale])

  const cycle = useCallback(() => {
    setScale((s) => (s >= 3 ? 1 : s + 1))
  }, [])

  const set = useCallback((n) => {
    if (VALID.includes(n)) setScale(n)
  }, [])

  return { scale, set, cycle }
}

export const FONT_SCALE_LEVELS = VALID
export default useFontScale