import { useTranslation } from 'react-i18next'
import { useTypewriter } from '../../hooks/useTypewriter'

/**
 * Typewriter — renders text with character-by-character reveal.
 * Falls back to plain text when `enabled` is false (e.g. when text is short
 * or already cached).
 */
export default function Typewriter({ text, speed = 10, enabled = true, className, style }) {
  const { text: out } = useTypewriter(text, { speed, enabled })
  return (
    <span className={className} style={style} data-selectable>
      {out}
      {enabled && out.length < (text?.length || 0) && (
        <span
          className="inline-block w-[0.6ch] h-[1em] align-middle blink-cursor ml-0.5"
          style={{ background: 'currentColor' }}
        />
      )}
    </span>
  )
}