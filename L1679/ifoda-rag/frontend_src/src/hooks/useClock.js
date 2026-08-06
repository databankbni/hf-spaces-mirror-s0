import { useEffect, useState } from 'react'

/**
 * Clock that updates once a second, formatted as HH:MM:SS in 24h UTC.
 * Used in the BottomHUD.
 */
export function useClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  const fmt = (n) => String(n).padStart(2, '0')
  return `${fmt(now.getUTCHours())}:${fmt(now.getUTCMinutes())}:${fmt(now.getUTCSeconds())}`
}