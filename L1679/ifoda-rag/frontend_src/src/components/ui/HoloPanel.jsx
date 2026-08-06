import clsx from 'clsx'
import { useId, useEffect, useRef } from 'react'

const COLOR_PRESETS = {
  cyan:   { main:'var(--color-neon-cyan)',   glow:'rgba(0,240,255,0.18)',  border:'rgba(0,240,255,0.35)' },
  magenta:{ main:'var(--color-neon-magenta)', glow:'rgba(255,43,214,0.18)',border:'rgba(255,43,214,0.35)' },
  yellow: { main:'var(--color-neon-yellow)',  glow:'rgba(252,238,10,0.18)',border:'rgba(252,238,10,0.35)' },
  green:  { main:'var(--color-neon-green)',   glow:'rgba(0,255,136,0.18)', border:'rgba(0,255,136,0.35)' },
  red:    { main:'var(--color-neon-red)',      glow:'rgba(255,46,76,0.18)', border:'rgba(255,46,76,0.35)' },
}

/**
 * HoloPanel — holographic glass panel with:
 *   - animated border glow sweep
 *   - corner brackets with pulsing
 *   - subtle holographic scan-line shimmer
 *   - depth shadow with colored rim
 */
export default function HoloPanel({
  color = 'cyan',
  glow = true,
  title,
  className,
  children,
  style,
  transparent = false,   // when true, panel uses a lighter background so the night-city shows through
  ...rest
}) {
  const c = COLOR_PRESETS[color] || COLOR_PRESETS.cyan
  const uid = useId().replace(/:/g, '')
  const panelRef = useRef(null)

  // Animated scan-line effect via canvas
  useEffect(() => {
    const el = panelRef.current
    if (!el) return
    const canvas = document.createElement('canvas')
    canvas.style.cssText = 'position:absolute;inset:0;pointer-events:none;z-index:2;opacity:0.06;border-radius:inherit;'
    canvas.width = el.offsetWidth || 400
    canvas.height = el.offsetHeight || 300
    el.style.position = el.style.position || 'relative'
    el.appendChild(canvas)

    let y = 0
    let raf
    const ctx = canvas.getContext('2d')
    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      // Moving scan line
      ctx.fillStyle = c.main
      ctx.globalAlpha = 0.25
      ctx.fillRect(0, y, canvas.width, 2)
      ctx.globalAlpha = 0.08
      ctx.fillRect(0, y + 4, canvas.width, 60)
      y = (y + 0.6) % canvas.height
      raf = requestAnimationFrame(draw)
    }
    draw()

    // Resize observer
    const ro = new ResizeObserver(([entry]) => {
      canvas.width = entry.contentRect.width
      canvas.height = entry.contentRect.height
    })
    ro.observe(el)

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      canvas.remove()
    }
  }, [c.main])

  return (
    <div
      ref={panelRef}
      className={clsx('relative rounded-2xl overflow-hidden flex flex-col', className)}
      style={{
        background: transparent
          ? 'linear-gradient(180deg, rgba(10,10,30,0.18) 0%, rgba(5,5,18,0.45) 100%)'
          : 'linear-gradient(180deg, rgba(10,10,30,0.45) 0%, rgba(5,5,18,0.88) 100%)',
        backdropFilter: transparent ? 'blur(8px) saturate(110%)' : 'blur(16px) saturate(120%)',
        WebkitBackdropFilter: transparent ? 'blur(8px) saturate(110%)' : 'blur(16px) saturate(120%)',
        border: `1px solid ${c.main}30`,
        boxShadow: glow
          ? `0 0 40px ${c.glow}, 0 0 80px ${c.main}08, inset 0 0 30px rgba(0,0,0,0.5), inset 0 1px 0 ${c.main}10`
          : 'inset 0 0 24px rgba(0,0,0,0.4)',
        transition: 'background 0.4s ease, backdrop-filter 0.4s ease',
        ...style,
      }}
      {...rest}
    >
      {/* Scoped corner brackets */}
      <style>{`
        .cf-${uid} { position:relative; }
        .cf-${uid}::before,.cf-${uid}::after{content:'';position:absolute;width:16px;height:16px;pointer-events:none;z-index:3;}
        .cf-${uid}::before{top:0;left:0;border-top:2px solid ${c.main};border-left:2px solid ${c.main};box-shadow:0 0 6px ${c.main}80, -1px -1px 0 ${c.main}40;}
        .cf-${uid}::after{bottom:0;right:0;border-bottom:2px solid ${c.main};border-right:2px solid ${c.main};box-shadow:0 0 6px ${c.main}80, 1px 1px 0 ${c.main}40;}
        @keyframes cfp-${uid}{0%,100%{opacity:0.7}50%{opacity:1}}
        .cf-${uid}::before,.cf-${uid}::after{animation:cfp-${uid} 3s ease-in-out infinite;}
      `}</style>

      {/* Top border glow line — sweeps horizontally */}
      <div aria-hidden className="pointer-events-none absolute top-0 left-4 right-4 h-px z-10"
        style={{
          background: `linear-gradient(90deg, transparent, ${c.main}80, ${c.main}, ${c.main}80, transparent)`,
          boxShadow: `0 0 8px ${c.main}60`,
          animation: 'border-flow 8s linear infinite',
        }}
      />

      {title && (
        <div
          className={`cf-${uid} relative flex items-center justify-between px-5 py-2.5 text-[0.65rem] uppercase tracking-[0.25em] z-10`}
          style={{
            borderBottom: `1px solid ${c.main}15`,
            color: 'var(--color-ink-dim)',
            fontFamily: 'var(--font-mono)',
            background: `linear-gradient(180deg, ${c.main}08, transparent)`,
          }}
        >
          <span style={{ color: c.main, textShadow: `0 0 8px ${c.main}99, 0 0 16px ${c.main}40` }}>
            ◈ {title}
          </span>
          {/* Decorative status dots */}
          <span className="flex gap-1.5">
            <span className="inline-block w-1 h-1 rounded-full" style={{background:c.main,boxShadow:`0 0 4px ${c.main}`}} />
            <span className="inline-block w-1 h-1 rounded-full" style={{background:c.main,boxShadow:`0 0 4px ${c.main}`,opacity:0.5}} />
            <span className="inline-block w-1 h-1 rounded-full" style={{background:c.main,boxShadow:`0 0 4px ${c.main}`,opacity:0.25}} />
          </span>
        </div>
      )}

      <div className={`cf-${uid} relative z-10 flex-1 min-h-0 flex flex-col`}>{children}</div>
    </div>
  )
}
