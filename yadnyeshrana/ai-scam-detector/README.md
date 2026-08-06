---
title: AI Scam Detector
emoji: 🛡️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 3000
pinned: false
---

# AI Scam Detector WhatsApp Bot & Landing Page

A privacy-first, zero-cost AI Scam Detector WhatsApp bot and landing page for Indian users. Deployed on Hugging Face Spaces.

## Architecture
* **Frontend:** Interactive scan widget on landing page (Express + HTML5/CSS3)
* **Backend:** Express.js server
* **WhatsApp client:** Self-hosted client using `whatsapp-web.js` + Puppeteer
* **Database:** Firebase Realtime Database
* **AI Engine:** Gemini 2.5 Flash API
