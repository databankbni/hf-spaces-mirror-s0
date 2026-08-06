import { useTranslation } from 'react-i18next'
import { useFontScale, FONT_SCALE_LEVELS } from '../../hooks/useFontScale'

/**
 * FontScaleToggle — three-button size selector for accessibility.
 *
 * 1 = current IFODA size
 * 2 = larger + medium weight
 * 3 = largest + bold
 *
 * Choice is persisted to localStorage and applies via CSS variables on
 * <html> so the whole document scales together.
 */
export default function FontScaleToggle() {
  const { t } = useTranslation()
  const { scale, set } = useFontScale()

  return (
    <div
      className="flex items-center gap-1 rounded-lg px-1 py-0.5"
      role="radiogroup"
      aria-label={t('font_size', { defaultValue: 'Размер шрифта' })}
      style={{
        border: '1px solid rgba(0, 240, 255, 0.35)',
        background: 'rgba(0, 240, 255, 0.04)',
        fontFamily: 'var(--font-mono)',
      }}
    >
      <span
        className="px-1.5 select-none"
        style={{
          color: 'var(--color-neon-cyan)',
          fontSize: '0.7rem',
          textShadow: '0 0 4px var(--color-neon-cyan)',
        }}
        aria-hidden
      >
        A
      </span>
      {FONT_SCALE_LEVELS.map((n) => {
        const active = scale === n
        return (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => set(n)}
            className="min-w-[26px] h-6 rounded text-center font-bold transition-all cursor-pointer"
            style={{
              fontSize: n === 1 ? '0.7rem' : n === 2 ? '0.8rem' : '0.95rem',
              fontWeight: n === 1 ? 400 : n === 2 ? 500 : 700,
              color: active ? 'var(--color-neon-cyan)' : 'var(--color-ink-dim)',
              background: active ? 'rgba(0, 240, 255, 0.18)' : 'transparent',
              border: active ? '1px solid rgba(0, 240, 255, 0.5)' : '1px solid transparent',
              boxShadow: active ? '0 0 8px rgba(0, 240, 255, 0.3)' : 'none',
              textShadow: active ? '0 0 6px var(--color-neon-cyan)' : 'none',
              fontFamily: 'var(--font-mono)',
              lineHeight: 1,
              padding: '0 4px',
            }}
            title={`Размер шрифта ${n} из 3`}
            aria-label={`Размер шрифта ${n} из 3`}
          >
            {n}
          </button>
        )
      })}
    </div>
  )
}