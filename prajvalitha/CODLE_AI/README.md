---
title: CODLE AI
emoji: 🤖
colorFrom: purple
colorTo: blue
sdk: gradio
sdk_version: "5.35.0"
python_version: "3.11"
app_file: app.py
pinned: false
---

# 🤖 Codle AI

> **AI-Powered Coding Mentor & Polyglot Code Translator**

...
# 🤖 Codle AI Platform

A premium AI developer platform built with Python + Gradio. Explain, translate, visualize, and analyze code with a polished dark UI.

## Features

| Tab | Feature |
|-----|---------|
| 🔍 Explain | AI code explanation with bug detection, complexity analysis, ELI5 mode |
| 🔄 Translate | AI code translator across 9 languages with split-view output |
| 📈 Complexity | Animated complexity dashboard with O() badges and growth curves |

## Setup

```powershell
# 1. Create a virtual environment (if not already created)
python -m venv venv

# 2. Install dependencies in the virtual environment
.\venv\Scripts\pip install -r requirements.txt

# 3. Configure your HF token
# Edit .env and replace the placeholder:
#   HF_TOKEN=hf_your_token_here

# 4. Run the app
.\venv\Scripts\python.exe app.py
```

## Project Structure

```
code_explainer/
├── app.py              # Main Gradio application
├── prompts.py          # All AI prompt builders
├── utils.py            # Inference engine (secure, token-safe)
├── .env                # Your HF_TOKEN (never commit this)
├── .gitignore
├── requirements.txt
├── assets/
│   ├── logo.png
│   ├── styles.css      # Full premium dark theme
│   └── codle.js        # Particles, flow viz, chart, toasts, shortcuts
└── README.md
```

## Security

- `HF_TOKEN` is loaded only from the environment/`.env` file
- Never accepted from UI inputs or passed through Gradio state
- Never logged, printed, or returned to the frontend
- App aborts at startup if token is missing

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Enter` | Analyze code |
| `Ctrl+K` | Clear editor |
| `Ctrl+S` | Download markdown report |
| `Ctrl+Shift+C` | Copy report to clipboard |
| `Ctrl+/` | Open command palette |
