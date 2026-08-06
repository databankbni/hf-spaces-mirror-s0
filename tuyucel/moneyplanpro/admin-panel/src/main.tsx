import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { fetchRuntimeConfig } from './config'

// Fetch runtime config before rendering app
try {
  await fetchRuntimeConfig()
  // App and its Supabase client read runtime config during module evaluation,
  // so import them only after the config request has completed.
  const { default: App } = await import('./App.tsx')
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
} catch (error) {
  console.error('Failed to load configuration:', error)
  // Show error to user
  document.getElementById('root')!.innerHTML = `
    <div style="display: flex; align-items: center; justify-content: center; height: 100vh; font-family: sans-serif;">
      <div style="text-align: center; max-width: 500px; padding: 2rem;">
        <h1 style="color: #ff4d4f;">⚠️ Configuration Error</h1>
        <p>Failed to load application configuration. Please check the backend connection.</p>
        <p style="color: #8c8c8c; font-size: 14px;">${error instanceof Error ? error.message : String(error)}</p>
        <button onclick="location.reload()" style="margin-top: 1rem; padding: 0.5rem 1rem; cursor: pointer;">
          Retry
        </button>
      </div>
    </div>
  `
}
