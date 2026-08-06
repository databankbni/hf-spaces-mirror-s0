import { Component } from 'react'

/**
 * ErrorBoundary — catches render errors and displays a terminal-style fallback.
 * Wraps the main App content so the 3D background remains intact on crash.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            zIndex: 100,
            textAlign: 'center',
            fontFamily: 'var(--font-mono)',
            padding: '2rem',
          }}
        >
          <div
            style={{
              color: 'var(--color-neon-red)',
              fontSize: '1.2rem',
              fontWeight: 'bold',
              textShadow: '0 0 12px var(--color-neon-red)',
              marginBottom: '1rem',
              letterSpacing: '0.2em',
            }}
          >
            ⚡ SYSTEM ERROR
          </div>
          <div
            style={{
              color: 'var(--color-ink-dim)',
              fontSize: '0.8rem',
              marginBottom: '1.5rem',
            }}
          >
            A critical error occurred. Please reload the terminal.
          </div>
          <button
            onClick={() => window.location.reload()}
            style={{
              background: 'rgba(255,46,76,0.15)',
              color: 'var(--color-neon-red)',
              border: '1px solid rgba(255,46,76,0.4)',
              padding: '0.5rem 1.5rem',
              borderRadius: '0.5rem',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.75rem',
              cursor: 'pointer',
              letterSpacing: '0.15em',
              textShadow: '0 0 6px rgba(255,46,76,0.6)',
            }}
          >
            RELOAD SYSTEM
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
