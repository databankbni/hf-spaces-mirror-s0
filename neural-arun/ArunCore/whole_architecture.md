# ArunCore: Complete System Blueprint & Master Architecture

This document presents the complete architectural specification for **ArunCore** — a production-grade, stateful, agentic portfolio, AI assistant, and 3-Way Live Human Takeover engine.

---

# Phase 0: Core Philosophy & Answer Policy

ArunCore is NOT a generic chatbot wrapper; it is a **Grounded Reasoning Engine** governed by strict rules.

### 1. The Answer Policy (Enforced via System Prompt):
1. **Never Invent or Inflate:** Do not hallucinate impact, fake scores, or invent metrics.
2. **"I Don't Know" is Valid:** If retrieval confidence is low, state it doesn't have the info and offers to ping Arun directly.
3. **Value & Problem-Solving First:** On project inquiries, lead with **WHAT problem it solves, HOW MUCH time/cost it saves, and THE REAL BUSINESS IMPACT** before code details.
4. **Dynamic 100% Language Matching:** Clean, articulate English for corporate/international queries; natural Hinglish for Hindi chats.
5. **3-Way Human Presence Co-Pilot**: When Real Arun joins the live chat, the AI Twin recognizes his presence and co-pilots alongside him seamlessly.

---

# Phase 1: Data Architecture & Storage Layers

### A. The Static Knowledge Layer
- `data/static/public_profile.md` (Bio, technical skills, enriched project value specs, contact info).
- `data/static/rules_of_engagement.md` (System prompts, guardrails, and answer policies).
- `data/linkedin/profile_summary.md` (Synced LinkedIn technical write-ups and posts).

### B. The Dynamic Knowledge Layer (Vector DB)
- **Vector Database**: ChromaDB (`db/`) with `text-embedding-3-small` embeddings.
- **Sparse Index**: BM25 keyword matching engine.
- **Real-Time Active Learning Store**: `data/raw/unknown_questions.json` (auto-ingests Real Arun's verified human answers from website Admin Reply Bar or Telegram swipe replies).

---

# Phase 2: Retrieval, Routing & Execution Loop

```
┌─────────────────────────────────────────────────────────────┐
│                       User Query                            │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                Agentic Execution Loop                       │
│                 (LLM: gpt-4.1-nano)                         │
└──────────────┬───────────────┼───────────────┬──────────────┘
               │               │               │
      [search_arun_knowledge] [get_github_live] [notify_arun]
               │               │               │
┌──────────────▼──────────────┐│        ┌──────▼──────────────┐
│  Hybrid RAG (Chroma + BM25) ││        │ Vercel Relay        │
│   + Cohere V3 Reranker      ││        │ Telegram Alerts     │
└──────────────┬──────────────┘│        └──────┬──────────────┘
               │               │               │
┌──────────────▼───────────────▼───────────────▼──────────────┐
│              1-Click Magic Link Admin Mode                  │
│       (Real Arun joins 3-Way Live Chat Room on Website)     │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│             Real-Time Token Stream (NDJSON)                 │
└─────────────────────────────────────────────────────────────┘
```

---

# Phase 3: The Production Tech Stack

| Layer | Component | Specification |
| :--- | :--- | :--- |
| **LLM Engine** | OpenAI `gpt-4.1-nano` | Ultra-low latency, $0.05/1M input, $0.15/1M output |
| **Embedding Model** | OpenAI `text-embedding-3-small` | 1536-dimensional dense vector embeddings |
| **Vector DB** | ChromaDB (`db/`) | Persistent vector store with metadata filtering |
| **Keyword Search** | BM25 Engine | Sparse keyword indexing for exact technical term recall |
| **Reranker Engine** | Cohere English V3 | Cross-encoder reranking candidate chunks to top 3–5 |
| **Voice Studio** | OpenAI `tts-1` (`alloy` voice) & Web Speech | HD Neural Speech synthesis (`/tts`) & Speech-to-Text (`[ 🎙️ ]`) |
| **Frontend Framework**| Next.js 16 (Turbopack) | React 19, Tailwind CSS, 3-Way Live Chat UI, Vercel deployment |
| **Backend Server** | FastAPI (Python 3.11) | Async HTTP server with NDJSON streaming (`/chat`) & 3-way history sync |
| **Egress Relay** | Next.js Serverless Route | `/api/telegram` serverless endpoint bypassing HF Space firewall blocks |
| **Human Control** | Deterministic State Machine | AI Twin pauses on human takeover, resumes on `/answer` or `/release` |
| **Hosting** | Hugging Face Spaces & Vercel | HF Docker Space (port 7860) & Vercel (`aruncore.vercel.app`) |

---

# Phase 4: Operations & Integration Testing

1. **Automated Integration Test Suite**:
   - Run `python3 tests/test_system.py` to test RAG search, Live GitHub sync, Active Learning Loop, Telegram Alert delivery, and Agent execution.

2. **Master Operations Guide**:
   - Refer to [`OPERATIONS_GUIDE.md`](file:///home/arun/projects/profile/OPERATIONS_GUIDE.md) for step-by-step operational instructions.