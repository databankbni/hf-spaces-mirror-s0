---
title: careTalk
tags:
  - healthcare
  - ai
  - bookkeeping
  - demo
emoji: 🏥
colorFrom: blue
colorTo: indigo
sdk: static
app_file: index.html
pinned: true
license: mit
short_description: AI-assisted voice documentation for care teams
---

# careTalk

**careTalk** is a **rules-led, AI-assisted care-documentation prototype** for UK adult social care. It learns your home’s **custom care training and documentation**, then turns **spoken observations** into **structured draft notes for staff review and approval**. Live **webhooks** let supervisors receive and view on-site information as draft records are created.

> **Demo to collect feedback.**

Support workers talk (or type) to get safety reminders, guided documentation questions, and agency-ready **draft** reports — with manager tools to approve users, review reports, and teach careTalk home-specific knowledge. Conversational replies use a rules-led dialogue engine, with an optional local Ollama model when available.

> Follow your home’s policy, escalate to the nurse in charge, and call **999** in an emergency.

---

## Live demo

**Version:** 1.1.31 — *Backfill Mary Nsaidoo-Storph + William FormSubmit notes*

There are **two** Hugging Face Spaces (same static build). The first attempt (`careTalk`) briefly used a HF build step that needs paid credits and stuck on **CONFIG_ERROR**; `careTalk-demo` is the clean prebuilt Space. From **v1.1.9** both host the identical release (current: **v1.1.31**).

| Space | Role | Links |
|---|---|---|
| **careTalk-demo** (primary) | Landing + app | [Space](https://huggingface.co/spaces/0001AMA/careTalk-demo) · [site](https://0001ama-caretalk-demo.static.hf.space/) · [app](https://0001ama-caretalk-demo.static.hf.space/app.html) |
| **careTalk** (mirror) | Same build | [Space](https://huggingface.co/spaces/0001AMA/careTalk) · [site](https://0001ama-caretalk.static.hf.space/) · [app](https://0001ama-caretalk.static.hf.space/app.html) |

Use **Chrome** or **Edge** for microphone / speech recognition. Allow mic when prompted. Prefer the **direct app URL** if the Space iframe blocks the mic. Data stays **on the device** (browser `localStorage`) unless you configure agency email/webhook forwarding.

### Shared feedback ticker (v1.1.31)

FormSubmit still emails every submission to the careTalk inbox. New submissions are also published to a **shared public feed**, so the landing ticker shows the same notes for every visitor (name initials, workplace, message) — not only the browser that submitted. Older emails can be backfilled into `public/feedback-feed.json`.

### Feedback ticker (v1.1.20)

A slow horizontal preview sits just under the landing hero. It shows **real feedback form submissions** saved on that site (browser `localStorage` for the HF / local origin): message preview, workplace, and name initials. No sample cards. The strip stays hidden until at least one submission exists on that device/origin.

### Demo banner (v1.1.19)

Landing and app banner text is now simply: **Demo to collect feedback.**

### Positioning & demo trust (v1.1.18)

Landing and app now frame careTalk as **AI-assisted voice documentation for care teams** (not “book-keeping”). The public prototype shows a permanent **Demonstration only** banner, one-tap **Try as support worker** / **Try as manager** fictional roles, and labels generated notes as **drafts for staff review**.

### Positioning (v1.1.17)

Landing copy emphasises AI-assisted book-keeping for health assistants and admins, plus custom training, speech-to-notes, and live supervisor webhooks.

### Landing hero videos (v1.1.16)

The home page hero rotates muted background clips from [Pexels 4053216](https://www.pexels.com/download/video/4053216/) and [Pexels 5941023](https://www.pexels.com/download/video/5941023/) (CDN first, local fallback). A still poster is used for reduced-motion and before the first clip is ready.

### Theme (v1.1.14)

Use the sun/moon icon (landing header, app corner, and admin) to switch between light and dark. Preference is saved in the browser.

### Feedback (v1.1.13)

On the [project landing page](https://0001ama-caretalk-demo.static.hf.space/#feedback), care assistants and supervisors can share how careTalk might help on shift or in oversight. **Send feedback** posts through a mail-forwarding service straight to **pd3rvr@icloud.com** (no device mail app). The first live submission may require a one-time FormSubmit confirmation email to that inbox.

### Subscribe for updates (v1.1.9)

Visitors can join an updates list on the landing page ([#subscribe](https://0001ama-caretalk-demo.static.hf.space/#subscribe)). Addresses are stored in browser `localStorage` on that device. A discreet lock icon in the footer opens a private updates admin screen (`admin.html`) to review / export the list — credentials are not published here.

**Default app admin (first install / device reset):**

| Field | Value |
|---|---|
| Email | `admin@don.local` |
| Password / train PIN | `2473` |

---

## What careTalk does

### Speech → documentation
- Capture **informal speech** from carers on the floor (or typed notes)
- Translate it into **relevant documentation** suited to care-record keeping
- Learn **custom training** and home-specific guidance so wording and prompts match how your service works

### Live supervisor visibility
- Configure agency **email / webhook** forwarding
- Supervisors can receive and view **near real-time** information as carers create records on site

### For support workers — **Talk to careTalk**
- Say **“Hi careTalk”** (or legacy **“Hi Don”**) to wake the assistant
- Ask for help or describe a situation: *“careTalk, Meggie just fell…”*
- Get **do / don’t** safe-practice reminders with optional visual guides
- Say **okay** when ready — careTalk asks **one documentation question at a time**, reads each answer back, and confirms before continuing
- Say **make a report** to start a **live report** that updates on your profile as you speak
- Pin quick notes for managers (“put on file”)

### For managers / nurses / admins
- **Give careTalk more knowledge** — train from the web, a single URL, or typed do/don’t guidance (PIN-protected)
- **Reports** — view support-worker reports grouped by category (falls, safeguarding, medication, etc.), training gaps, registrations, and user profiles
- Approve admin registrations; carers verify email then auto-approve as support workers

### Optional local LLM
- If [Ollama](https://ollama.com) is running locally with a chat model (default `qwen2.5:7b`), conversational replies can use the LLM; otherwise the rule-based dialogue brain is used

---

## Features at a glance

| Area | Details |
|---|---|
| Speech → notes | Informal carer speech translated into relevant documentation for record-keeping |
| Custom training | Learns home-specific care training and guidance (web, URL, or typed knowledge) |
| Live webhooks | Supervisors can receive near real-time updates as carers create records on site |
| Voice | UK English speech recognition + TTS; turn-taking so careTalk does not talk over you |
| Documentation | Scenario playbooks (fall, dysphagia, distress, medication, skin, wellbeing, general) |
| Reports | Pinned / live / agency outbox reports from carers **and** admins on the same device |
| Categories | Falls, safeguarding/abuse, swallowing, behaviour & distress, medication, skin, wellbeing, general |
| Training gaps | Unresolved incidents when advice is requested on an untrained topic; optional agency notify |
| PWA | Installable progressive web app (HTTPS required for mic + service worker) |
| Mobile shells | Capacitor projects for Android / iOS (`android/`, `ios/`) |

---

## Quick start (local)

**Requirements:** Node.js 20+, modern Chromium browser.

```bash
npm install
npm run dev
```

Open **http://localhost:5173**

```bash
npm run build      # production bundle → dist/
npm run preview    # http://localhost:4173
```

### Optional Ollama (local LLM)

```bash
ollama pull qwen2.5:7b
# Ollama default: http://127.0.0.1:11434
```

---

## Default accounts & reset

- Fresh install creates **careTalk Admin** at `admin@don.local` / `2473`
- Change the train PIN after first unlock under **Give careTalk more knowledge**
- Localhost only: open `http://localhost:5173/?reset=1` to wipe device data and restore the default admin
- Admins can also use **Reports → Users → Reset all users to default admin**

---

## Modes

1. **Talk to careTalk** — carer help, voice notes, live/agency reports  
2. **Give careTalk more knowledge** — admin knowledge studio (registration role + PIN)  
3. **Reports** — outbox, gaps, regs, users (admin)

---

## Architecture (web)

```
index.html          UI shells (gate, auth, talk, train, reports)
src/main.js         App wiring, speech, Q&A flow, admin UI
src/dialogue.js     Rule-based nurse dialogue / slot filling
src/flows.js        Scenarios, wake word, session, report text
src/llm.js          Optional Ollama chat client
src/userReports.js  Live/pinned reports + presence
src/reportIndex.js  Unified carer+admin report list
src/reportCategories.js  Category grouping
src/users.js        Registration, verify, roles
src/store.js        localStorage (knowledge, agency, PIN, outbox)
src/knowledge.js    Built-in UK care practice themes
```

**Storage:** everything is **device-local** (`localStorage` / `sessionStorage`). There is no cloud care-record backend. Clearing site data clears users and reports on that browser.

---

## Scripts

| Script | Purpose |
|---|---|
| `npm run dev` | Local Vite server |
| `npm run build` | Production PWA → `dist/` |
| `npm run preview` | Preview production build |
| `npm run icons` | Regenerate icons |
| `npm run mobile:sync` | Build + Capacitor sync |
| `npm run android:open` / `ios:open` | Open native IDE |

See [DEPLOY.md](./DEPLOY.md) for website / Play Store / App Store notes.

---

## Deploy

### Hugging Face Spaces

Both Spaces are **static** and serve a pre-built Vite `dist/` (no HF build credits / no `app_build_command`).

1. `npm run build`
2. Publish `dist/` + a short Space `README.md` (YAML front matter only: `sdk: static`) to:
   - `0001AMA/careTalk-demo` (primary)
   - `0001AMA/careTalk` (mirror)

Do **not** set `app_build_command` — that is what left `careTalk` on CONFIG_ERROR previously.

### Other static hosts

Deploy the `dist/` folder to Netlify, Vercel, Cloudflare Pages, S3, etc. HTTPS is required for microphone access.

### GitHub

Source: https://github.com/2000pd3rvr/careTalk

---

## Privacy & safety

- Voice and notes are processed in the browser (and optionally Ollama on localhost)
- Agency forward may open a mail client or POST to a webhook you configure
- Do not enter confidential information on shared devices without local policy approval
- careTalk supports documentation and reminders — it does **not** replace clinical assessment

---

## Licence

MIT (unless your organisation requires a different licence for distribution).

<!-- dailygit-space-order running-top 2026-08-06T02:46Z -->

---

Author: [@0001AMA](https://huggingface.co/0001AMA) · [GitHub](https://github.com/2000pd3rvr)
