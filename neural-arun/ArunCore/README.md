---
title: ArunCore AI Assistant & Multi-Tenant Enterprise Engine
emoji: 🧠
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# 🧠 ArunCore — AI Systems Architect & Multi-Tenant Enterprise Engine

**ArunCore** is a production-grade, stateful, agentic portfolio and multi-tenant AI Assistant platform built for **Arun Yadav** (AI Systems Architect specializing in Healthcare & Education).

It features a **100% Data-Driven Multi-Tenant Enterprise JSON Engine** that can instantly spin up custom 24/7 AI Course Advisors and Sales Representatives for any tutor, instructor, or consultant (e.g. Ed Donner) simply by passing a query parameter (`?tutor=ed_donner`) backed by a single 238-key JSON schema.

---

## 🌟 Key System Features

1. **🤖 Multi-Tenant Enterprise JSON Engine (`?tutor=<tutor_id>`)**:
   - Dynamically loads tutor profiles, real course catalogs, bios, social links, FAQs, and custom system prompts from `data/<tutor_id>_enterprise_dictionary.json`.
   - **Zero Code Changes Needed**: To onboard a new tutor or client, duplicate `demos/general.json`, fill their bio/courses/colors, and open `?tutor=<new_client_id>`.

2. **🎨 Dynamic CSS Brand Theme System**:
   - Reads `theme_design_system` from the active JSON file and injects custom CSS variables (`--accent-green`, `--accent-green-hover`, `--border-accent`, `--bg-accent-soft`).
   - Automatically adapts the entire UI (buttons, active tabs, badges, quick questions, sidebar status dots) to the tutor's brand personality.
   - Defaults seamlessly to Arun Yadav's original sacred **Emerald Green (`#10b981`)** portfolio when no parameter is provided.

3. **🎓 Flagship Ed Donner Integration Demo (`?tutor=ed_donner`)**:
   - Complete real-world course catalog covering Ed's flagship tracks on Udemy (*AI Engineer Core Track*, *Agentic Track with MCP*, *Production MLOps Track*, *AI Builder*, *AI Coder*, *AI Leadership*).
   - Custom Deep Teal (`#0d9488`) brand theme, local high-res avatar, and clean SVG social symbols (`🎓`, `💼`, `𝕏`, `🌐`).

4. **⚡ 100% Automated Telegram Alerts (Zero LLM Dependency)**:
   - Automatically triggers instant notifications to the instructor's Telegram Alert Bot for visitor messages.
   - Includes: User Question, AI Response, Session ID, and a **1-Click Magic Join Link**.

5. **👨‍💻 1-Click Magic Link 3-Way Real Human Takeover**:
   - Tapping the 1-click link in Telegram opens the website in **Admin Mode** on any device.
   - Unlocks a dedicated input box for the real human instructor to chat live alongside the AI in a **3-Way Conversation Room**.

6. **🧠 AI Agent Onboarding Guide & SOP (`demos/TUTOR_ONBOARDING_GUIDE.md`)**:
   - A phase-by-phase protocol for AI Coding Agents and developers to research and populate new tutor JSON files with strict **Zero-Hallucination Guardrails**.

---

## 📁 Directory Structure & Key Files

```
aruncore/
├── core/
│   ├── agent.py               # Dynamic Tutor LLM agent loader & prompt builder
│   └── api.py                 # FastAPI backend server with /chat & /api/config endpoints
├── data/
│   ├── arun_enterprise_dictionary.json     # Arun Yadav master JSON schema
│   └── ed_donner_enterprise_dictionary.json # Ed Donner lead JSON schema
├── demos/
│   ├── general.json           # Blank master JSON schema template
│   ├── TUTOR_ONBOARDING_GUIDE.md # AI Agent Onboarding Protocol SOP
│   └── ed_donner_enterprise_dictionary.json # Gold standard reference example
├── frontend/
│   ├── app/page.tsx           # Main Next.js page with URL tutor search param fetch
│   ├── components/            # Header, Sidebar, ChatPanel, ProjectsView, ManifestoView, HandoffModal
│   └── public/                # Local avatars (ed_donner.png, profile_photo.png)
└── PRODUCTION_CLIENT_ONBOARDING_PLAYBOOK.md # Production deployment playbook for $300+ clients
```

---

## 🚀 Quick Start & Local Execution

### 1. Backend Server (FastAPI on Port 8000)
```bash
source .venv/bin/activate
python3 -m uvicorn core.api:app --reload --port 8000
```

### 2. Frontend Dev Server (Next.js on Port 3000)
```bash
cd frontend
npm run dev
```

### 3. Test URLs
- **Arun Yadav Default Portfolio**: [http://localhost:3000](http://localhost:3000)
- **Ed Donner AI Course Advisor**: [http://localhost:3000/?tutor=ed_donner](http://localhost:3000/?tutor=ed_donner)
