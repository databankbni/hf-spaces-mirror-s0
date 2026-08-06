# ArunCore: High-Level System Design & Architecture

This document outlines the production architecture, component interactions, state machine, and data flows for **ArunCore**.

---

## 🏗️ System Architecture Diagram

```mermaid
graph TD
    User["User Interface<br/>(Next.js 16 • 3-Way Live Chat)"] -->|HTTP /chat NDJSON| API["FastAPI Web Server<br/>(Local :8000 / HF Docker :7860)"]
    
    %% 3-Way Live Chat Takeover
    TelegramAlert["Telegram Alert Bot<br/>(@ai_twin_alert_bot)"] -->|1-Click Magic Join Link| AdminMode["1-Click Admin Mode<br/>(aruncore.vercel.app/?session_id=...&admin_token=...)"]
    AdminMode -->|POST /chat/human-message| API
    API -->|1.5s Polling GET /chat/history| User

    %% Vercel Relay
    API -->|Outbound Alerts| VercelRelay["Vercel Egress Relay<br/>(/api/telegram)"]
    VercelRelay --> TelegramAlert

    %% Intent & Tool Routing
    API --> Agent["Agentic Execution Loop<br/>(LLM: gpt-4.1-nano)"]
    
    Agent -->|Tool: search_arun_knowledge| HybridRAG["Hybrid RAG Pipeline"]
    Agent -->|Tool: get_github_live_data| GitHubAPI["GitHub Live API"]
    Agent -->|Tool: notify_arun| TelegramAlert

    %% Hybrid RAG Pipeline
    subgraph Hybrid RAG Pipeline
        HybridRAG --> Dense["ChromaDB Vector Search<br/>(text-embedding-3-small)"]
        HybridRAG --> Sparse["BM25 Keyword Matching"]
        Dense --> Combine["Candidate Assembly (Top 20)"]
        Sparse --> Combine
        Combine --> Rerank["Cohere English V3 Reranker"]
        Rerank --> TopContext["High-Confidence Context (Top 3-5)"]
    end

    %% Active Learning
    AdminMode -->|Auto-Ingest Q&A| UnknownJSON["data/raw/unknown_questions.json"]
    TelegramAlert -->|Swipe Reply Q&A| UnknownJSON
    UnknownJSON -->|Background Re-Ingest| ChromaDB["ChromaDB Vector Memory"]

    %% Value-First Synthesizer
    TopContext --> Synthesizer["Value-First Prompt Synthesizer<br/>(Problem Solved • Time Saved • Business Impact)"]
    GitHubAPI --> Synthesizer
    
    Synthesizer --> Agent
    Agent -->|Token Stream & Thoughts| API
    API -->|NDJSON Stream| User
```

---

## 📁 Component Breakdown

### 1. 💻 User Interface (Next.js 16 • Vercel Deployment)
- **3-Way Live Chat**: Unified chat room displaying messages for Web Visitor (`user`), AI Assistant (`twin`), and Real Arun (`human_arun`) with a glowing green verified badge (`👨‍💻 Arun Yadav [VERIFIED HUMAN] 🟢`).
- **1-Click Magic Link Admin Mode**: Tapping a Telegram magic link opens `aruncore.vercel.app` in Admin Mode, unlocking the Admin Reply Bar (`[ 👨‍💻 SEND AS REAL ARUN ]`, `[ 🤖 Trigger AI Answer (/answer) ]`, `[ 🔄 Hand Back to AI (/release) ]`).
- **Voice Studio**: STT microphone button with duplicate-free transcription & HD neural TTS voice button (`/tts` endpoint).

### 2. 🌐 FastAPI Backend Server (`core/api.py`)
- Manages real-time NDJSON streaming (`/chat`), 3-way transcript persistence (`GET /chat/history`), human message submission (`POST /chat/human-message`), and admin token verification (`GET /chat/verify-admin-token`).

### 3. 🕹️ Deterministic Human Control State Machine
- **Normal Default Mode**: AI Twin answers visitor questions automatically.
- **Human Control Mode**: Real Arun's first response pauses the AI Twin. Visitor questions wait for Real Arun's reply or command.
- **`/answer` Command**: Triggers the AI Twin to synthesize all 3 participants' messages and generate a response.
- **`/release` Command**: Hands control back to automatic AI Twin responses.

### 4. 🌐 Vercel Serverless Egress Relay (`frontend/app/api/telegram/route.ts`)
- Routes outbound Telegram POST requests through Vercel serverless functions, bypassing Hugging Face Space firewall drop timeouts.

### 5. 🧠 Real-Time Active Learning & RAG Memory
- Real Arun's answers (from website Admin Reply Bar or Telegram swipe replies) are automatically saved to `data/raw/unknown_questions.json` and re-ingested into ChromaDB in real time.
