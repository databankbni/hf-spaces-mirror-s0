/**
 * Storage that never throws.
 *
 * In a sandboxed iframe (`sandbox="allow-scripts"` with no `allow-same-origin`)
 * even *reading* the `window.localStorage` getter throws a DOMException
 * ("Forbidden in a sandboxed document without the 'allow-same-origin' flag").
 * The Hub blog sanitizer hardcodes exactly that sandbox on every iframe, so our
 * `/embed/*` cards run as an opaque origin. An unguarded `window.localStorage`
 * access aborts React startup and leaves a blank frame.
 *
 * `safeStorage()` probes once for a usable Storage and otherwise returns an
 * in-memory shim with the same surface, so callers can persist optimistically
 * without branching on availability.
 */

type SafeStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">

function inMemoryStorage(): SafeStorage {
  const store = new Map<string, string>()
  return {
    getItem: (key) => (store.has(key) ? store.get(key)! : null),
    setItem: (key, value) => {
      store.set(key, String(value))
    },
    removeItem: (key) => {
      store.delete(key)
    },
  }
}

export function safeStorage(): SafeStorage {
  try {
    const probe = "__safe_storage_probe__"
    window.localStorage.setItem(probe, probe)
    window.localStorage.removeItem(probe)
    return window.localStorage
  } catch {
    return inMemoryStorage()
  }
}
