---
title: AI Agent Content Planner
emoji: 🤖
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# AI Agent Content Planner

Backend FastAPI yang membuat brief konten multi-platform (Instagram, LinkedIn, dll)
menggunakan Google Gemini API. Dipanggil oleh dashboard WordPress.

## Endpoint

- `GET /` — cek backend hidup
- `POST /buat-brief` — kirim `{ "topik", "link", "platform": [...] }`, balikin brief per platform
