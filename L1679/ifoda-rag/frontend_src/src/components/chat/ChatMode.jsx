import { useTranslation } from 'react-i18next'
import { useEffect, useRef, useState, useCallback, memo } from 'react'
import { queryRAG } from '../../api/client'
import NeonInput from '../ui/NeonInput'
import LoadingGlitch from '../ui/LoadingGlitch'
import ConfidenceBadge from '../ui/ConfidenceBadge'
import Typewriter from '../ui/Typewriter'
import GlitchText from '../ui/GlitchText'
import CitationList from './CitationList'

// ── markdown parser with bullet lists, bold, italic, headings ──
function renderMarkdown(text) {
  if (!text) return null
  const lines = text.split('\n')
  const result = []
  let listItems = []

  const flushList = () => {
    if (listItems.length) {
      result.push(<ul key={`ul-${result.length}`} className="list-none pl-2 my-1 space-y-0.5">{listItems}</ul>)
      listItems = []
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (!line.trim()) { flushList(); result.push(<div key={i} className="h-2" />); continue }
    if (/^###\s/.test(line)) { flushList(); result.push(<h4 key={i} className="text-[0.85rem] font-bold mt-3 mb-1" style={{color:'var(--color-neon-yellow)'}}>{line.replace(/^###\s/,'')}</h4>); continue }
    if (/^##\s/.test(line)) { flushList(); result.push(<h3 key={i} className="text-[0.9rem] font-bold mt-3 mb-1" style={{color:'var(--color-neon-cyan)'}}>{line.replace(/^##\s/,'')}</h3>); continue }
    if (/^[-*•]\s/.test(line)) {
      const content = parseInline(line.replace(/^[-*•]\s/, ''))
      listItems.push(<li key={i} className="flex gap-2 text-[0.82rem]"><span style={{color:'var(--color-neon-cyan)'}}>▸</span><span>{content}</span></li>)
      continue
    }
    if (/^\d+[.)]\s/.test(line)) {
      const num = line.match(/^(\d+)/)[1]
      const content = parseInline(line.replace(/^\d+[.)]\s/, ''))
      listItems.push(<li key={i} className="flex gap-2 text-[0.82rem]"><span style={{color:'var(--color-neon-cyan)'}}>{num}.</span><span>{content}</span></li>)
      continue
    }
    flushList()
    result.push(<div key={i} className="leading-relaxed">{parseInline(line)}</div>)
  }
  flushList()
  return result
}

function parseInline(text) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g)
  return parts.map((p, j) => {
    if (/^\*\*/.test(p)) return <strong key={j} style={{color:'var(--color-neon-yellow)',textShadow:'0 0 4px var(--color-neon-yellow)'}}>{p.replace(/\*\*/g,'')}</strong>
    if (/^\*[^*]/.test(p)) return <em key={j} style={{color:'var(--color-neon-cyan)'}}>{p.replace(/\*/g,'')}</em>
    if (/^`/.test(p)) return <code key={j} className="px-1 rounded text-[0.8rem]" style={{background:'rgba(0,240,255,0.1)',color:'var(--color-neon-green)',fontFamily:'var(--font-mono)'}}>{p.replace(/`/g,'')}</code>
    return p
  })
}

const ChatMessage = memo(function ChatMessage({ msg, t }) {
  return (
    <div
      className="flex flex-col msg-enter"
      style={{
        alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
        maxWidth: '88%',
      }}
    >
      <div
        className="text-[0.6rem] tracking-[0.3em] uppercase mb-1 px-1"
        style={{
          color: msg.role === 'user' ? 'var(--color-neon-yellow)' : 'var(--color-neon-cyan)',
          textShadow: msg.role === 'user' ? '0 0 4px var(--color-neon-yellow)' : '0 0 4px var(--color-neon-cyan)',
          alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
        }}
      >
        {msg.role === 'user' ? t('role_user') : t('role_ai')}
      </div>
      <div
        className="px-4 py-3 rounded-lg corner-frame text-[0.85rem] leading-relaxed whitespace-pre-wrap break-words"
        style={{
          background: msg.role === 'user'
            ? 'linear-gradient(180deg, rgba(252,238,10,0.08) 0%, rgba(252,238,10,0.04) 100%)'
            : 'linear-gradient(180deg, rgba(0,240,255,0.10) 0%, rgba(0,240,255,0.04) 100%)',
          border: `1px solid ${msg.role === 'user' ? 'rgba(252,238,10,0.35)' : 'rgba(0,240,255,0.3)'}`,
          boxShadow: msg.role === 'user'
            ? '0 0 12px rgba(252,238,10,0.08)'
            : '0 0 16px rgba(0,240,255,0.08)',
        }}
      >
        {msg.role === 'ai' && msg.confidence && (
          <div className="mb-2"><ConfidenceBadge level={msg.confidence} /></div>
        )}
        {msg.role === 'user' ? (
          <span data-selectable style={{color:'var(--color-neon-yellow)',textShadow:'0 0 4px var(--color-neon-yellow)'}}>{msg.text}</span>
        ) : msg.error ? (
          <div>
            <div className="mb-2" style={{color:'var(--color-neon-red)'}} data-selectable>{msg.answer}</div>
            <button
              onClick={msg.onRetry}
              className="px-3 py-1 rounded text-[0.7rem] font-bold tracking-[0.15em] cursor-pointer transition-all hover:brightness-125"
              style={{
                background:'rgba(255,46,76,0.15)',
                color:'var(--color-neon-red)',
                border:'1px solid rgba(255,46,76,0.4)',
                textShadow:'0 0 6px rgba(255,46,76,0.5)',
                fontFamily:'var(--font-mono)',
              }}
            >
              {t('retry')}
            </button>
          </div>
        ) : (
          <span data-selectable style={{color:'#e0f0ff'}}>
            <Typewriter text={msg.answer || ''} speed={6} enabled={!msg.ready} />
            {msg.ready && renderMarkdown(msg.answer || '')}
          </span>
        )}
        {msg.role === 'ai' && msg.products?.length > 0 && (
          <div className="mt-3 pt-3 border-t" style={{borderColor:'rgba(252,238,10,0.2)'}}>
            <div className="text-[0.65rem] tracking-[0.2em] uppercase mb-2" style={{color:'var(--color-neon-yellow)'}}>
              {t('products_found')}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {msg.products.map((p) => (
                <span key={p} className="px-2 py-0.5 rounded text-[0.7rem]"
                  style={{background:'rgba(252,238,10,0.08)',color:'var(--color-neon-yellow)',border:'1px solid rgba(252,238,10,0.25)'}}
                >{p}</span>
              ))}
            </div>
          </div>
        )}
        {msg.role === 'ai' && msg.citations?.length > 0 && (
          <CitationList citations={msg.citations} />
        )}
      </div>
    </div>
  )
})

/**
 * ChatMode — conversational interface.
 *
 * Behaviors:
 *   - The chat window unfurls vertically (full height) when the user starts
 *     typing, and folds back when the input is empty / cleared / sent.
 *     The expansion is signalled to <App/> via window events.
 *   - Mouse wheel + arrow keys / PgUp / PgDn / Home / End scroll the chat
 *     history, even while the input is focused.
 *   - Enter sends, Shift+Enter inserts newline, Esc clears input.
 */
export default function ChatMode() {
  const { t } = useTranslation()
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const listRef = useRef(null)
  const inputRef = useRef(null)
  const abortRef = useRef(null)

  // Track whether the user is at the bottom of the chat
  const [stickToBottom, setStickToBottom] = useState(true)
  const onListScroll = useCallback(() => {
    const el = listRef.current
    if (!el) return
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight
    setStickToBottom(distance < 24)
  }, [])
  const scrollToBottom = useCallback((behavior = 'smooth') => {
    const el = listRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior })
  }, [])

  // Auto-scroll on new messages — only if user is at the bottom
  useEffect(() => {
    if (!listRef.current) return
    if (stickToBottom || messages.length <= 1) {
      listRef.current.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
    }
  }, [messages, loading, stickToBottom])

  // Focus the input on mount
  useEffect(() => {
    if (inputRef.current) inputRef.current.focus()
  }, [])

  // Keyboard handlers — work everywhere, including when the input is focused
  // (so the user can scroll the chat without leaving the textarea).
  useEffect(() => {
    const onKey = (e) => {
      const inInput = document.activeElement === inputRef.current
      // Modifier keys for nav (work even inside the textarea)
      if (e.key === 'PageUp')   { e.preventDefault(); listRef.current?.scrollBy({ top: -listRef.current.clientHeight * 0.9, behavior: 'smooth' }); return }
      if (e.key === 'PageDown') { e.preventDefault(); listRef.current?.scrollBy({ top:  listRef.current.clientHeight * 0.9, behavior: 'smooth' }); return }
      if (e.key === 'Home')     { e.preventDefault(); listRef.current?.scrollTo({ top: 0, behavior: 'smooth' }); return }
      if (e.key === 'End')      { e.preventDefault(); scrollToBottom('smooth'); return }
      if (!inInput && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
        e.preventDefault()
        listRef.current?.scrollBy({ top: e.key === 'ArrowUp' ? -40 : 40, behavior: 'smooth' })
        return
      }
      if (e.key === 'Escape' && inInput) {
        e.preventDefault()
        setInput('')
        window.dispatchEvent(new CustomEvent('panel:collapse'))
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [scrollToBottom])

  // Cancel pending request on unmount
  useEffect(() => {
    return () => {
      if (abortRef.current) abortRef.current.abort()
    }
  }, [])

  const send = useCallback(async (retryText) => {
    const q = (retryText || input).trim()
    if (!q || loading) return
    if (!retryText) {
      // Clear input but keep the window expanded — the user is reading the
      // AI's response and may want to type a follow-up. Collapse only happens
      // on explicit user action (Esc) or mode switch.
      setInput('')
    }
    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller

    const userMsg = { role: 'user', text: q, id: Date.now() }
    setMessages((m) => [...m, userMsg])
    setLoading(true)

    try {
      const res = await queryRAG(q, { topK: 5, useLLM: true, signal: controller.signal })
      setMessages((m) => [...m, {
        role: 'ai', id: Date.now() + 1,
        answer: res.answer,
        confidence: res.confidence,
        citations: res.citations || [],
        products: res.products_found || [],
        ready: true,
      }])
    } catch (err) {
      if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED') return
      setMessages((m) => [...m, {
        role: 'ai', id: Date.now() + 1,
        answer: t('error_offline'),
        confidence: 'low',
        error: true,
        onRetry: () => send(q),
        ready: true,
      }])
    }
    setLoading(false)
    abortRef.current = null
  }, [input, loading, t])

  // Unfurl the window on the first character and keep it open. The window
  // collapses only on explicit user action (Esc) or mode switch — clearing
  // the input manually or after a send does NOT collapse it.
  const onInputChange = useCallback((e) => {
    const v = e.target.value
    setInput(v)
    if (v.length > 0) window.dispatchEvent(new CustomEvent('panel:expand'))
  }, [])

  const onInputKey = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }, [send])

  return (
    <div className="relative flex-1 min-h-0 flex flex-col" style={{fontFamily:'var(--font-mono)'}}>
      {/* Messages */}
      <div
        ref={listRef}
        onScroll={onListScroll}
        className="flex-1 min-h-0 overflow-y-scroll px-4 md:px-5 py-4 pb-4 chat-scroll"
        style={{
          display:'flex',
          flexDirection:'column',
          gap:'14px',
          scrollbarGutter:'stable',
          cursor: stickToBottom ? 'default' : 'ns-resize',
        }}
        role="log" aria-label={t('chat_log')} aria-live="polite"
      >
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center text-center mt-16 gap-1" style={{fontFamily:'var(--font-mono)'}}>
            <GlitchText as="div" color="cyan" className="text-[1.2rem] font-bold tracking-[0.25em]" style={{fontFamily:'var(--font-display)'}}>
              {t('empty_title')}
            </GlitchText>
            <div className="text-[0.85rem] tracking-wider mt-1" style={{color:'var(--color-neon-cyan)',textShadow:'0 0 6px var(--color-neon-cyan)'}}>
              {t('empty_subtitle')}
            </div>
            <div className="text-[0.8rem] tracking-[0.15em] mt-2"
              style={{color:'var(--color-neon-yellow)',textShadow:'0 0 6px var(--color-neon-yellow)'}}>
              {t('empty_hint')}
            </div>
            <div className="flex gap-4 mt-4 text-[0.65rem] tracking-[0.15em]" style={{color:'var(--color-ink-faint)',fontFamily:'var(--font-mono)'}}>
              <span>⏎ Enter — {t('send')}</span>
              <span>⇧⏎ Shift+Enter — ↲</span>
              <span>Esc — {t('clear')}</span>
            </div>
          </div>
        )}

        {messages.map((m) => (
          <ChatMessage key={m.id} msg={m} t={t} />
        ))}

        {loading && (
          <div className="self-start"><LoadingGlitch mode="chat" /></div>
        )}

        {!stickToBottom && (
          <button
            onClick={() => scrollToBottom('smooth')}
            aria-label={t('scroll_to_latest', { defaultValue: 'К последнему сообщению' })}
            className="sticky bottom-2 self-end mr-2 px-3 py-1.5 rounded-full text-[0.7rem] font-bold tracking-[0.2em] cursor-pointer transition-all hover:brightness-125"
            style={{
              background: 'rgba(0,240,255,0.18)',
              color: 'var(--color-neon-cyan)',
              border: '1px solid rgba(0,240,255,0.5)',
              boxShadow: '0 0 12px rgba(0,240,255,0.35), inset 0 0 6px rgba(0,240,255,0.1)',
              fontFamily: 'var(--font-mono)',
              textShadow: '0 0 6px var(--color-neon-cyan)',
              backdropFilter: 'blur(4px)',
            }}
          >
            ↓ {t('latest', { defaultValue: 'К НОВЫМ' })}
          </button>
        )}
      </div>

      {/* Input dock — fixed size; the WINDOW around it expands, not this */}
      <div
        className="shrink-0 px-3 md:px-4 py-2 md:py-3"
        style={{
          background: 'linear-gradient(transparent 0%, rgba(4,4,17,0.9) 30%)',
        }}
      >
        <div
          className="flex items-center gap-2 rounded-xl px-2 py-1"
          style={{
            background: 'rgba(0,0,0,0.6)',
            border: '1px solid rgba(0,240,255,0.35)',
            boxShadow: '0 0 20px rgba(0,240,255,0.12), inset 0 0 12px rgba(0,240,255,0.05)',
          }}
        >
          <span className="pl-2 select-none" style={{color:'var(--color-neon-cyan)',fontFamily:'var(--font-mono)'}}>❯</span>
          <NeonInput
            ref={inputRef}
            multiline
            maxRows={6}
            value={input}
            onChange={onInputChange}
            onKeyDown={onInputKey}
            placeholder={t('placeholder_chat')}
            disabled={loading}
            aria-label={t('placeholder_chat')}
          />
          <button
            onClick={() => send()}
            disabled={loading || !input.trim()}
            aria-label={t('send')}
            className="px-4 py-1.5 rounded-lg font-bold transition-all cursor-pointer"
            style={{
              background: loading || !input.trim() ? 'rgba(0,240,255,0.05)' : 'rgba(0,240,255,0.2)',
              color: loading || !input.trim() ? 'var(--color-ink-faint)' : 'var(--color-neon-cyan)',
              border: '1px solid rgba(0,240,255,0.3)',
              fontFamily: 'var(--font-mono)',
              textShadow: !loading && input.trim() ? '0 0 6px var(--color-neon-cyan)' : 'none',
              cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
            }}
          >{t('send')}</button>
        </div>
      </div>
    </div>
  )
}