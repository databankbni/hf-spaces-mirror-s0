# 💻 Frontend Web Application (`/frontend/`)

This folder contains the **Next.js 16 (Turbopack) web application** for Arun's portfolio website and 3-Way Live Chat AI Assistant interface. Deployed on **Vercel** (`aruncore.vercel.app`).

---

## 📁 Directory Structure

```
frontend/
├── app/
│   ├── api/
│   │   └── telegram/
│   │       └── route.ts     # Vercel Serverless Relay Route (bypasses HF Space Telegram firewall blocks)
│   ├── globals.css         # Custom CSS tokens, glassmorphism theme, and animation utilities
│   ├── layout.tsx          # Root HTML layout, font configurations, and default light theme wrapper
│   └── page.tsx            # Main state container managing active tab, streaming chat, 3-way session polling, & admin mode
├── components/
│   ├── Header.tsx          # Top navigation bar, tab switcher (Assistant, Projects, About), social links, theme toggle
│   ├── ChatPanel.tsx       # 3-Way Chat panel, Admin Reply Bar, quick commands (/answer, /release), STT & HD TTS studio
│   ├── ManifestoView.tsx   # About page: principles, technical skills, engineering philosophy
│   ├── ProjectsView.tsx    # Filterable grid of 22+ projects with live GitHub API data auto-sync
│   └── HandoffModal.tsx    # Contact modal with quick links to WhatsApp, Email, Phone, & Telegram
├── lib/
│   └── types.ts            # TypeScript interfaces for Message (user, twin, human_arun), Project, & Chat API payloads
├── next.config.ts          # Serverless route deployment config for Vercel
└── package.json            # Frontend dependencies and build scripts
```

---

## 📁 Component Descriptions

### 1. `app/api/telegram/route.ts` — Vercel Serverless Relay
- Next.js serverless route that accepts Telegram `sendMessage` payloads and forwards them to `api.telegram.org`.
- Solves Hugging Face free space network firewall drop issues on Telegram API IP ranges.

### 2. `app/page.tsx` — Main Application & 3-Way Session Sync
- Detects `session_id` and `admin_token` URL parameters when opening 1-Click Telegram Magic Join Links.
- Verifies admin tokens with backend `/chat/verify-admin-token`.
- Automatically fetches and renders the full chat transcript from `GET /chat/history?session_id=...`.
- Runs a 1.5-second polling loop so both the web visitor and Real Arun see the exact same 3-way conversation history in real time.

### 3. `components/ChatPanel.tsx` — 3-Way Live Chat & Voice Studio
The core interactive view. Contains:
- **3-Party Message Cards**: Renders messages for Visitor (`user`), AI Assistant (`twin`), and Real Arun (`human_arun`) with a glowing green verified badge (`👨‍💻 Arun Yadav [VERIFIED HUMAN] 🟢`).
- **Admin Reply Bar**: Unlocks in Admin Mode allowing Real Arun to send messages, trigger AI answers (`/answer`), or hand back control (`/release`).
- **Speech-to-Text (STT)**: Microphone button (`[ 🎙️ ]`) with duplicate-free transcription.
- **Text-to-Speech (TTS)**: `[ 🔊 Listen (HD Voice) ]` for HD audio using OpenAI studio neural voice.

### 4. `components/ProjectsView.tsx` — Portfolio Projects Grid
- Searchable, filterable grid of 22+ engineering projects with live client-side auto-sync from `api.github.com/users/neural-arun/repos` sorted by `pushed_at` descending.

### 5. `components/ManifestoView.tsx` — About Page
- Renders Arun's engineering philosophy, operating principles (value & impact first), and technical skills breakdown.

### 6. `lib/types.ts` — TypeScript Definitions
- Strict TypeScript interfaces for `Message` supporting `sender: "user" | "twin" | "human_arun"`.

---

## 🚀 Running Locally

```bash
cd frontend
npm install
npm run dev       # Dev server at http://localhost:3000
npm run build     # Production build
```
