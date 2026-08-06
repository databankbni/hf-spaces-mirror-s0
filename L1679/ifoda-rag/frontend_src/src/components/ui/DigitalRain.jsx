import { useEffect, useRef } from 'react'

/**
 * DigitalRain — subtle Matrix-style falling glyphs overlay.
 * Runs on a canvas behind the UI but above the 3D scene.
 * Very low opacity — atmospheric, not distracting.
 */
export default function DigitalRain({ density = 40, speed = 0.6 }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    let raf
    let drops = []

    const resize = () => {
      canvas.width = window.innerWidth
      canvas.height = window.innerHeight
      const cols = Math.floor(canvas.width / 22)
      drops = Array.from({ length: cols }, () => ({
        x: 0,
        y: Math.random() * canvas.height,
        speed: 0.5 + Math.random() * speed * 2,
        length: 3 + Math.floor(Math.random() * 12),
        opacity: 0.03 + Math.random() * 0.08,
      }))
      // set x positions
      drops.forEach((d, i) => { d.x = i * 22 + Math.random() * 10 })
    }

    const CYAN = '0, 240, 255'
    const MAGENTA = '255, 43, 214'

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      for (const d of drops) {
        const color = Math.random() > 0.7 ? MAGENTA : CYAN
        // Head (bright)
        ctx.fillStyle = `rgba(${color}, ${d.opacity * 2.5})`
        const headY = d.y
        ctx.fillRect(d.x, headY, 1.2, 3)
        // Tail (fading)
        for (let j = 1; j < d.length; j++) {
          ctx.fillStyle = `rgba(${color}, ${d.opacity * (1 - j / d.length) * 1.5})`
          ctx.fillRect(d.x, headY + j * 16, 1.2, 16)
        }
        d.y += d.speed
        if (d.y > canvas.height + 100) {
          d.y = -100 - Math.random() * 200
          d.speed = 0.5 + Math.random() * speed * 2
        }
      }
      raf = requestAnimationFrame(draw)
    }

    resize()
    draw()
    window.addEventListener('resize', resize)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
    }
  }, [density, speed])

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 5,
        pointerEvents: 'none',
        opacity: 0.55,
      }}
    />
  )
}
