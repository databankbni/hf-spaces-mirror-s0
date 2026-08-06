# 📊 Knowledge Base Data Directory (`/data/`)

This folder is the **single source of truth knowledge base** for Arun's AI Assistant. The ingestion engine (`core/ingest.py`) indexes all files here into ChromaDB vector memory (`db/`).

---

## 📁 Directory Structure

```
data/
├── static/
│   ├── public_profile.md         # Core identity, contact info, project value specs, stack & career overview
│   └── rules_of_engagement.md   # Behavioral rules, safety boundaries, and response guidelines
├── github/                       # 22+ curated project repositories (README + metadata per repo)
│   └── [project_name]/
│       ├── README.md             # Full project README scraped from GitHub
│       └── metadata.json         # Stars, language, last push, topics
├── linkedin/
│   └── profile_summary.md        # Synced LinkedIn posts, insights, and engagement metrics
└── raw/
    └── unknown_questions.json    # ← Real-Time Active Learning Store: Arun's verified human Q&A pairs
```

---

## 📁 Detailed File Overview

### 1. `data/static/public_profile.md`
- Defines Arun Yadav's background, contact details (+91 8881109193, `neural.arun.dev@gmail.com`), core engineering philosophy, specialization in Healthcare & Education AI systems, detailed project specs (Legal RAG IPC chunking, MedCoach reasoning tutor, NEET 10,000+ MCQs, 99acres scraper), and operating principles.

### 2. `data/static/rules_of_engagement.md`
- Defines system instructions for the AI assistant — zero-hallucination rules, when to cite GitHub repos, how to handle unknown questions, when to trigger lead alerts, and dynamic 100% language matching behavior.

### 3. `data/github/` — Project Knowledge Base
- Contains 22+ individual subfolders for each of Arun's projects (e.g., `ArunCore`, `deep_research`, `legal_RAG_system`, `med_coach`, `neet-bot`). Each folder contains a detailed `README.md` and `metadata.json` for RAG vector retrieval.
- **Alias Resolution**: Maps common name variations (e.g. `MedCoach`, `med coach`, `clinical tutor`) to the correct project folder automatically.

### 4. `data/linkedin/profile_summary.md`
- Contains synced LinkedIn posts and articles written by Arun.

### 5. `data/raw/unknown_questions.json` ← Real-Time Active Learning Store
- **What it is**: A JSON file that stores Q&A pairs verified by Arun himself.
- **How it works (2 Real-Time Triggers)**:
  1. **Website Admin Reply Bar**: Whenever Real Arun responds to a visitor from the 3-way live chat Admin Reply Bar, the backend automatically extracts the visitor's question, pairs it with Real Arun's answer, appends it here, and triggers background ChromaDB vector DB re-ingestion.
  2. **Telegram Swipe Reply**: Whenever Real Arun replies to an alert message on Telegram, the bot auto-saves the pair here and re-ingests ChromaDB.
- **Format**:
  ```json
  [
    {
      "question": "What is Arun favorite IDE for AI agent development?",
      "answer": "I use Antigravity IDE and Cursor for building agentic AI systems.",
      "timestamp": "2026-07-30T10:16:47Z"
    }
  ]
  ```

---

## ➕ How Knowledge Increases Automatically

1. **Option A: Real-Time Admin Reply Bar (Website)**: Type an answer on the live website chat panel as Real Arun. System auto-ingests into vector DB.
2. **Option B: Telegram Swipe Reply (Mobile)**: Swipe-reply to any alert on Telegram. System auto-ingests into vector DB.
3. **Option C: Direct File Edit**: Edit `data/static/public_profile.md` and run `python core/ingest.py`.
