# DHAAL — 15-minute deploy guide (Gate G0)

Three free accounts, zero cost. Do these in order. Every step is copy-paste.

## 1. GitHub (5 min)

1. github.com → New repository → name `dhaal` → **Private** → Create (no README).
2. On your machine, unzip `dhaal_day1.zip`, then:
   ```bash
   cd dhaal
   git init -b main
   git add -A && git commit -m "Day 1: engine + corpus 103 + frontend"
   git remote add origin https://github.com/<YOUR_USERNAME>/dhaal.git
   git push -u origin main
   ```
   (If Claude has a repo PAT, Claude pushes instead — just share the repo URL.)

## 2. Backend on Hugging Face Spaces (5 min)

1. huggingface.co → sign up (free) → New Space.
2. Name: `dhaal-api` · SDK: **Docker** · visibility: Public · CPU basic (free).
3. Upload these from the repo (Files tab → Add file → Upload):
   `Dockerfile`, the whole `backend/` folder, `frontend/demo.html`, `data/samples.jsonl`.
   (Or connect the Space to the GitHub repo under Settings.)
4. **Space secrets** (Settings → Variables and secrets → New secret) — the engine reads these at runtime:
   `GROQ_API_KEY`, `GEMINI_API_KEY` (LLM layer), and optionally
   `GOOGLE_SAFE_BROWSING_KEY`, `ABUSECH_AUTH_KEY` (Forensic Agent live feeds).
   All optional — the engine degrades gracefully without any of them.
5. Wait for build → your API is live at `https://<username>-dhaal-api.hf.space`.
6. **Smoke test:** open `https://<username>-dhaal-api.hf.space/health` →
   `{"status":"ok","llm_configured":true,"forensic_feeds":{...}}`.

## 3. Frontend on Vercel (5 min)

1. vercel.com → Continue with GitHub → Import the `dhaal` repo.
2. Root Directory: **frontend** (click Edit next to the repo root).
3. Environment variable: `NEXT_PUBLIC_API_URL` = `https://<username>-dhaal-api.hf.space`.
4. Deploy → live at `https://dhaal-<something>.vercel.app`.
5. **Smoke test:** open the URL on your phone → tap "FedEx digital arrest" chip → verdict card appears.

## 4. Keep-warm (2 min)

GitHub repo → Settings → Secrets and variables → Actions → **Variables** tab:
- `API_URL` = the HF Space URL
- `FRONTEND_URL` = the Vercel URL
Actions tab → enable workflows. The `keep-warm` cron now pings every 10 min.

## Gate G0 checklist (sign in tracker)

- [ ] `GET /health` returns ok on HF Space
- [ ] Frontend live on Vercel, scan works end-to-end on a phone
- [ ] Keep-warm workflow green in Actions tab
- [ ] `.env` values set ONLY in dashboards, never committed

## API keys (paste into the chat with Claude when ready)

| Key | Where to get it | Needed for |
|---|---|---|
| GROQ_API_KEY | console.groq.com → API Keys | Day 2 LLM layer |
| GEMINI_API_KEY | aistudio.google.com → Get API key | Day 2 fallback + Day 6 vision |
| GOOGLE_SAFE_BROWSING_KEY | console.cloud.google.com → enable Safe Browsing API → Credentials | Day 3 Forensic Agent (optional) |
| ABUSECH_AUTH_KEY | auth.abuse.ch → free account | Day 3 Forensic Agent / URLhaus (optional) |
| SUPABASE_URL + ANON_KEY | supabase.com → New project | Day 9 report store |
