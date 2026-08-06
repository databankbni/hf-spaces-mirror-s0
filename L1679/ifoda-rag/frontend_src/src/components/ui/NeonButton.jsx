import clsx from 'clsx'

/**
 * NeonButton — chip / button with neon outline + glow + active fill.
 *
 * Props:
 *   - active: boolean — filled state
 *   - color: 'cyan' | 'magenta' | 'yellow' | 'green' | 'red'
 *   - size: 'sm' | 'md'
 */
export default function NeonButton({
  active = false,
  color = 'cyan',
  size = 'md',
  className,
  children,
  style,
  ...rest
}) {
  const colorMap = {
    cyan: 'var(--color-neon-cyan)',
    magenta: 'var(--color-neon-magenta)',
    yellow: 'var(--color-neon-yellow)',
    green: 'var(--color-neon-green)',
    red: 'var(--color-neon-red)',
  }
  const c = colorMap[color] || colorMap.cyan

  return (
    <button
      className={clsx(
        'relative font-mono uppercase tracking-wider rounded-md border transition-all duration-150 cursor-pointer',
        size === 'sm' ? 'px-2.5 py-1 text-[0.65rem]' : 'px-3.5 py-1.5 text-[0.7rem] font-bold',
        'hover:brightness-125 active:translate-y-px',
        className
      )}
      style={{
        fontFamily: 'var(--font-mono)',
        color: active ? '#ffffff' : 'var(--color-ink)',
        borderColor: active ? c : `${c}60`,
        background: active ? `${c}2a` : 'rgba(0,0,0,0.5)',
        textShadow: active ? `0 0 10px ${c}, 0 0 20px ${c}60` : `0 0 4px ${c}40`,
        boxShadow: active ? `0 0 14px ${c}50, inset 0 0 10px ${c}30` : `0 0 6px ${c}18`,
        ...style,
      }}
      {...rest}
    >
      {active && (
        <span
          aria-hidden
          className="absolute -top-px -left-px w-1.5 h-1.5 border-t border-l"
          style={{ borderColor: c }}
        />
      )}
      {active && (
        <span
          aria-hidden
          className="absolute -bottom-px -right-px w-1.5 h-1.5 border-b border-r"
          style={{ borderColor: c }}
        />
      )}
      {children}
    </button>
  )
}