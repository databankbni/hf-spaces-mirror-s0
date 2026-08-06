# ⚙️ Core Engine (`/core/`)

This folder contains the **Python backend engine** for ArunCore. It handles the FastAPI API server, AI reasoning loop (`gpt-4.1-nano`), vector database search, OpenAI studio voice synthesis, real-time GitHub data fetching, **100% automated Telegram notifications**, a **1-Click Magic Link 3-Way Real Human Takeover Engine**, a **Deterministic Human Control State Machine**, and the **Active Learning Memory Loop**.

---

## 📁 Files Overview & Descriptions

### 1. 🌐 `core/api.py` — FastAPI Web Server & 3-Way Live Chat Engine
- Runs the async HTTP server (`port 8000` locally, `port 7860` on Hugging Face Spaces).
- **Key Endpoints**:
  - `POST /chat`: Streams real-time AI responses token-by-token (NDJSON) with execution trace thoughts. Unconditionally queues automated Telegram chat alerts for EVERY visitor message.
  - `GET /chat/history`: Returns full central session chat transcript (`SESSION_CHAT_STORE`) so both visitor and Real Arun see the exact same 3-way conversation history in real time.
  - `POST /chat/human-message`: Receives live messages sent by Real Arun from the Admin Reply Bar or Telegram commands (`/answer`, `/release`). Automatically pairs Real Arun's answer with the visitor's question, appends to `data/raw/unknown_questions.json`, and triggers background ChromaDB vector DB re-ingestion!
  - `GET /chat/verify-admin-token`: Validates secure HMAC admin tokens generated for 1-click Telegram magic join links.
  - `POST /tts`: Converts AI text into HD neural studio voice using OpenAI `tts-1` (`alloy` voice).
  - `GET /health`: Health check endpoint showing active sessions, Telegram log statuses, and system uptime.

---

### 2. 🧠 `core/agent.py` — AI Persona, Agentic Loop & Tools
- Configures the main LLM (`gpt-4.1-nano`), persona system prompt, and tool functions.
- **Dynamic 100% Language Matching**: Responds in 100% articulate English for English queries with zero Hindi/Hinglish slang leaks. Responds naturally in Hinglish/Hindi when the user speaks Hindi.
- **3-Way Human Presence Injection**: When Real Arun is active in a session, dynamically injects a system notice containing Real Arun's messages into the prompt context so the AI Twin recognizes Real Arun's presence and co-pilots seamlessly.
- **Tools**:
  - `search_arun_knowledge`: Alias-aware project search (resolves `MedCoach` → `med_coach/README.md`), always includes `public_profile.md` and checks `data/raw/unknown_questions.json` for Arun's verified human answers.
  - `get_github_live_data`: Fetches real-time public repositories and recent commit activity from GitHub (`api.github.com/users/neural-arun/repos`).
  - `notify_arun`: Sends instant Telegram alerts (`@ai_twin_alert_bot`) for leads or urgent queries.
- **1-Click Magic Link Generation**: `generate_admin_token(session_id)` & `verify_admin_token(session_id, token)` create tamper-proof magic links (`https://aruncore.vercel.app/?session_id=...&admin_token=...`).
- **Active Learning**: `save_unknown_question_answer(question, answer)` appends verified Q&A pairs to `data/raw/unknown_questions.json` and triggers background re-ingestion.

---

### 3. 📚 `core/ingest.py` — Vector Database Compiler
- Scans all markdown and JSON files inside `data/`, chunks them semantically, generates vector embeddings (`text-embedding-3-small`), and compiles into ChromaDB (`db/`).
- **Smart JSON Parsing**: Specially parses `data/raw/unknown_questions.json` — each Q&A pair becomes its own searchable vector chunk.

---

### 4. 🤖 `core/bot.py` — Public Telegram Bot Service & Active Learning Handler
- Runs a standalone Telegram bot allowing visitors to interact with Arun's AI Assistant directly in Telegram.
- **Active Learning Reply Handler**: When Arun replies to an alert message in Telegram:
  1. Extracts original user question from alert message.
  2. Pairs with Arun's reply as verified answer.
  3. Saves to `data/raw/unknown_questions.json`.
  4. Triggers background ChromaDB re-ingestion.
  5. Sends Arun confirmation: *"✅ Answer Saved & Ingested into AI Memory!"*

---

### 5. 🧪 `core/evaluate.py` — Evaluation & Benchmarking Engine
- Stress-tests benchmark evaluations against test sets to measure retrieval precision and generation quality.
