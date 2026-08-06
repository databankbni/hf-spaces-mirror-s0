import axios from 'axios'

// API base URL.
//   Default `/api` — Vite proxies it to the FastAPI backend in dev (see vite.config.js).
//   In production, either set VITE_API_URL to a full origin (e.g. https://api.example.com)
//   or have your reverse-proxy (nginx/caddy) route `/api/*` to the backend.
const API_BASE = import.meta.env.VITE_API_URL || '/api'

const client = axios.create({
  baseURL: API_BASE,
  // LLM answers can take 30-60s end-to-end (retrieval + generation).
  // 90s gives enough headroom while still failing fast on real network issues.
  timeout: 90_000,
  headers: { 'Content-Type': 'application/json' },
})

/**
 * Health check
 * @returns {Promise<{status: string, documents: number, version: string}>}
 */
export async function healthCheck() {
  const { data } = await client.get('/health')
  return data
}

/**
 * Query the RAG system.
 * Backend signature (server.py QueryRequest):
 *   { query: string, top_k: int = 5, use_llm: bool = false }
 * Response (QueryResponse):
 *   { query, answer, citations[], products_found[], confidence }
 * @param {string} query
 * @param {object} [opts]
 * @param {number} [opts.topK=5]
 * @param {boolean} [opts.useLLM=false]  Backend default is False; turn on for LLM-generated answers (requires DeepSeek key).
 */
export async function queryRAG(query, { topK = 5, useLLM = false, signal } = {}) {
  const { data } = await client.post(
    '/query',
    { query, top_k: topK, use_llm: useLLM },
    { signal }
  )
  return data
}

/**
 * Raw context for external integrations.
 * @param {string} q
 * @param {number} topK
 */
export async function getContext(q, topK = 5) {
  const { data } = await client.get('/context', { params: { q, top_k: topK } })
  return data
}

export { client, API_BASE }