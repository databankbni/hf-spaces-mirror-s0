---
title: Godena
emoji: 🌐
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# Godena

**The open agent network — a search engine for AI agents and real-world services.** Type what you need, get the top matches ranked by reputation, with a real link.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Live search](https://img.shields.io/badge/try%20it-sammyghe.github.io%2FGodena-1d9e75.svg)](https://sammyghe.github.io/Godena/)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-1d9e75.svg)](CONTRIBUTING.md)

### ▶ Try it now — no app, no login, no number
- **Web:** **[sammyghe.github.io/Godena](https://sammyghe.github.io/Godena/)** ← live, works today
- **API:** `GET` [sammygh-godena.hf.space/api/search?q=lawyer+kampala](https://sammygh-godena.hf.space/api/search?q=lawyer+kampala)

### Channels
- **Web + API** — live now.
- **Telegram** — [@GodenaBot](https://t.me/GodenaBot) *(messaging channel; needs no phone number — set up via @BotFather)*.
- **WhatsApp** — the scale channel, activated with first funding (needs a verified business number).
- **Vision:** [docs/VISION.md](docs/VISION.md) · **Roadmap:** [docs/ROADMAP.md](docs/ROADMAP.md) · **Why not just Supabase:** [docs/DATABASE.md](docs/DATABASE.md)

---

## What it is

Most of the world's commerce still runs on one question: *"do you know a guy?"*

Godena answers it. You type what you need — a lawyer, a mechanic, a flight, a sourcing agent in China, an AI coding tool — and Godena returns the best matches, ranked by reputation, with a real link. Then it steps back. Your conversation, your business. Godena just made the introduction.

It's messaging-native by design — no app to install, no login, no data bundle to burn — so it meets the next billion people where they already are. It runs on the web today; Telegram and WhatsApp are the same engine over chat.

```
lawyer kampala      →  Uganda Law Society + real WhatsApp contact
flights nairobi     →  Kenya Airways + Ethiopian Airlines + KLM
send money africa   →  Wise + Chipper Cash + WorldRemit
ai coding           →  Claude + Cursor + Groq
china sourcing      →  Alibaba + Yiwu sourcing agents
```

## Why this is a network, not an app

Software is becoming free — anyone can clone this repo and run it tonight. So the code is not the moat, and we do not pretend it is. We open-sourced it on purpose.

The moat is the **network**: the registry of agents, the reputation earned through real jobs, and the demand signal of what people actually search for. Every search, every rating, every claimed business makes the network more useful for the next person — and that value compounds in one place even when the code is everywhere. Open networks tend to win, because the value lives in the graph, not the binary.

## How it works

```
User texts Godena
       ↓
Search engine matches skill + location
       ↓
Reputation engine ranks results
       ↓
Top 3 returned with real contact links
       ↓
Godena steps back — the conversation is yours
```

No middleman. No commission. No data sold.

## Architecture

- **Bot:** FastAPI on Hugging Face Spaces (free tier)
- **Database:** Supabase (Postgres) — hundreds of thousands of agents on the free tier
- **WhatsApp:** Green API (inbound webhook)
- **Telegram:** Webhook mode (no polling, works on free hosting)
- **Search:** skill-first filtering + reputation ranking
- **Reputation:** an evidence-weighted score combining identity, performance, peer trust, and external signals

All secrets live in environment variables / Hugging Face Space settings — never in the code. See [SECURITY.md](SECURITY.md).

## API

Godena is open infrastructure. Any developer, platform, or AI agent can register and be discovered — free, forever.

Register an agent:

```bash
curl -X POST https://sammygh-godena.hf.space/api/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My_Service_Name",
    "skill": "legal",
    "location": "nairobi",
    "country": "kenya",
    "whatsapp": "https://wa.me/254712345678"
  }'
```

Search:

```
GET /api/search?q=lawyer+kampala
```

See the running service root (`/`) for the full list of endpoints (register, claim, rate, endorse, complete, gaps).

## Run your own / fork a city

Clone it. Change a few lines. Deploy your own Godena for your community.

```bash
git clone https://github.com/sammyghe/Godena
cd Godena
# Add your own secrets in Hugging Face Space settings (never commit them)
# Deploy to Hugging Face Spaces (free)
```

A Lagos mechanic network. An SF African-business directory. A Nairobi legal-referral line. Same code, different registries. The networks can stay separate or federate — your call. See [CONTRIBUTING.md](CONTRIBUTING.md) to add agents or improve the core.

## Roadmap

We are early — Stage 1 of 5 (a working directory). The path to a real reputation network and beyond is in [docs/ROADMAP.md](docs/ROADMAP.md). The contributions that move us fastest are **real, verified agents** — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Built by

**Samuel Gedamua** — Founder.
**Amanuel Asmerom** — Co-Founder.

First agent: Emmas_cars Kampala — March 11 2026.
Co-built with Claude (Anthropic).

## License

[MIT](LICENSE) — free forever. The network grows when you add to it.
