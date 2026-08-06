---
title: Quest
emoji: 🎯
colorFrom: red
colorTo: gray
sdk: docker
pinned: false
---

# Quest
 
A Flask-first hybrid web application combining educational content and interactive tools for the Quest ecosystem — fitness, coding, and the Quest philosophy.

---

## The Hub

`quest_site` serves as the public-facing content hub and interactive tool center for the Quest ecosystem.

**This project is responsible for:**
- Serving **Refined Scrolls** organized by Series and Topic.
- Housing the **Archive** of legacy articles.
- Providing interactive fitness and math tools (Dash calculators).
- Hosting the **Portfolio & Resume** (`/portfolio`) for the creator.

---

## Content Model

The site follows a **Series-First model**:

1.  **Refined Scrolls**: The core content unit.
    -   **Series View** (Default): Scrolls are read in a narrative journey (e.g., `1_the_story`).
    -   **Topic View**: Scrolls are aggregated by subject (e.g., "Hypertrophy") using their Direction DNA.
2.  **The Archive**: A collection of legacy long-form articles.

---

## Tech Stack

- **Flask** — Routes, templates, markdown rendering
- **Dash/Plotly** — Interactive tools (mounted at `/tools/*`)
- **Jinja2** — Template engine
- **markdown2** — Converts `.md` files to HTML with extras (tables, code blocks, metadata parsing)

---

## Running Locally

```powershell
# Setup (one-time)
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# Run
.venv\Scripts\python.exe app.py
```

Visit **http://localhost:9000** (Default Port)

---

## Project Structure

```
quest_site/
├── app.py                      # Flask app with Dash mount
├── requirements.txt            # Dependencies
├── doc_todo/
│   └── DASH_TOOLS_DEPLOYMENT.md  # Architecture & deployment strategy
├── static/
│   ├── css/style.css          # Jackked design system
│   └── images/                # Assets
├── templates/
│   ├── base.html              # Layout with nav & theme toggle
│   ├── listing.html           # Index pages (Scrolls sorted by Series/Topic)
│   ├── article.html           # Scroll reading view
│   └── 404.html               # Custom error page
├── content/
│   ├── scrolls/               # New Content (Series Folders)
│   └── archive/               # Legacy Articles
├── tools/
│   ├── dash_utils.py          # Shared Dash helpers (Back button, Theme sync)
│   ├── body_calculator/       # Dash App: Body Comp
│   └── fitnotes_cleaner/      # Dash App: FitNotes Tool
└── utils/
    └── content_loader.py      # Custom Loader (Parses folders & direction metadata)
```

---

## Future Plans

- **Interactive Scroll Components**: Embed mini-calculators directly into markdown.
- **1RM Calculator**: Dedicated tool for strength estimation.

---

## Deployment (Hugging Face Spaces)

This site is designed to run on **Hugging Face Spaces** using the **Docker SDK**.

### Environment Variables
Set these in **Settings > Variables and secrets** if needed:
- `FLASK_ENV`: `production` (optional)
- `PORT`: `7860` (default for HF Spaces, handled automatically by `app.py`)

### Remote Repositories
This project syncs to two locations:
1.  **GitHub (`origin`)**: The source code repository.
2.  **Hugging Face Spaces (`space`)**: The production build server.

**Deployment Workflow:**
```powershell
# 1. Commit changes
git commit -m "Your update"

# 2. Deploy to Hugging Face
git push space main

# 3. Backup to GitHub
git push origin main
```

### Troubleshooting

#### Binary Files (Git LFS)
Hugging Face rejects pushes containing large binary files (like images) in the git history. We use **Git LFS** for `*.png`.
If you add new image types, track them:
```powershell
git lfs track "*.jpg"
git add .gitattributes
```

#### YAML Metadata (Crucial)
The `README.md` frontmatter MUST use allowed colors.
- **Colors**: Use `green`, `yellow`, `blue`, etc. (NOT `teal` or `orange`).
- **SDK**: Must be `docker`.

---

**The best risk-to-reward project is yourself.**