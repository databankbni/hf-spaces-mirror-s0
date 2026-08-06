import { useState, useRef, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { queryRAG } from '../../api/client'
import NeonInput from '../ui/NeonInput'
import LoadingGlitch from '../ui/LoadingGlitch'
import ConfidenceBadge from '../ui/ConfidenceBadge'
import Typewriter from '../ui/Typewriter'
import GlitchText from '../ui/GlitchText'
import CitationList from '../chat/CitationList'

/**
 * SearchMode — single-shot search with debounce, abort, retry, keyboard shortcuts.
 */
export default function SearchMode() {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const abortRef = useRef(null)
  const debounceRef = useRef(null)
  const inputRef = useRef(null)

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (abortRef.current) abortRef.current.abort()
    }
  }, [])

  // Keyboard: Escape clears input/results
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') {
        if (results || error) { setResults(null); setError('') }
        else if (query) {
          setQuery('')
          window.dispatchEvent(new CustomEvent('panel:collapse'))
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [results, error, query])

  const doSearch = useCallback(async (q) => {
    const text = (q ?? query).trim()
    if (!text || loading) return
    if (!q) setQuery(text)

    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    setError('')
    setResults(null)

    try {
      const res = await queryRAG(text, { topK: 5, useLLM: true, signal: controller.signal })
      setResults(res)
    } catch (err) {
      if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED') return
      setError(t('error_offline'))
    }
    setLoading(false)
    abortRef.current = null
  }, [query, loading, t])

  const onKey = useCallback((e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      doSearch()
    }
  }, [doSearch])

  // Unfurl the panel on first character; collapse on clear.
  const onInputChange = useCallback((e) => {
    const v = e.target.value
    setQuery(v)
    if (v.length > 0) window.dispatchEvent(new CustomEvent('panel:expand'))
    else              window.dispatchEvent(new CustomEvent('panel:collapse'))
  }, [])

  const onClear = useCallback(() => {
    setQuery('')
    setResults(null)
    setError('')
    window.dispatchEvent(new CustomEvent('panel:collapse'))
  }, [])

  return (
    <div className="relative h-full overflow-y-auto px-5 py-4 flex flex-col gap-4" style={{fontFamily:'var(--font-mono)'}}>
      {/* Search bar */}
      <div className="flex items-center gap-2 rounded-xl px-2 py-1 sticky top-0 z-10"
        style={{background:'rgba(4,4,17,0.92)',backdropFilter:'blur(6px)',border:'1px solid rgba(0,240,255,0.45)',boxShadow:'0 0 24px rgba(0,240,255,0.15), inset 0 0 16px rgba(0,240,255,0.05)'}}>
        <span className="pl-2 select-none" style={{color:'var(--color-neon-cyan)',fontFamily:'var(--font-mono)'}}>⌕</span>
        <NeonInput
          ref={inputRef}
          multiline
          maxRows={6}
          value={query}
          onChange={onInputChange}
          onKeyDown={onKey}
          placeholder={t('placeholder_search')}
          disabled={loading}
        />
        {/* Clear button — visible when there's input */}
        {query.trim() && (
          <button onClick={onClear}
            className="px-2 py-1 text-[0.7rem] cursor-pointer hover:brightness-125 transition-all"
            style={{color:'var(--color-ink-faint)',fontFamily:'var(--font-mono)'}}
            title={t('clear')}
          >✕</button>
        )}
        <button onClick={() => doSearch()} disabled={loading || !query.trim()}
          aria-label={t('search')}
          className="px-5 py-2 rounded-lg font-bold transition-all tracking-[0.2em] cursor-pointer"
          style={{
            background: loading || !query.trim() ? 'rgba(252,238,10,0.05)' : 'rgba(252,238,10,0.2)',
            color: loading || !query.trim() ? 'var(--color-ink-faint)' : 'var(--color-neon-yellow)',
            border: '1px solid rgba(252,238,10,0.4)',
            fontFamily:'var(--font-mono)',fontSize:'0.8rem',
            textShadow: !loading && query.trim() ? '0 0 6px var(--color-neon-yellow)' : 'none',
            cursor: loading || !query.trim() ? 'not-allowed' : 'pointer',
          }}
        >{loading ? '...' : t('search')}</button>
      </div>

      {error && (
        <div className="flex flex-col items-center gap-3 py-6">
          <div className="text-[0.85rem] tracking-[0.15em]"
            style={{color:'var(--color-neon-red)',textShadow:'0 0 6px var(--color-neon-red)'}}>
            {error}
          </div>
          <button onClick={() => doSearch(query)} className="px-4 py-1.5 rounded text-[0.7rem] font-bold tracking-[0.15em] cursor-pointer transition-all hover:brightness-125"
            style={{background:'rgba(255,46,76,0.15)',color:'var(--color-neon-red)',border:'1px solid rgba(255,46,76,0.4)',textShadow:'0 0 6px rgba(255,46,76,0.5)',fontFamily:'var(--font-mono)'}}>
            {t('retry')}
          </button>
        </div>
      )}

      {/* Empty state */}
      {!results && !loading && !error && (
        <div className="flex flex-col items-center justify-center text-center mt-8 gap-1">
          <GlitchText as="div" color="cyan" className="text-[1.1rem] font-bold tracking-[0.25em]" style={{fontFamily:'var(--font-display)'}}>
            {t('empty_title')}
          </GlitchText>
          <div className="text-[0.8rem] tracking-wider mt-1" style={{color:'var(--color-ink-dim)'}}>{t('empty_subtitle')}</div>
          <div className="text-[0.75rem] tracking-[0.15em] mt-2" style={{color:'var(--color-neon-yellow)',textShadow:'0 0 6px var(--color-neon-yellow)'}}>
            ⏎ Enter — {t('search')}
          </div>
          <div className="text-[0.65rem] tracking-[0.15em] mt-1" style={{color:'var(--color-ink-faint)',fontFamily:'var(--font-mono)'}}>
            Esc — {t('clear')}
          </div>
        </div>
      )}

      {loading && (<div className="flex justify-center py-8"><LoadingGlitch mode="search" /></div>)}

      {results && !loading && (
        <div className="flex flex-col gap-4 pb-4">
          {/* Result header */}
          <div className="flex items-center justify-between rounded-lg px-4 py-2.5"
            style={{background:'rgba(0,240,255,0.06)',border:'1px solid rgba(0,240,255,0.2)'}}>
            <div className="flex items-center gap-2 text-[0.7rem] tracking-[0.2em] uppercase">
              <span style={{color:'var(--color-ink-dim)'}}>{t('results_for')}</span>
              <span style={{color:'var(--color-neon-cyan)',textShadow:'0 0 6px var(--color-neon-cyan)',fontWeight:'bold'}} data-selectable>
                {results.query || query}
              </span>
            </div>
            <ConfidenceBadge level={results.confidence} />
          </div>

          {/* Answer */}
          <div className="px-5 py-4 rounded-xl"
            style={{background:'linear-gradient(180deg, rgba(0,240,255,0.08) 0%, rgba(0,240,255,0.02) 100%)',border:'1px solid rgba(0,240,255,0.25)',boxShadow:'0 0 16px rgba(0,240,255,0.06)'}}>
            <div className="flex items-center gap-2 mb-3">
              <GlitchText as="span" color="cyan" className="text-[0.7rem] font-bold tracking-[0.25em] uppercase">
                {t('section_answer')}
              </GlitchText>
            </div>
            <div className="text-[0.9rem] leading-relaxed whitespace-pre-wrap" style={{color:'var(--color-ink)'}} data-selectable>
              <Typewriter text={results.answer || ''} speed={4} enabled={!loading} />
            </div>
          </div>

          {/* Products */}
          {results.products_found?.length > 0 && (
            <div className="rounded-xl p-4"
              style={{background:'linear-gradient(180deg, rgba(252,238,10,0.06) 0%, rgba(252,238,10,0.02) 100%)',border:'1px solid rgba(252,238,10,0.25)'}}>
              <div className="text-[0.7rem] font-bold tracking-[0.25em] uppercase mb-3" style={{color:'var(--color-neon-yellow)'}}>
                {t('products_found')}
              </div>
              <div className="flex flex-wrap gap-2">
                {results.products_found.map((p) => (
                  <span key={p} className="px-2.5 py-1 rounded-md text-[0.75rem]"
                    style={{background:'rgba(252,238,10,0.1)',color:'var(--color-neon-yellow)',border:'1px solid rgba(252,238,10,0.3)',textShadow:'0 0 4px var(--color-neon-yellow)'}}
                  >{p}</span>
                ))}
              </div>
            </div>
          )}

          {/* No results */}
          {!results.answer && !results.products_found?.length && !results.citations?.length && (
            <div className="text-center py-6 text-[0.8rem] tracking-[0.15em]" style={{color:'var(--color-ink-dim)'}}>
              {t('no_results')}
            </div>
          )}

          {/* Citations */}
          {results.citations?.length > 0 && <CitationList citations={results.citations} />}
        </div>
      )}
    </div>
  )
}
