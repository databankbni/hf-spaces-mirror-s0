# 🛠️ ArunCore Master Operational Guide

This document contains full operational procedures for managing, updating, testing, and deploying **ArunCore**.

---

## 📋 Table of Contents
1. [Architecture Overview](#1-architecture-overview)
2. [100% Automated Telegram Alerts & 3-Way Live Takeover](#2-100-automated-telegram-alerts--3-way-live-takeover)
3. [Vercel Serverless Egress Relay](#3-vercel-serverless-egress-relay)
4. [Active Learning Loop (Telegram Reply)](#4-active-learning-loop-telegram-reply)
5. [Data Maintenance & Vector Ingestion](#5-data-maintenance--vector-ingestion)
6. [System Verification & Integration Testing](#6-system-verification--integration-testing)
7. [Automated CI/CD Deployment](#7-automated-cicd-deployment)

---

## 1. Architecture Overview

ArunCore consists of three main components:
- **Frontend UI (`frontend/`)**: Built with Next.js 16, React, Tailwind CSS. Deployed on **Vercel** (`aruncore.vercel.app`).
- **Backend Engine (`core/`)**: Built with FastAPI, LangChain, ChromaDB, Cohere V3 Reranker, and OpenAI `gpt-4.1-nano`. Deployed on **Hugging Face Spaces** (`neural-arun-aruncore.hf.space`).
- **Telegram Notification & Active Learning System**: Dual Telegram bot system for 100% automated alerts, full execution trace logging, active learning ingestion, and 1-Click Magic Link 3-Way Real Human Takeover.

---

## 2. 100% Automated Telegram Alerts & 3-Way Live Takeover

### How Automated Alerts Work:
- Every time a visitor sends a message on `aruncore.vercel.app`, the backend unconditionally queues an instant notification to `@ai_twin_alert_bot`.
- The notification contains:
  - 👤 **User Question**
  - 🤖 **AI Response**
  - 🔗 **1-Click Magic Join Link**: `https://aruncore.vercel.app/?session_id=...&admin_token=...`

### How 3-Way Real Human Takeover Works:
1. Click the **1-Click Magic Join Link** in your Telegram notification on your phone or laptop.
2. The website opens in **Admin Mode** with a green status banner: `🟢 LOGGED IN AS REAL ARUN YADAV — LIVE 3-WAY CHAT ROOM`.
3. Type a message in the bottom **Admin Reply Bar** and click **SEND AS REAL ARUN**.
4. Your message appears live on the visitor's screen in 3 seconds formatted as:
   `👨‍💻 Arun Yadav [VERIFIED HUMAN] 🟢`
5. The AI Twin continues answering visitor questions normally, while you can chime in alongside the AI in a 3-way conversation.

---

## 3. Vercel Serverless Egress Relay

- Free Hugging Face Spaces block outbound TCP port 443 connections to `api.telegram.org` IP ranges.
- To eliminate network timeouts (`_ssl.c:999: The handshake operation timed out`), all Telegram messages are routed through Vercel's serverless endpoint `/api/telegram` (`frontend/app/api/telegram/route.ts`).
- Hugging Face has unrestricted access to Vercel HTTPS endpoints, ensuring 100% reliable alert delivery.

---

## 4. Active Learning Loop (Telegram Reply)

When you receive a Telegram notification for an `UNKNOWN_QUESTION` or lead inquiry:
1. Reply directly to the Telegram message on your phone.
2. The bot handler (`core/bot.py`) extracts the question and saves your reply to `data/raw/unknown_questions.json`.
3. ChromaDB automatically re-ingests the updated knowledge store in the background.
4. Future user queries matching that question are answered using your exact verified words!

---

## 5. Data Maintenance & Vector Ingestion

To manually update knowledge base files or re-index ChromaDB:

```bash
# Activate virtual environment
source .venv/bin/activate

# Add new markdown files to data/raw/ or edit data/static/public_profile.md

# Re-run vector ingestion manually
python3 core/ingest.py
```

---

## 6. System Verification & Integration Testing

Run the automated 5-part integration test suite before pushing changes:

```bash
source .venv/bin/activate
python3 tests/test_system.py
```

The test suite verifies:
1. Knowledge Base RAG Search (Alias mapping & markdown chunk retrieval).
2. Live GitHub API Data Sync (`pushed_at` repository sorting).
3. Active Learning Loop (`unknown_questions.json` saving & ChromaDB re-indexing).
4. Telegram Alert Delivery Engine (Vercel Relay endpoint).
5. Agent Invocation & Dynamic Language Rules (Pure English enforcement).

---

## 7. Automated CI/CD Deployment

To deploy updates to GitHub, Vercel, and Hugging Face simultaneously:

```bash
git add .
git commit -m "feat: description of your changes"
git push origin main
```

- **GitHub**: Code pushed to `origin main`.
- **Vercel**: Next.js frontend rebuilds automatically via GitHub webhook.
- **Hugging Face**: Docker container rebuilds automatically via GitHub Actions workflow (`.github/workflows/deploy.yml`).
