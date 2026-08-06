---
title: MediFlow AI Backend
emoji: 🏥
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# MediFlow AI - Backend

API phân tích hồ sơ bệnh án (FastAPI + Claude). Chạy trên Hugging Face Spaces (Docker).

- Endpoint kiểm tra: `/health`
- Phân tích PDF: `POST /analyze`
- Chatbot: `POST /chat`

Khóa API đặt ở Settings > Variables and secrets > Secrets, tên `ANTHROPIC_API_KEY`.
