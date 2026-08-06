import clsx from 'clsx'
import { useId } from 'react'

const COLOR_MAP = {
  cyan:    'var(--color-neon-cyan)',
  magenta: 'var(--color-neon-magenta)',
  yellow:  'var(--color-neon-yellow)',
  green:   'var(--color-neon-green)',
  red:     'var(--color-neon-red)',
  blue:    'var(--color-neon-blue)',
  orange:  'var(--color-neon-orange)',
}

/**
 * GlitchText — neon text with optional:
 *   - glitch: RGB split jitter
 *   - flicker: opacity pulse
 *   - chromatic: subtle color fringing (red/cyan offsets)
 */
export default function GlitchText({
  as: Tag = 'span',
  color = 'cyan',
  glitch = false,
  flicker = false,
  chromatic = false,
  className,
  children,
  style,
  ...rest
}) {
  const c = COLOR_MAP[color] || COLOR_MAP.cyan
  const uid = useId().replace(/:/g, '')

  return (
    <>
      {chromatic && (
        <style>{`
          .gt-${uid} {
            position: relative;
            display: inline-block;
          }
          .gt-${uid}::before,
          .gt-${uid}::after {
            content: attr(data-text);
            position: absolute;
            top: 0; left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            opacity: 0.5;
          }
          .gt-${uid}::before {
            color: #ff2bd6;
            text-shadow: 0 0 6px #ff2bd6;
            clip-path: inset(0 0 50% 0);
            animation: gts-${uid} 3s ease-in-out infinite;
            transform: translate(-1px, 0);
          }
          .gt-${uid}::after {
            color: #00f0ff;
            text-shadow: 0 0 6px #00f0ff;
            clip-path: inset(50% 0 0 0);
            animation: gts-${uid} 3s ease-in-out infinite 0.15s;
            transform: translate(1px, 0);
          }
          @keyframes gts-${uid} {
            0%,100%{opacity:0.35;transform:translate(0,0)}
            25%{opacity:0.6;transform:translate(-0.5px,0)}
            50%{opacity:0.3;transform:translate(0.5px,0)}
            75%{opacity:0.5;transform:translate(0,0)}
          }
        `}</style>
      )}
      <Tag
        data-text={chromatic ? children : undefined}
        className={clsx(
          chromatic && `gt-${uid}`,
          glitch && 'glitch-text',
          flicker && 'text-flicker',
          className
        )}
        style={{
          color: c,
          textShadow: `0 0 8px ${c}99, 0 0 16px ${c}40, 0 0 32px ${c}20`,
          ...style,
        }}
        {...rest}
      >
        {children}
      </Tag>
    </>
  )
}
