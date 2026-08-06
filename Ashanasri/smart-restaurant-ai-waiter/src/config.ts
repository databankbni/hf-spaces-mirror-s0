import dotenv from 'dotenv';

dotenv.config();

/**
 * Centralized, validated runtime configuration. Reading env vars in one place
 * keeps the rest of the codebase free of `process.env` access and makes the
 * service easy to reason about and test.
 */

function num(value: string | undefined, fallback: number): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

const port = num(process.env.PORT, 4000);

/**
 * Demo mode: serve a built-in sample menu instead of calling a real backend.
 * Active when DEMO_MODE=true, or when no BACKEND_BASE_URL is configured at all
 * (e.g. a fresh Hugging Face Space before the real backend is connected).
 */
const demoMode =
  process.env.DEMO_MODE === 'true' ||
  !(process.env.BACKEND_BASE_URL ?? '').trim();

export const config = {
  port,
  host: process.env.HOST ?? '0.0.0.0',
  demoMode,
  // In demo mode the menu service calls this same server's built-in demo route.
  backendBaseUrl: demoMode
    ? `http://127.0.0.1:${port}`
    : (process.env.BACKEND_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, ''),
  /**
   * Menu endpoint path template on the backend; `{slug}` is replaced per
   * request. Production (mlo.co.tz): /api/public/restaurants/{slug}/menu/
   */
  backendMenuPath: demoMode
    ? '/api/restaurants/{slug}/menu/'
    : (process.env.BACKEND_MENU_PATH ?? '/api/restaurants/{slug}/menu/'),
  /** Restaurants list path (for info: hours, delivery, phone). Production: /api/public/restaurants/ */
  backendRestaurantsPath: process.env.BACKEND_RESTAURANTS_PATH ?? '/api/restaurants/',
  backendTimeoutMs: num(process.env.BACKEND_TIMEOUT_MS, 5000),
  menuCacheTtlMs: num(process.env.MENU_CACHE_TTL_MS, 30000),
  // Conversation memory: how long a session is remembered, and a safety cap on
  // how many sessions we keep in memory at once.
  sessionTtlMs: num(process.env.SESSION_TTL_MS, 30 * 60 * 1000),
  sessionMax: num(process.env.SESSION_MAX, 5000),
  // ── Groq LLM (the conversational waiter brain) ────────────────────────────
  // When a key is present the waiter replies via Groq, grounded on live menu
  // data. When absent (or on any Groq failure) we fall back to the built-in
  // rule-based waiter, so the service always works.
  groqApiKey: (process.env.GROQ_API_WAITER ?? process.env.GROQ_API_KEY ?? '').trim(),
  groqModel: process.env.GROQ_MODEL ?? 'llama-3.3-70b-versatile',
  /** Tried when the primary model is rate-limited (Groq limits are per-model). */
  groqModelFallback: process.env.GROQ_MODEL_FALLBACK ?? 'llama-3.1-8b-instant',
  groqTimeoutMs: num(process.env.GROQ_TIMEOUT_MS, 20000),
  /** How many past chat turns to send to the LLM as conversation memory. */
  llmMaxHistory: num(process.env.LLM_MAX_HISTORY, 10),
  /**
   * Where learned guest insights are persisted (JSON). Set to '' to disable
   * persistence (in-memory only). On ephemeral hosts pair with periodic
   * harvesting via GET /api/ai/insights.
   */
  learningFile: process.env.LEARNING_FILE ?? './data/learning.json',
  logLevel: process.env.LOG_LEVEL ?? 'info',
  corsOrigin: process.env.CORS_ORIGIN ?? '*',
} as const;

export type AppConfig = typeof config;
