import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// Backend origin for the Vite dev proxy. Matches the FastAPI server started
// by `scripts/start-dev.ps1` (or `npm run dev:api`).
const BACKEND_ORIGIN = 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(process.cwd(), 'src'),
    },
  },
  server: {
    port: 5173,
    host: true,
    // Forward `/api/*` to the backend so the frontend can call same-origin URLs.
    // Default VITE_API_URL is `/api` (see src/api/client.js) so dev just works.
    // Set VITE_API_URL=https://api.example.com to bypass the proxy.
    proxy: {
      '/api': {
        target: BACKEND_ORIGIN,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
        configure: (proxy) => {
          proxy.on('error', (err) => {
            console.error('[vite-proxy] backend unreachable:', err.message)
          })
        },
      },
    },
  },
  build: {
    sourcemap: false,
  },
})