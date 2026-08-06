import clsx from 'clsx'
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'

/**
 * NeonInput — terminal-style input.
 *   - `multiline={true}` swaps <input> for <textarea> and auto-resizes
 *     vertically to fit content (capped at `maxRows`, then scrolls inside).
 *   - All visuals (focus glow bar, scan line, caret glow, colors) are identical
 *     between single-line and multi-line modes.
 *
 * Enter behaviour is controlled by the caller (see ChatMode/SearchMode):
 *   - single-line: Enter submits, Esc clears
 *   - multi-line:  Enter submits, Shift+Enter inserts newline
 */
const NeonInput = forwardRef(function NeonInput(
  {
    className,
    color = 'cyan',
    onFocus,
    onBlur,
    onKeyDown,
    multiline = false,
    maxRows = 8,
    fillHeight = false,   // when true (multiline), the textarea fills its parent
    ...rest
  },
  ref
) {
  const colorMap = {
    cyan: 'var(--color-neon-cyan)',
    magenta: 'var(--color-neon-magenta)',
    yellow: 'var(--color-neon-yellow)',
  }
  const c = colorMap[color] || colorMap.cyan
  const [focused, setFocused] = useState(false)
  const innerRef = useRef(null)

  // Forward the parent ref to the inner element so .focus() / .select() still work.
  useImperativeHandle(ref, () => innerRef.current, [])

  // Auto-grow the textarea to fit its content (multiline only).
  // When `fillHeight` is true, the textarea fills its parent and overflows
  // internally (the parent decides how tall to be).
  useEffect(() => {
    if (!multiline || !innerRef.current) return
    const el = innerRef.current
    if (fillHeight) {
      el.style.height = '100%'
      el.style.overflowY = 'auto'
      return
    }
    el.style.height = 'auto'
    const cs = getComputedStyle(el)
    const fontSize = parseFloat(cs.fontSize) || 14.4
    const lh = parseFloat(cs.lineHeight)
    const lineHeight = Number.isFinite(lh) ? lh : fontSize * 1.5
    const maxHeight = lineHeight * maxRows
    const target = Math.min(el.scrollHeight, maxHeight)
    el.style.height = `${target}px`
    el.style.overflowY = el.scrollHeight > maxHeight ? 'auto' : 'hidden'
  }, [rest.value, multiline, maxRows, fillHeight])

  const sharedClass = clsx(
    'w-full bg-transparent outline-none px-3 py-2 text-[0.9rem] relative z-10',
    'placeholder:tracking-[0.15em]',
    multiline && 'resize-none block',
    fillHeight && 'h-full',
    className
  )
  const sharedStyle = {
    color: c,
    fontFamily: 'var(--font-mono)',
    caretColor: c,
    textShadow: focused ? `0 0 6px ${c}60, 0 0 12px ${c}30` : `0 0 4px ${c}40`,
    transition: 'text-shadow 0.3s ease',
    lineHeight: '1.5',
  }

  const handleFocus = (e) => { setFocused(true); onFocus?.(e) }
  const handleBlur  = (e) => { setFocused(false); onBlur?.(e) }

  return (
    <div className="relative flex-1">
      {multiline ? (
        <textarea
          ref={innerRef}
          rows={1}
          className={sharedClass}
          style={sharedStyle}
          onFocus={handleFocus}
          onBlur={handleBlur}
          onKeyDown={onKeyDown}
          {...rest}
        />
      ) : (
        <input
          ref={innerRef}
          className={sharedClass}
          style={sharedStyle}
          onFocus={handleFocus}
          onBlur={handleBlur}
          onKeyDown={onKeyDown}
          {...rest}
        />
      )}
      {/* Focus glow bar — slides in from left */}
      <div
        aria-hidden
        className="absolute bottom-0 left-2 right-2 h-px transition-all duration-300 pointer-events-none"
        style={{
          background: `linear-gradient(90deg, transparent, ${c}, transparent)`,
          opacity: focused ? 1 : 0,
          boxShadow: focused ? `0 0 8px ${c}80` : 'none',
        }}
      />
      {/* Focus scan line */}
      {focused && (
        <div
          aria-hidden
          className="absolute top-2 bottom-2 w-px pointer-events-none"
          style={{
            left: '3px',
            background: `linear-gradient(180deg, transparent, ${c}60, transparent)`,
            boxShadow: `0 0 4px ${c}40`,
            animation: 'scan-down 2s ease-in-out infinite',
          }}
        />
      )}
    </div>
  )
})

export default NeonInput