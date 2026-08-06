---
title: HDFC Banking Assistant
emoji: "🏦"
colorFrom: blue
colorTo: indigo
app_port: 7860
sdk: docker
pinned: false
---

# HDFC Banking Assistant (Docker)

This project runs as a Docker Space on Hugging Face and serves an HDFC-branded demo web app backed by Groq.

## Files

- BankingAgent.py
- hf_web.py
- Dockerfile

## Runtime Behavior

The app uses a LangChain-based RAG flow with semantic embeddings from `sentence-transformers/all-MiniLM-L6-v2`, in-memory vector retrieval over approved HDFC public URLs, and a direct Groq LLM fallback when retrieval returns no usable context.

## Local run

1. Set `GROQ_API_KEY` in your environment.
2. Run:

```bash
python hf_web.py
```

3. Open `http://localhost:7860`.

## Hugging Face Spaces (Docker)

1. Create a Space and choose **Docker** SDK.
2. Upload this repository (including `Dockerfile`).
3. Add a Space Secret named `GROQ_API_KEY`.
4. Deploy. Hugging Face builds the container and serves the HDFC demo assistant on port `7860`.