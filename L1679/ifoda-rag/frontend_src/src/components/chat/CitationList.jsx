import { useTranslation } from 'react-i18next'

/**
 * CitationList — collapsible source chunks with:
 *   - animated entry
 *   - confidence indicator per source
 *   - expand/collapse
 */
export default function CitationList({ citations = [] }) {
  const { t } = useTranslation()
  if (!citations.length) return null

  return (
    <div
      className="mt-3 pt-3 border-t msg-enter"
      style={{
        borderColor: 'rgba(0,240,255,0.15)',
        fontFamily: 'var(--font-mono)',
      }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-2.5">
        <span
          className="text-[0.65rem] tracking-[0.25em] uppercase"
          style={{ color: 'var(--color-ink-dim)' }}
        >
          {t('sources', { count: citations.length })}
        </span>
        {/* Decorative line */}
        <span className="flex-1 h-px" style={{background:'linear-gradient(90deg, rgba(0,240,255,0.2), transparent)'}} />
      </div>

      <div className="flex flex-col gap-2">
        {citations.map((c, i) => (
          <div
            key={c.index ?? i}
            className="pl-3 py-1.5 rounded-r-md transition-all hover:brightness-110 cursor-default"
            style={{
              borderLeft: '2px solid var(--color-neon-cyan)',
              background: 'rgba(0,240,255,0.03)',
              boxShadow: 'inset 0 0 8px rgba(0,240,255,0.02)',
              animation: `msg-in 0.3s ease-out ${i * 0.06}s both`,
            }}
          >
            <div className="flex items-baseline gap-2 mb-0.5">
              <span
                className="text-[0.65rem] font-bold shrink-0"
                style={{
                  color: 'var(--color-neon-cyan)',
                  textShadow: '0 0 6px var(--color-neon-cyan)',
                }}
              >
                [{String(c.index ?? i + 1).padStart(2, '0')}]
              </span>
              <span
                className="text-[0.7rem] truncate"
                style={{ color: 'var(--color-ink)' }}
                data-selectable
              >
                {c.product || c.source || '—'}
              </span>
            </div>
            {c.source && (
              <div
                className="flex items-center gap-1.5 text-[0.6rem] ml-[3.2em]"
                style={{ color: 'var(--color-ink-faint)' }}
              >
                <span className="inline-block w-1 h-1 rounded-full" style={{background:'var(--color-ink-faint)'}} />
                <span className="truncate">{c.source}</span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
