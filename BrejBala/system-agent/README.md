---
title: The System — Portfolio Agent
emoji: ⚔️
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# The System — Portfolio Agent

Grounded Q&A backend for [Brejesh Balakrishnan's status-window portfolio](https://brej-29.github.io).
A deliberately small FastAPI proxy with guardrails — not a platform.

```
Visitor browser ──POST /chat──▶ this Space (FastAPI) ──▶ Groq llama-3.1-8b-instant
   (no key)                     keys ONLY in Space          └▶ Gemini 2.5-flash-lite (fallback)
                                secrets, read from env
```

## API

| Route | Method | Contract |
|---|---|---|
| `/chat` | POST | `{"messages":[{"role":"user"\|"assistant","content":"..."}]}` — chronological, starts & ends with `user`, ≤12 messages, ≤500 chars each. Success: `200 {"reply":"..."}`. Failure: `{"error":"..."}` with 4xx/5xx. |
| `/health` | GET | `{"status":"ok","provider":"groq\|gemini\|none"}` |

## Security model

- **No secrets in code or git — ever.** `GROQ_API_KEY` / `GEMINI_API_KEY` are read from the
  environment only (HF Space **secrets** in production, `.env` locally, which is gitignored).
  If a key ever leaks into a commit, rotate it at the provider immediately.
- **Server-side system prompt** is the single source of truth. Client messages are untrusted:
  strict Pydantic schema (role whitelist, message/char caps, `extra="forbid"`), otherwise 422.
- **Prompt-injection defenses:** visitor text is NFKC-normalized, stripped of control /
  zero-width / bidi-override characters, cleansed of delimiter forgery, and wrapped in
  `<visitor_query>` tags the model is instructed to treat as data.
- **CORS allowlist only** — exact origins via `ALLOWED_ORIGINS`, `POST`+`OPTIONS`, no `*`.
- **Rate limiting:** 20 requests / 5 min per IP (first hop of `X-Forwarded-For`) + a global
  daily cap (default 1,000, override with `DAILY_CAP`). *Known limitation:* in-memory and
  single-process — resets on restart, not shared across workers. Accepted tradeoff for a
  free single-container Space.
- **Generation caps:** `max_tokens=400`, `temperature=0.3`, 20 s timeout per provider, one
  fallback attempt, then `503 {"error":"SYSTEM LINK UNSTABLE"}`. Replies truncated server-side.
- **Surface reduction:** interactive docs/OpenAPI disabled; 16 KB body cap (413); uniform
  generic error bodies; `nosniff` / `no-store` / `no-referrer` headers.
- **Privacy-respecting logging:** timestamps, status codes, latency, token counts —
  never message content.

## Local development (Windows / PowerShell)

```powershell
cd D:\Project\portfolio-system-agent
uv sync                          # creates .venv from uv.lock
Copy-Item .env.example .env      # then fill in your keys
uv run pytest                    # all guard + endpoint tests, no network needed

# run the server (loads .env into the process first)
Get-Content .env | ForEach-Object { if ($_ -match '^(\w+)=(.+)$') { Set-Item "env:$($Matches[1])" $Matches[2] } }
uv run uvicorn app.main:app --port 7860
```

Verification calls:

```powershell
# health
Invoke-RestMethod http://localhost:7860/health

# happy path
Invoke-RestMethod http://localhost:7860/chat -Method Post -ContentType 'application/json' `
  -Body '{"messages":[{"role":"user","content":"What certifications does he hold?"}]}'

# out-of-scope -> refusal phrasing, no fabrication
Invoke-RestMethod http://localhost:7860/chat -Method Post -ContentType 'application/json' `
  -Body '{"messages":[{"role":"user","content":"What is his salary expectation?"}]}'

# oversized payload -> 422
Invoke-RestMethod http://localhost:7860/chat -Method Post -ContentType 'application/json' `
  -Body ('{"messages":[{"role":"user","content":"' + ('x'*501) + '"}]}')
```

## Deploy to Hugging Face (Docker Space)

1. Create the Space: **huggingface.co → New Space → SDK: Docker → Blank**, name `system-agent`.
2. **Settings → Variables and secrets → New secret:** add `GROQ_API_KEY` and `GEMINI_API_KEY`
   (secrets, not variables). Optionally set `ALLOWED_ORIGINS` as a variable.
3. Push this repo to the Space git remote:
   ```powershell
   git remote add space https://huggingface.co/spaces/BrejBala/system-agent
   git push space main
   ```
4. Wait for the build, then check `https://brejbala-system-agent.hf.space/health`.

## Wire the portfolio

In the site's `index.html`, set:

```js
AGENT_ENDPOINT: "https://brejbala-system-agent.hf.space/chat",
```

commit, push. The chat header badge flips to `LINK: HF AGENT`.
