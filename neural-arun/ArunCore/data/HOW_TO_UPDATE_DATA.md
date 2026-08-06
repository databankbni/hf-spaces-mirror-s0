# How to Update ArunCore Knowledge Data

ArunCore uses a modular single-source-of-truth structure for your project data.

---

## 📁 Data Structure Overview

```
data/
├── static/
│   ├── public_profile.md         # Your core identity, principles, vision & loop
│   └── rules_of_engagement.md   # LLM guidelines & zero-hallucination rules
│
└── github/                        # ONE clean folder per GitHub project
    ├── <project_name>/
    │   ├── README.md              # Project overview, tech stack, & direct GitHub URL link
    │   └── metadata.json          # Structured metadata (URL, stack, stars, topics)
    └── ...
```

---

## 🚀 How to Add or Update a Project

### Option A: Automatic GitHub Sync (Recommended)
Run the automated sync script to pull your latest READMEs and GitHub URLs directly from your GitHub profile (`neural-arun`):

```bash
python scripts/sync_github_data.py
```

### Option B: Manual Add
1. Create a new folder under `data/github/<your_repo_name>/`.
2. Place your project `README.md` and `metadata.json` inside it.
3. Make sure `README.md` starts with a link header:
   ```markdown
   > **GitHub Repository:** [https://github.com/neural-arun/your_repo_name](https://github.com/neural-arun/your_repo_name)
   ```

---

## 🔄 Re-Ingest into Vector DB

After adding or modifying files in `data/`:

```bash
python core/ingest.py
```

`ingest.py` incrementally updates ChromaDB so your agent instantly gains access to the new knowledge.
