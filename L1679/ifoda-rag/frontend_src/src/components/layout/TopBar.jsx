import { useTranslation } from 'react-i18next'
import { healthCheck } from '../../api/client'
import { useEffect, useState, useRef } from 'react'
import NeonButton from '../ui/NeonButton'
import GlitchText from '../ui/GlitchText'
import FontScaleToggle from '../ui/FontScaleToggle'
import { useLanguage } from '../../hooks/useLanguage'

/**
 * TopBar — fixed top bar with animated brand, status pulse, mode toggle, language switcher.
 * Visual: gradient fade, animated connection dot with pulse ring, neon glow on active elements.
 */
export default function TopBar({ mode, onModeChange }) {
  const { t } = useTranslation()
  const { label, cycleLanguage } = useLanguage()
  const [status, setStatus] = useState({ state: 'checking', docs: 0 })
  const dotRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    const fetchStatus = () => {
      healthCheck()
        .then((s) => !cancelled && setStatus({ state: 'online', docs: s.documents }))
        .catch(() => !cancelled && setStatus({ state: 'offline', docs: 0 }))
    }
    fetchStatus()
    const id = setInterval(fetchStatus, 15_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  const dotColor =
    status.state === 'online' ? 'var(--color-neon-green)' :
    status.state === 'offline' ? 'var(--color-neon-red)' :
    'var(--color-neon-yellow)'

  const statusText =
    status.state === 'online' ? t('status_online', { docs: status.docs }) :
    status.state === 'offline' ? t('status_offline') :
    t('status_checking')

  return (
    <header
      className="fixed top-0 left-0 right-0 flex items-center justify-between px-4 md:px-6 py-3"
      style={{
        zIndex: 50,
        background: 'linear-gradient(rgba(4,4,17,0.95) 0%, rgba(4,4,17,0.55) 60%, transparent 100%)',
        pointerEvents: 'none',
      }}
    >
      {/* Brand block */}
      <div className="flex flex-col gap-0 pointer-events-auto">
        <div className="flex items-center gap-2.5">
          {/* Animated connection dot with pulse ring */}
          <span className="relative flex items-center justify-center shrink-0" style={{width:14,height:14}}>
            <span
              ref={dotRef}
              className="absolute inset-0 rounded-full"
              style={{
                background: dotColor,
                boxShadow: `0 0 10px ${dotColor}, 0 0 20px ${dotColor}80`,
                animation: status.state === 'checking' ? 'blink-cursor 1s step-end infinite' : 'none',
              }}
            />
            {/* Pulse ring */}
            <span
              className="absolute inset-[-4px] rounded-full"
              style={{
                border: `1.5px solid ${dotColor}`,
                opacity: 0.5,
                animation: status.state !== 'checking' ? 'pulse-glow 2s ease-in-out infinite' : 'none',
              }}
            />
          </span>

          <div className="flex flex-col leading-tight">
            <GlitchText
              as="span"
              color="yellow"
              flicker
              className="font-bold tracking-[0.2em] md:tracking-[0.3em] text-[0.85rem] md:text-[1rem]"
              style={{ fontFamily: 'var(--font-display)' }}
            >
              {t('brand')}
            </GlitchText>
            <span
              className="text-[0.55rem] tracking-[0.3em] uppercase hidden sm:block"
              style={{ color: 'var(--color-ink-faint)', fontFamily: 'var(--font-mono)', marginTop: -1 }}
            >
              {t('tagline')}
            </span>
          </div>
        </div>

        {/* Status text */}
        <div
          className="hidden sm:flex items-center gap-1.5 text-[0.6rem] tracking-[0.2em] uppercase mt-0.5"
          style={{ color: 'var(--color-ink-faint)', fontFamily: 'var(--font-mono)' }}
        >
          <span style={{ color: dotColor, textShadow: `0 0 4px ${dotColor}` }}>●</span>
          <span>{statusText}</span>
        </div>
      </div>

      {/* Controls — highlighted panel */}
      <div
        className="flex items-center gap-2 pointer-events-auto rounded-xl px-3 py-2"
        style={{
          border: '2px solid var(--color-neon-cyan)',
          boxShadow: '0 0 16px rgba(0,240,255,0.5), 0 0 32px rgba(0,240,255,0.25), inset 0 0 12px rgba(0,240,255,0.08)',
          background: 'rgba(0,240,255,0.06)',
          animation: 'pulse-glow 2s ease-in-out infinite',
        }}
      >
        {/* Mode toggle group */}
        <div className="flex rounded-lg overflow-hidden" style={{border:'1px solid rgba(0,240,255,0.3)'}}>
          <NeonButton
            active={mode === 'chat'}
            color="cyan"
            size="md"
            onClick={() => onModeChange('chat')}
          >
            {t('mode_chat')}
          </NeonButton>
          <NeonButton
            active={mode === 'search'}
            color="yellow"
            size="md"
            onClick={() => onModeChange('search')}
          >
            {t('mode_search')}
          </NeonButton>
        </div>

        {/* Separator */}
        <span className="w-px h-7" style={{background:'var(--color-neon-cyan)',opacity:0.5,boxShadow:'0 0 4px var(--color-neon-cyan)'}} />

        {/* Font size selector — accessibility */}
        <FontScaleToggle />

        {/* Separator */}
        <span className="w-px h-7" style={{background:'var(--color-neon-cyan)',opacity:0.5,boxShadow:'0 0 4px var(--color-neon-cyan)'}} />

        {/* Language switcher */}
        <NeonButton
          color="magenta"
          size="md"
          onClick={cycleLanguage}
          title={t('language')}
          aria-label={t('language')}
        >
          <span className="flex items-center gap-1.5">
            <span style={{fontSize:'1.1em'}}>◐</span>
            <span style={{color:'var(--color-neon-magenta)',textShadow:'0 0 6px var(--color-neon-magenta)'}}>{label}</span>
          </span>
        </NeonButton>
      </div>
    </header>
  )
}
