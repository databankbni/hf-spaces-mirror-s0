---
title: Nomos42 Political LLM Trading Floor
emoji: 🏛️
colorFrom: purple
colorTo: red
sdk: gradio
sdk_version: 5.23.0
app_file: app.py
python_version: "3.11"
pinned: true
---

# Nomos42 Political LLM Trading Floor

10 AI agents trade sector ETFs on daily political signals — every decision is a **real LLM API call**.

## What it does

Each agent receives:
- Daily political events (insider trades, Fed rules, executive orders) from 2026-03-12 to 2026-03-26
- 30-day sector trend baselines (avg excess_return, win_rate per sector)
- Agent-specific persona and system prompt

Each agent must decide: **long**, **short**, or **hold cash** on each event's sector ETF.
After all 14 days and ~1120 events, we rank agents by final bankroll.

**Leakage-safe:** agents never see `excess_return`, `y`, or `outcome` — only signal metadata.
**Resolution:** `pnl_pct = direction_sign × excess_return × 5.0` (leverage), capped at ±50%.

## Agents (10 real LLMs)

| Agent | Model | Provider | Persona |
|-------|-------|----------|---------|
| Qwen Quant 235B | Qwen 3 235B | Cerebras | Regulatory-delta quant |
| Qwen Arb 235B | Qwen 3 235B | Cerebras | Cross-sector arbitrage |
| Llama Contrarian | Llama 3.1 8B | Cerebras | Consensus-fade |
| Gemini Analytical | Gemini 3 Flash | Google | Fed/SEC stats-first |
| Gemini Tactical | Gemini 3 Flash | Google | Calendar/schedule |
| Mistral Large | Mistral Large | Mistral | Ensemble meta-allocator |
| Mistral Medium | Mistral Medium | Mistral | Portfolio diversification |
| Mistral Small | Mistral Small | Mistral | Cash when no conviction |
| Mistral Nemo | Mistral Nemo | Mistral | Exec-order momentum |
| Ministral 8B | Ministral 8B | Mistral | Game-theory sizing |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Experiment status, agent bankrolls, running state |
| `/api/run` | POST | Start/resume experiment (non-blocking) |
| `/api/stop` | POST | Graceful stop (finishes current day) |
| `/api/reset` | POST | Clear saved state, start fresh |
| `/api/mutate` | POST | Change agent params mid-experiment |
| `/api/logs` | GET | Per-agent decision log stream |
| `/api/day-decisions` | GET | Day-level allocation details |
| `/api/leaderboard` | GET | Current standings JSON |

## Architecture

- **TradingAgents** (arXiv 2412.20138): structured agent reasoning framework
- **Prediction Arena** (arXiv 2604.07355): 1-bet-per-agent competition validation
- **DMAD** (Diverse Multi-Agent Debate): structurally distinct reasoning via different system prompts

## Data

Political events schema: `{date, ticker, event_type, signal_strength, agency, title, signal_type, signal_sector, donor_info, macro}`
Top event types: `insider_trade` (961), `fed_rule` (149), `polymarket` (8), `exec_order` (2)
Top sectors: `private_prisons`, `healthcare`, `energy`, `finance`
