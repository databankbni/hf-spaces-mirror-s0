import { useMemo } from 'react'

/**
 * RainGlass — subtle raindrop streaks on the "window" looking at Night City.
 * Creates 50-80 random drops that animate top-to-bottom at varying speeds.
 */
export default function RainGlass({ count = 60 }) {
  const drops = useMemo(() => {
    const arr = []
    for (let i = 0; i < count; i++) {
      arr.push({
        left: `${Math.random() * 100}%`,
        delay: `${Math.random() * 5}s`,
        duration: `${1.2 + Math.random() * 2.5}s`,
        height: `${8 + Math.random() * 20}px`,
        opacity: 0.15 + Math.random() * 0.25,
      })
    }
    return arr
  }, [count])

  return (
    <div className="rain-glass" aria-hidden="true">
      {drops.map((d, i) => (
        <span
          key={i}
          className="drop"
          style={{
            left: d.left,
            animationDelay: d.delay,
            animationDuration: d.duration,
            height: d.height,
            opacity: d.opacity,
          }}
        />
      ))}
    </div>
  )
}
