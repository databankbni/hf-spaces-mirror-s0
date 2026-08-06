---
title: Spotify Review Discovery Engine
emoji: 🎵
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# Spotify Review Discovery Engine

AI-powered RAG system analyzing 2,054 real Spotify user reviews to surface music discovery insights.

## What it does

Ask any question about Spotify user frustrations and get cited evidence-backed answers from real reviews.

## Example questions

- Why do users struggle to discover new music?
- What are the most common frustrations with recommendations?
- Which user segments experience discovery challenges?

## Tech Stack

- Backend: FastAPI, ChromaDB, BGE-small embeddings, Groq/Llama 3.3
- Frontend: Next.js 14, Tailwind CSS
- Data: 2,054 real reviews across 6 sources
