---
project_name: Notes_maker_via_youtube_or_subs
github_url: https://github.com/neural-arun/Notes_maker_via_youtube_or_subs
language: Python
stars: 0
topics: 
updated_at: 2026-05-04T22:29:02Z
---

# Notes_maker_via_youtube_or_subs

> **GitHub Repository:** [https://github.com/neural-arun/Notes_maker_via_youtube_or_subs](https://github.com/neural-arun/Notes_maker_via_youtube_or_subs)  
> **Primary Language:** Python | **Stars:** 0 | **Forks:** 0  
> **Description:** No description provided.

---

---
title: Lecture Notes Generator
emoji: 📚
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: 1.32.0
app_file: app.py
pinned: false
---

# 📚 Lecture Notes Generator

Convert long lecture subtitle files (`.srt` / `.vtt`) into clean, structured notes using the **DeepSeek AI API** — chunk by chunk.

## Features

- 🔄 **Resumable processing** — if it stops midway, just hit Resume
- 📦 **Configurable chunk size** — 5, 10, or 15 minutes per API call
- ✏️ **Custom prompt** — tailor notes for any subject (medicine, law, CS, etc.)
- 👁️ **Live preview** — see notes appear as each chunk finishes
- 🔁 **Auto-retry** — failed chunks are retried automatically
- 📥 **Export** as `.md` or `.txt`

## How to Use

1. Get a [DeepSeek API key](https://platform.deepseek.com/)
2. Upload your `.srt` or `.vtt` subtitle file
3. Configure settings in the sidebar
4. Click **Start Generating Notes**
5. Download when done

## Running Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploying to Hugging Face Spaces

1. Create a new Space on [huggingface.co/spaces](https://huggingface.co/spaces)
2. Choose **Streamlit** as the SDK
3. Upload `app.py`, `requirements.txt`, and this `README.md`
4. The Space will build and launch automatically

> ⚠️ Your API key is **never stored** — it only lives in the browser session.
