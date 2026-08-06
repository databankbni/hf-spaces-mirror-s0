import { useTranslation } from 'react-i18next'

/**
 * LoadingGlitch — dramatic cyberpunk loading indicator.
 * Features: animated scan bars, glitch text, data-stream dots.
 */
export default function LoadingGlitch({ mode = 'chat' }) {
  const { t } = useTranslation()
  const text = mode === 'chat' ? t('loading_chat') : t('loading_search')

  return (
    <div className="flex flex-col items-center gap-2 py-4">
      {/* Scan bars */}
      <div className="flex items-center gap-1">
        {[0,1,2,3,4].map((i) => (
          <span
            key={i}
            className="inline-block rounded-sm"
            style={{
              width: '3px',
              height: `${12 + Math.sin(i * 1.2) * 8}px`,
              background: `var(--color-neon-${i % 2 === 0 ? 'cyan' : 'magenta'})`,
              boxShadow: `0 0 6px var(--color-neon-${i % 2 === 0 ? 'cyan' : 'magenta'})`,
              animation: `blink-cursor ${0.4 + i * 0.15}s step-end infinite`,
              animationDelay: `${i * 0.1}s`,
              opacity: 0.8,
            }}
          />
        ))}
      </div>

      {/* Loading text with glitch */}
      <div
        className="text-[0.7rem] tracking-[0.25em] flicker"
        style={{
          color: 'var(--color-neon-yellow)',
          fontFamily: 'var(--font-mono)',
          textShadow: '0 0 8px rgba(252,238,10,0.6), 0 0 16px rgba(252,238,10,0.3)',
        }}
      >
        {text}
      </div>

      {/* Progress dots */}
      <div className="flex gap-1.5 mt-1">
        {[0,1,2].map((i) => (
          <span
            key={i}
            className="inline-block w-1 h-1 rounded-full blink-cursor"
            style={{
              background: 'var(--color-neon-cyan)',
              boxShadow: '0 0 4px var(--color-neon-cyan)',
              animationDelay: `${i * 0.25}s`,
            }}
          />
        ))}
      </div>
    </div>
  )
}
