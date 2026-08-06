/**
 * ConfidenceBar — slim progress bar with a color stop on the score.
 */
export default function ConfidenceBar({ score = 0 }) {
  const pct = Math.round(Math.max(0, Math.min(1, score)) * 100)
  const color =
    pct > 50
      ? 'var(--color-neon-green)'
      : pct > 20
      ? 'var(--color-neon-yellow)'
      : 'var(--color-neon-red)'
  return (
    <div
      className="flex items-center gap-2 text-[0.65rem]"
      style={{ fontFamily: 'var(--font-mono)' }}
    >
      <div
        className="flex-1 h-[3px] rounded-full overflow-hidden"
        style={{ background: 'rgba(255,255,255,0.06)' }}
      >
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${pct}%`,
            background: color,
            boxShadow: `0 0 6px ${color}80`,
          }}
        />
      </div>
      <span style={{ color, minWidth: '2.5em', textAlign: 'right' }}>{pct}%</span>
    </div>
  )
}