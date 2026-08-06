---
title: tune_research
app_file: app.py
sdk: gradio
sdk_version: 5.49.1
---

# Deep Research

Enter a topic, answer 3 quick clarifying questions, and get a fully researched
markdown report delivered by email or Pushover.

## Required Space secrets

- `OPENAI_API_KEY`
- `SENDGRID_API_KEY` (if `SEND_EMAIL=true`)
- `USER_EMAIL` (verified sender/recipient for email)
- `PUSHOVER_USER_KEY`, `PUSHOVER_API_TOKEN` (if `SEND_EMAIL=false`)
- `SEND_EMAIL` (`true` to email the report, `false` to Pushover it — defaults to `false`)
- `MODEL` (optional, defaults to `gpt-4o-mini`)
