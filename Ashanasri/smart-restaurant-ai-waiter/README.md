---
title: Smart Restaurant AI Waiter
emoji: 🍽️
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

<div align="center">

# 🍽️ Smart Restaurant AI Waiter Service

### *"MLO" — a digital waiter brain that welcomes guests, explains dishes, advises on calories & allergies, and helps them order — in English and Swahili.*

![Node.js](https://img.shields.io/badge/Node.js-20_LTS-339933?style=for-the-badge&logo=nodedotjs&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5.5-3178C6?style=for-the-badge&logo=typescript&logoColor=white)
![Fastify](https://img.shields.io/badge/Fastify-5-000000?style=for-the-badge&logo=fastify&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-LLM_Inference-F55036?style=for-the-badge&logo=groq&logoColor=white)
![Llama 3.3](https://img.shields.io/badge/Llama_3.3-70B-0866FF?style=for-the-badge&logo=meta&logoColor=white)

![Zod](https://img.shields.io/badge/Zod-Validation-3E67B1?style=for-the-badge&logo=zod&logoColor=white)
![Axios](https://img.shields.io/badge/Axios-HTTP_Client-5A29E4?style=for-the-badge&logo=axios&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Container-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Hugging Face](https://img.shields.io/badge/🤗_Hugging_Face-Spaces-FFD21E?style=for-the-badge&logoColor=black)
![Tests](https://img.shields.io/badge/Tests-18%2F18_passing-16A34A?style=for-the-badge&logo=checkmarx&logoColor=white)

**[🌍 Live Demo (Chat UI)](https://ashanasri-smart-restaurant-ai-waiter.hf.space/ui)** ·
**[⚡ Live API](https://ashanasri-smart-restaurant-ai-waiter.hf.space/api/ai/chat)** ·
**[🤗 Space](https://huggingface.co/spaces/Ashanasri/smart-restaurant-ai-waiter)**

</div>

---

## 📖 What Is This?

Many restaurant guests don't fully understand the menu — *what is this dish made of? how many calories? is it safe for my allergy? what goes well with it?* This service is the **AI layer of a Smart Hotel & Restaurant System** that solves exactly that.

It is a production-ready **AI Waiter** ("MLO") that sits in the customer-facing app. Guests chat with it like a real waiter at the table. It:

- 🧑‍🍳 **Explains any dish** — composition, ingredients, calories, price, allergens
- 🥗 **Advises** — healthy / low-calorie / vegetarian / vegan / spicy / budget choices
- ⚠️ **Protects** — filters out dishes containing a guest's allergens
- 🛒 **Builds the order** — tracks picks, sums the exact total, then hands over to the *human* waiter who delivers the food (the AI never pretends to serve food itself)
- 🗣️ **Speaks the guest's language** — English, Swahili, or mixed, matching their tone
- 🧠 **Keeps learning** — reads the live menu from the backend database on every request (RAG), remembers each conversation, and tracks which dishes guests ask about most

> **Scope:** this repo is the **AI service only**. The Django backend (database/API) and the frontend already exist separately. This service consumes the backend's REST API and serves an AI chat API to the frontend. No ML model is trained; no paid APIs are used.

---

## 🧠 The Hybrid Brain (Architecture)

The waiter has **two brains** working together, so it is both *smart* and *unbreakable*:

```
                            POST /api/ai/chat
                                   │
                 ┌─────────────────▼─────────────────┐
                 │        chat.controller.ts          │  Zod validation, error mapping
                 └─────────────────┬─────────────────┘
                                   │
                 ┌─────────────────▼─────────────────┐
                 │           ai.service.ts            │  ORCHESTRATOR
                 └───┬──────────┬──────────┬─────────┘
                     │          │          │
        ┌────────────▼───┐  ┌───▼──────┐  ┌▼──────────────┐
        │ menu.service   │  │ ⚙️ RULE   │  │ conversation + │
        │ live menu from │  │  ENGINE  │  │ trend services │
        │ backend (RAG)  │  │          │  │ (memory)       │
        └────────────────┘  │ intent → │  └────────────────┘
                            │ filter → │
                            │ reply    │
                            └───┬──────┘
                                │ grounding + fallback
                 ┌──────────────▼────────────────────┐
                 │        🧠 llm.service.ts           │
                 │  Groq · Llama-3.3-70B (primary)    │
                 │  auto-cascade → Llama-3.1-8B on    │
                 │  rate limit → rule reply on failure│
                 └───────────────────────────────────┘
```

1. **⚙️ Rule engine** (deterministic, zero-cost): detects intent via bilingual keyword heuristics, filters the live menu (low-calorie, vegan, allergen-safe, cheapest…), and produces structured `results` + a solid fallback reply.
2. **🧠 Groq LLM** (conversational): receives the **live menu** (so it can never hallucinate dishes), the **conversation history**, the rule engine's **relevance hints**, and a **trending-dishes signal** — then replies like a warm, wise human waiter.
3. **🛟 Graceful degradation:** primary model rate-limited? → fast fallback model. Groq down entirely? → rule-based reply. Backend unreachable? → polite waiter apology. **The service never dies.**

### How "continuous learning" works (honest engineering)

No model training is involved (that would be slow, costly, and unnecessary). Instead, three live signals keep the waiter permanently up to date:

| Signal | Mechanism | Effect |
|---|---|---|
| 🍲 Menu changes in the DB | RAG — menu fetched fresh (30s cache) on every request | New dishes/prices/photos known instantly |
| 💬 The guest's own chat | Per-session history sent to the LLM | Remembers budget, allergies, order, mood |
| 📈 All guests' questions | `trend.service.ts` counts asked-about dishes | Waiter knows what's trending *today* |

---

## 🛠️ Technology Stack

| Technology | Role |
|---|---|
| ![Node.js](https://img.shields.io/badge/Node.js-339933?logo=nodedotjs&logoColor=white) | Runtime (v20 LTS) |
| ![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white) | Type-safe codebase, strict mode |
| ![Fastify](https://img.shields.io/badge/Fastify-000000?logo=fastify&logoColor=white) | High-performance HTTP server (chosen over Express for lower overhead) |
| ![Groq](https://img.shields.io/badge/Groq-F55036?logo=groq&logoColor=white) | Ultra-fast free LLM inference API |
| ![Meta Llama](https://img.shields.io/badge/Llama_3.3_70B-0866FF?logo=meta&logoColor=white) | Primary conversational model (+ Llama-3.1-8B-instant fallback) |
| ![Zod](https://img.shields.io/badge/Zod-3E67B1?logo=zod&logoColor=white) | Runtime validation of requests & backend payloads |
| ![Axios](https://img.shields.io/badge/Axios-5A29E4?logo=axios&logoColor=white) | Backend + Groq HTTP calls |
| ![dotenv](https://img.shields.io/badge/dotenv-ECD53F?logo=dotenv&logoColor=black) | Environment configuration |
| ![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white) | Multi-stage production image (non-root) |
| ![Hugging Face](https://img.shields.io/badge/🤗_HF_Spaces-FFD21E?logoColor=black) | Cloud deployment (Docker SDK, port 7860) |
| ![Node Test](https://img.shields.io/badge/node:test-5FA04E?logo=nodedotjs&logoColor=white) | 18 unit tests, zero test dependencies |

---

## 📂 Project Structure — What Every File Does

```
SMART_HOTEL_SYSTEM_AI_ENGINE/
├── src/
│   ├── server.ts                  # Fastify bootstrap: CORS, /health, /ui, demo-mode route,
│   │                              #   graceful shutdown. Entry point of the service.
│   ├── config.ts                  # ALL env vars read & validated in one place (port, backend
│   │                              #   URL, Groq key/models, cache & session TTLs, demo mode).
│   │
│   ├── api/
│   │   └── chat.controller.ts     # POST /api/ai/chat — validates body with Zod, calls the
│   │                              #   orchestrator, maps errors to clean waiter-friendly HTTP
│   │                              #   responses (400/404/502). Never leaks raw errors.
│   │
│   ├── services/
│   │   ├── ai.service.ts          # 🧩 THE ORCHESTRATOR. Runs the full pipeline per message:
│   │   │                          #   fetch menu → resolve follow-ups → detect intent → filter
│   │   │                          #   → LLM reply (with rule fallback) → save memory.
│   │   ├── llm.service.ts         # 🧠 Groq client. Builds the waiter persona system prompt,
│   │   │                          #   injects live menu (token-optimized RAG), chat history &
│   │   │                          #   trending dishes. Model cascade 70B → 8B → rules.
│   │   ├── menu.service.ts        # The ONLY caller of the Django backend. Fetches
│   │   │                          #   /api/restaurants/:slug/menu/, validates with Zod,
│   │   │                          #   normalizes (tags/images/snake_case), 30s cache,
│   │   │                          #   typed MenuFetchError for clean error handling.
│   │   ├── conversation.service.ts# Per-session memory keyed by sessionId: last results,
│   │   │                          #   pagination cursor, referenced dish, rolling chat
│   │   │                          #   transcript. TTL + size-capped, in-memory (Redis-ready).
│   │   └── trend.service.ts       # Live "learning": counts which dishes guests ask about
│   │                              #   (per restaurant, daily decay) → fed to the LLM.
│   │
│   ├── engine/                    # ⚙️ The deterministic rule brain (no ML, no network)
│   │   ├── intent.engine.ts       # Bilingual (EN+SW) weighted keyword intent detection:
│   │   │                          #   13 intents (healthy, vegan, allergen_check, cheapest,
│   │   │                          #   explain_food, greeting…) + dish-entity extraction.
│   │   ├── menu.filter.ts         # Pure filters per intent: calories thresholds, tag matches,
│   │   │                          #   allergen exclusion, price sorting, health scoring
│   │   │                          #   (drinks excluded from "healthy"), fuzzy dish lookup
│   │   │                          #   across name/description/ingredients.
│   │   ├── followup.engine.ts     # Conversational references: "show me more" (pagination),
│   │   │                          #   "the second one" / "ya pili" (ordinals), "tell me more
│   │   │                          #   about it / hiyo" (pronouns) — EN + SW.
│   │   └── response.builder.ts    # Rule-based waiter replies (the LLM's fallback): per-intent
│   │                              #   templates, menu-overview by sections, follow-up
│   │                              #   suggestions. Never returns raw JSON to users.
│   │
│   ├── types/
│   │   └── index.ts               # Single source of truth for types: Intent union, Zod
│   │                              #   schemas for the backend payload (defensive normalization
│   │                              #   of tags/calories/images), ChatRequest/ChatResponse.
│   │
│   ├── utils/
│   │   └── text.parser.ts         # NLP primitives: normalize (diacritics/punctuation),
│   │                              #   tokenize, phrase matching, Levenshtein fuzzy matching.
│   │
│   ├── demo/
│   │   └── demo-menu.json         # Built-in 72-dish sample menu (12 categories, EN+SW dishes,
│   │                              #   images, allergens, sold-out items). Served internally
│   │                              #   when DEMO_MODE=true — lets the cloud deployment work
│   │                              #   before the real backend is connected.
│   │
│   └── __tests__/
│       └── engine.test.ts         # 18 unit tests (node:test): intents EN/SW, filters,
│                                  #   allergen safety, no-hallucination, multi-turn memory,
│                                  #   pagination, ordinal references.
│
├── public/
│   └── index.html                 # Zero-dependency chat UI (served at /ui): chat bubbles,
│                                  #   session persistence, food cards with photos, clickable
│                                  #   suggestions, intent/engine badges per reply.
│
├── scripts/
│   └── mock-backend.js            # Local stand-in for the Django backend (npm run mock):
│                                  #   serves the 72-dish menu on :8000 for development.
│
├── Dockerfile                     # Multi-stage build (build+prune → slim runtime), non-root
│                                  #   user, port 7860 — ready for HF Spaces / any host.
├── .dockerignore                  # Keeps secrets & dev files out of the image.
├── .env.example                   # Documented template of every environment variable.
├── package.json                   # Scripts: build / start / dev / mock / test / typecheck.
└── tsconfig.json                  # Strict TypeScript config (ES2021, source maps).
```

---

## 🔌 API Reference

### `POST /api/ai/chat` — talk to the waiter

**Request**
```json
{
  "restaurantSlug": "demo-grand-restaurant",
  "message": "nipendekezee chakula chenye calories chache",
  "sessionId": "(omit on first message)"
}
```

**Response**
```json
{
  "sessionId": "261a01f4-…",
  "intent": "low_calorie",
  "confidence": 0.85,
  "engine": "llm",
  "reply": "Karibu! Kwa calories chache ninapendekeza Kachumbari (90 cal, 3,000 TZS)…",
  "suggestions": ["Would you like vegetarian options?"],
  "results": [
    {
      "id": "item-018", "name": "Kachumbari", "price": 3000, "calories": 90,
      "category": "Salads", "tags": ["vegetarian","vegan","low-calorie"],
      "is_available": true, "image": "https://…/kachumbari.jpg",
      "description": "Fresh tomato and onion salad"
    }
  ]
}
```

| Field | Frontend usage |
|---|---|
| `reply` | The waiter's message — render in the chat bubble |
| `sessionId` | **Store & echo back** every next message (conversation memory) |
| `results` | Dish data — render photo cards |
| `suggestions` | Clickable follow-up chips |
| `engine` | `llm` (Groq) or `rules` (fallback) — for analytics |

Other endpoints: `GET /health` (probe) · `GET /ui` (built-in chat UI) · `GET /` (service info).

### Backend contract (what this service consumes)

```
GET {BACKEND_BASE_URL}/api/restaurants/:slug/menu/
→ { "restaurant": {...}, "menuItems": [ { id, name, description, price,
    calories, ingredients, allergens, tags[], is_available, image, category:{name} } ] }
```
Tolerant to: `menu_items` (snake_case), tags as CSV string, `image_url`/`photo`/`picture`, numeric strings, missing fields.

---

## 🚀 Getting Started (Local)

```bash
# 1. Install
npm install

# 2. Configure
cp .env.example .env        # put your GROQ_API_WAITER key inside (free: console.groq.com)

# 3. Run — Terminal 1 (sample backend with 72 dishes)
npm run mock

# 4. Run — Terminal 2 (the AI service)
npm start                   # or: npm run dev (hot reload)

# 5. Chat!
# open http://localhost:4000/ui
```

No Groq key? The service automatically runs on the rule-based brain — fully functional, just less conversational.

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `PORT` / `HOST` | `4000` / `0.0.0.0` | Server binding |
| `BACKEND_BASE_URL` | `http://localhost:8000` | Django backend base URL |
| `DEMO_MODE` | auto | `true` → serve built-in 72-dish menu (no backend needed) |
| `GROQ_API_WAITER` | — | Groq API key (empty → rule-engine only) |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Primary LLM |
| `GROQ_MODEL_FALLBACK` | `llama-3.1-8b-instant` | Used when primary is rate-limited |
| `WAITER_NAME` | `MLO` | The waiter's persona name |
| `MENU_CACHE_TTL_MS` | `30000` | Menu cache lifetime |
| `SESSION_TTL_MS` / `SESSION_MAX` | 30 min / 5000 | Conversation memory limits |
| `LLM_MAX_HISTORY` | `10` | Chat turns sent to the LLM |
| `CORS_ORIGIN` | `*` | Allowed origins |

---

## ☁️ Deployment (Hugging Face Spaces — already live)

Deployed via the included multi-stage `Dockerfile` (Docker SDK, port 7860):

1. Space created: **[Ashanasri/smart-restaurant-ai-waiter](https://huggingface.co/spaces/Ashanasri/smart-restaurant-ai-waiter)**
2. Secrets/variables set in Space settings: `GROQ_API_WAITER` *(secret)*, `DEMO_MODE=true`, `WAITER_NAME=MLO`
3. Live at: **https://ashanasri-smart-restaurant-ai-waiter.hf.space/ui**

**Connecting the real backend later (2-minute switch, zero code changes):**
Space Settings → Variables → set `BACKEND_BASE_URL=https://your-django-backend.com` and `DEMO_MODE=false`. The Space restarts and the waiter instantly serves the real database menu, photos included.

---

## 🧪 Testing

```bash
npm run build
node --test dist/__tests__/     # 18/18 passing
```

Covers: bilingual intent detection, calorie/tag/allergen filters, price sorting, fuzzy dish lookup, **no-hallucination guarantees**, empty-menu handling, multi-turn memory (pagination, ordinals, pronoun references).

---

## 🛡️ Guardrails

- **Never hallucinates** — every dish, price, calorie and ingredient traces to backend data; the LLM prompt forbids inventing anything, and unknown dishes get an honest "not available".
- **Role boundaries** — the AI explains, advises and totals the order; it *never* claims to deliver food or take payments (human staff do that).
- **Listens first** — answers exactly what was asked; a declined offer is dropped, a goodbye is closed gracefully.
- **Safety-aware** — allergen questions always end with "please confirm with our kitchen staff".
- **Fails soft** — Groq outage → rule replies; backend outage → polite apology; malformed backend data → Zod-normalized, never a crash.
- **Secrets stay server-side** — the Groq key is never logged, never sent to the frontend, never committed.

---

## 📄 License

MIT © Smart Hotel System

<div align="center">
<sub>Built with ❤️ (and a lot of pilau) — <b>MLO</b> is waiting at the table: <a href="https://ashanasri-smart-restaurant-ai-waiter.hf.space/ui">talk to her</a>.</sub>
</div>
