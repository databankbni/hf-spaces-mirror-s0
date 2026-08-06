import { useTranslation } from 'react-i18next'

const COLOR_MAP = {
  high:   { fg:'var(--color-neon-green)',  bg:'rgba(0,255,136,0.12)', glow:'0 0 8px var(--color-neon-green)' },
  medium: { fg:'var(--color-neon-yellow)', bg:'rgba(252,238,10,0.12)', glow:'0 0 8px var(--color-neon-yellow)' },
  low:    { fg:'var(--color-neon-red)',    bg:'rgba(255,46,76,0.12)',  glow:'0 0 8px var(--color-neon-red)' },
}

/**
 * ConfidenceBadge — animated pill with pulse dot.
 */
export default function ConfidenceBadge({ level = 'low' }) {
  const { t } = useTranslation()
  const colors = COLOR_MAP[level] || COLOR_MAP.low

  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[0.65rem] font-bold uppercase tracking-[0.18em] border"
      style={{
        color: colors.fg,
        background: colors.bg,
        borderColor: `${colors.fg}50`,
        textShadow: colors.glow,
        fontFamily: 'var(--font-mono)',
        animation: level === 'high' ? 'pulse-glow 2s ease-in-out infinite' : 'none',
      }}
    >
      <span
        className="inline-block w-1.5 h-1.5 rounded-full"
        style={{
          background: colors.fg,
          boxShadow: `0 0 8px ${colors.fg}, 0 0 16px ${colors.fg}60`,
          animation: 'blink-cursor 2s step-end infinite',
        }}
      />
      {t(`confidence_${level}`, level)}
    </span>
  )
}
