/**
 * Scanlines — fixed full-screen overlay with CRT scanlines + vignette.
 * Mount once at the app root for a consistent retro-CRT look.
 */
export default function Scanlines() {
  return (
    <div
      aria-hidden
      className="scanlines pointer-events-none fixed inset-0"
      style={{ zIndex: 9999 }}
    />
  )
}