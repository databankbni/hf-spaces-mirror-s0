---
title: Golf MCP
emoji: 🏌️
colorFrom: green
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Golf Swing Coach — MCP Backend

Backend for the Golf Coach mobile app. Runs a FastMCP / Starlette server that exposes:

- `GET /health` — health check
- `POST /analyze` — swing analysis: Gemini vision (if `GEMINI_API_KEY` set) with automatic fallback to the free on-server MediaPipe Pose + rule engine
- `POST /chat`, `POST /drills`, `POST /pro_swing` — Coach Birdie coaching (RAG over golf tips + Claude)

Set `ANTHROPIC_API_KEY` as a Space secret to enable the chat / drills / pro-swing endpoints. Set `GEMINI_API_KEY` (free from [Google AI Studio](https://aistudio.google.com/apikey)) to upgrade swing analysis from the free pose+rules engine to full Gemini video analysis — `/analyze` works with neither key set, just at reduced quality.
