# 📖 Master Operations Guide — ArunCore Architecture

This master guide covers system design, operational maintenance, and live communication flows for **ArunCore**.

---

## 🏛️ System Architecture Overview

```
[Web Visitor on Vercel] ◄─────────────── SSE / NDJSON Streaming Stream ────────────────► [FastAPI Backend]
         │                                                                                      │
         ▼                                                                                      ▼
[1-Click Magic Link Admin Mode]                                                     [ChromaDB + Cohere Reranker]
   (Arun joins 3-Way Live Chat)                                                                 │
         ▲                                                                                      ▼
         │                                                                          [Vercel Egress Relay API]
         └───────────────────────── [Telegram Alert Bot] ◄──────────────────────────────────────┘
```

---

## 🔑 Operational Components

### 1. 100% Automated Telegram Chat Alerts
- Backend triggers `queue_automated_chat_alert()` on every user interaction.
- Delivers complete transcript snippet and 1-Click Join Link to Arun's phone.

### 2. 1-Click Magic Link 3-Way Real Human Takeover
- URL format: `https://aruncore.vercel.app/?session_id=<SESSION_ID>&admin_token=<TOKEN>`
- Unlocks Admin Reply Bar on `frontend/components/ChatPanel.tsx`.
- Real Arun messages broadcast with `👨‍💻 Arun Yadav [VERIFIED HUMAN] 🟢` badge.
- AI Twin remains active for 3-party group conversation.

### 3. Vercel Serverless Egress Relay
- Endpoint: `frontend/app/api/telegram/route.ts`
- Routes outbound Telegram POST requests through Vercel serverless infrastructure to prevent Hugging Face Space firewall drop timeouts.

### 4. Active Learning Memory Loop
- Endpoint: `core/bot.py`
- Parses replies to Telegram alerts, writes to `data/raw/unknown_questions.json`, and triggers `core/ingest.py`.

### 5. Automated CI/CD Deployment
- Command: `git push origin main`
- Updates GitHub, Vercel (`aruncore.vercel.app`), and Hugging Face (`neural-arun-aruncore.hf.space`).
