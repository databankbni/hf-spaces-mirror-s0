import { useState, lazy, Suspense, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import NightCity from './components/background/NightCity'
import TopBar from './components/layout/TopBar'
import BottomHUD from './components/layout/BottomHUD'
import HoloPanel from './components/ui/HoloPanel'
import Scanlines from './components/ui/Scanlines'
import RainGlass from './components/ui/RainGlass'
import DigitalRain from './components/ui/DigitalRain'
import ErrorBoundary from './components/ui/ErrorBoundary'
import LoadingGlitch from './components/ui/LoadingGlitch'
import { useTelegram } from './hooks/useTelegram'

const ChatMode = lazy(() => import('./components/chat/ChatMode'))
const SearchMode = lazy(() => import('./components/search/SearchMode'))

export default function App() {
  const { t } = useTranslation()
  const [mode, setMode] = useState('chat')
  const { isTelegram } = useTelegram()

  // Panel "unfurls" like a scroll while the user is typing in any mode.
  // ChatMode / SearchMode dispatch `panel:expand` / `panel:collapse` events.
  const [panelExpanded, setPanelExpanded] = useState(false)
  useEffect(() => {
    const onExpand = () => setPanelExpanded(true)
    const onCollapse = () => setPanelExpanded(false)
    window.addEventListener('panel:expand', onExpand)
    window.addEventListener('panel:collapse', onCollapse)
    return () => {
      window.removeEventListener('panel:expand', onExpand)
      window.removeEventListener('panel:collapse', onCollapse)
    }
  }, [])

  // Collapse automatically when the user switches modes.
  useEffect(() => {
    window.dispatchEvent(new CustomEvent('panel:collapse'))
  }, [mode])

  return (
    <div
      className={isTelegram ? 'tg-webapp' : ''}
      style={{
        position: 'relative',
        width: '100vw',
        height: '100vh',
        overflow: 'hidden',
        background: '#04040f',
      }}
    >
      {/* 3D Night City background */}
      <NightCity />

      {/* Digital rain overlay — between 3D and UI */}
      <DigitalRain density={35} speed={0.5} />

      {/* Top bar */}
      <TopBar mode={mode} onModeChange={setMode} />

      {/* Centered interactive panel — unfurls to full vertical when chat is expanded */}
      <ErrorBoundary>
        <main
          id="main-content"
          className="absolute"
          style={{
            top: panelExpanded ? '40px' : '50%',
            left: '50%',
            transform: panelExpanded ? 'translate(-50%, 0)' : 'translate(-50%, -50%)',
            zIndex: 20,
            width: 'min(720px, 96vw)',
            height: panelExpanded
              ? 'calc(100vh - 80px)'
              : 'min(560px, 76vh)',
            maxHeight: 'calc(100vh - 80px)',
            transition: 'top 0.45s cubic-bezier(0.4, 0, 0.2, 1), transform 0.45s cubic-bezier(0.4, 0, 0.2, 1), height 0.45s cubic-bezier(0.4, 0, 0.2, 1), width 0.45s cubic-bezier(0.4, 0, 0.2, 1)',
          }}
        >
          <HoloPanel
            color="cyan"
            title={mode === 'chat' ? t('panel_chat') : t('panel_search')}
            className="w-full h-full"
            transparent={panelExpanded}
          >
            <Suspense fallback={
              <div className="flex justify-center items-center h-full">
                <LoadingGlitch mode={mode} />
              </div>
            }>
              <div key={mode} className="mode-enter flex-1 min-h-0 flex flex-col">
                {mode === 'chat' ? <ChatMode /> : <SearchMode />}
              </div>
            </Suspense>
          </HoloPanel>
        </main>
      </ErrorBoundary>

      {/* Bottom HUD */}
      <BottomHUD />

      {/* Raindrop glass overlay */}
      <RainGlass />

      {/* CRT scanlines + vignette */}
      <Scanlines />
    </div>
  )
}
