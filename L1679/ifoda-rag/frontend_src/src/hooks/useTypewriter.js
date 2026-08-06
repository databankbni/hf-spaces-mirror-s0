import { useEffect, useRef, useState } from 'react'

/**
 * Typewriter effect: gradually reveals `text` one character at a time.
 * Returns the currently displayed prefix and a `done` flag.
 */
export function useTypewriter(text, { speed = 12, enabled = true, onDone } = {}) {
  const [out, setOut] = useState('')
  const [done, setDone] = useState(false)
  const timer = useRef(null)
  const onDoneRef = useRef(onDone)

  useEffect(() => {
    onDoneRef.current = onDone
  }, [onDone])

  useEffect(() => {
    if (!enabled || !text) {
      setOut(text || '')
      setDone(true)
      return
    }
    setOut('')
    setDone(false)
    let i = 0
    clearInterval(timer.current)
    timer.current = setInterval(() => {
      i += 1
      setOut(text.slice(0, i))
      if (i >= text.length) {
        clearInterval(timer.current)
        setDone(true)
        onDoneRef.current?.()
      }
    }, speed)
    return () => clearInterval(timer.current)
  }, [text, speed, enabled])

  return { text: out, done }
}