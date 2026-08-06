import { useTranslation } from 'react-i18next'
import { useClock } from '../../hooks/useClock'

/**
 * BottomHUD — Night City style data stream.
 * Visual: scrolling ticker with glitch effects, live clock, sector coordinates.
 */
export default function BottomHUD() {
  const { t } = useTranslation()
  const clock = useClock()

  return (
    <div className="fixed bottom-0 left-0 right-0 pointer-events-none flex flex-col" style={{zIndex:50}}>
      <style>{`
        @keyframes ticker-scroll {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        @keyframes hud-flicker {
          0%,100%{opacity:1} 92%{opacity:1} 93%{opacity:0.6} 94%{opacity:1} 96%{opacity:1} 97%{opacity:0.5} 98%{opacity:1}
        }
      `}</style>

      {/* Scrolling ticker bar */}
      <div
        className="w-full overflow-hidden py-0.5"
        style={{
          background: 'linear-gradient(90deg, transparent 0%, rgba(0,240,255,0.05) 15%, rgba(255,43,214,0.04) 50%, rgba(0,240,255,0.05) 85%, transparent 100%)',
          borderTop: '1px solid rgba(0,240,255,0.1)',
          borderBottom: '1px solid rgba(0,240,255,0.06)',
          animation: 'hud-flicker 8s linear infinite',
        }}
      >
        <div
          className="whitespace-nowrap text-[0.5rem] md:text-[0.55rem] tracking-[0.2em] uppercase py-0.5"
          style={{
            color: 'var(--color-ink-faint)',
            fontFamily: 'var(--font-mono)',
            animation: 'ticker-scroll 50s linear infinite',
            display: 'inline-block',
          }}
        >
          <span style={{color:'var(--color-neon-cyan)',textShadow:'0 0 4px var(--color-neon-cyan)'}}>◆ NETRUNNER v1.0 ◆</span>
          {' '}<span style={{color:'var(--color-neon-magenta)'}}>{t('hud_coords')}</span>
          {' ◆ UPLINK ACTIVE ◆ '}
          <span style={{color:'var(--color-neon-yellow)'}}>{t('hud_time', { time: clock })}</span>
          {' ◆ CHROMA-DB ◆ DEEPSEEK-R1 ◆'}
          {' '}<span style={{color:'var(--color-neon-cyan)'}}>◆ IFODA AGRO KNOWLEDGE ◆</span>
          {' ◆ '}<span style={{color:'var(--color-neon-magenta)'}}>{t('hud_coords')}</span>
          {' ◆ '}<span style={{color:'var(--color-neon-yellow)'}}>{t('hud_time', { time: clock })}</span>
          {' ◆'}
        </div>
      </div>

      {/* Status line */}
      <div
        className="flex items-end justify-between px-3 md:px-5 py-1.5"
        style={{ background: 'linear-gradient(0deg, rgba(4,4,17,0.6) 0%, transparent 100%)' }}
      >
        {/* Clock + sector */}
        <div className="flex items-center gap-3">
          <span style={{
            color:'var(--color-neon-cyan)',fontFamily:'var(--font-mono)',fontSize:'0.6rem',
            letterSpacing:'0.2em',textShadow:'0 0 8px var(--color-neon-cyan)',
          }}>
            {t('hud_time', { time: clock })}
          </span>
          <span style={{
            color:'var(--color-ink-faint)',fontFamily:'var(--font-mono)',fontSize:'0.5rem',
            letterSpacing:'0.3em',
          }}>
            SEC-7 :: IFODA-NET
          </span>
        </div>

        {/* Right side indicators */}
        <div className="flex items-center gap-3">
          <span style={{
            color:'var(--color-neon-green)',fontFamily:'var(--font-mono)',fontSize:'0.5rem',
            letterSpacing:'0.25em',textShadow:'0 0 6px var(--color-neon-green)',
          }}>
            SIG: 98%
          </span>
          <span style={{
            color:'var(--color-ink-faint)',fontFamily:'var(--font-mono)',fontSize:'0.5rem',
            letterSpacing:'0.3em',
          }}>
            <span style={{color:'var(--color-neon-magenta)',textShadow:'0 0 4px var(--color-neon-magenta)'}}>●</span> REC
          </span>
        </div>
      </div>
    </div>
  )
}
