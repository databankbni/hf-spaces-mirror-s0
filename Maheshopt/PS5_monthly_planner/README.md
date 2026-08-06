---
title: PS5 Monthly Planner
emoji: 🎮
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: "4.0.0"
python_version: "3.10"
app_file: PS5MonthlyPlanner.py
pinned: false
---

# PS5 Monthly Planner

This repository contains a Gradio-based PS5 Monthly Game Planner that scrapes release data from PS Index, allows selection of a game, and generates a monthly playtime planner. The app is implemented in `PS5MonthlyPlanner.py`.

## Quick start (local)

1. Create and activate a Python environment (recommended Python 3.10+):

```bash
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the app locally:

```bash
python PS5MonthlyPlanner.py
```

Open the local URL printed in the console (e.g. http://127.0.0.1:7860) or the public `gradio` share link if provided.

## Files of interest

- `PS5MonthlyPlanner.py` — main app and scraper
- `planner_memory.json` — saved planner history (ignored in git)
- `PS5MonthlyPlanner_report.html` — generated technical report

## Notes

- The app scrapes `https://www.psindex.co.uk/` and may be impacted by site structure changes or rate limiting.
- To publish to Hugging Face Spaces, follow the deploy steps in HF_DEPLOY.md.
