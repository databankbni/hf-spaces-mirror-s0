# 🛠️ Scripts & Data Automation (`/scripts/`)

This folder contains **Python utility, evaluation, and sync scripts** used to automate knowledge base updates from GitHub and LinkedIn, as well as stress-test AI performance.

---

## 📁 File Descriptions

### 1. 🐙 `scripts/sync_github_data.py`
- **What it does**: Connects to GitHub API, inspects all of Arun's public repositories (`neural-arun`), downloads fresh `README.md` files and metadata, and updates `data/github/` automatically.
- **How to run**:
  ```bash
  python scripts/sync_github_data.py
  ```

---

### 2. 💼 `scripts/sync_linkedin.py`
- **What it does**: Uses Apify API to fetch recent LinkedIn posts, articles, and engagement metrics from Arun's LinkedIn profile, and updates `data/linkedin/profile_summary.md`. Automatically triggers re-ingestion into ChromaDB vector memory.
- **How to run**:
  ```bash
  python scripts/sync_linkedin.py
  ```

---

### 3. 🧪 `scripts/evaluate_30_questions.py`
- **What it does**: Runs the 30-question stress-test benchmark suite across 6 categories (Identity, Live GitHub, RAG Projects, LinkedIn Insights, Lead Handoffs, Safety Guardrails) and saves the results to `test_output_30.json`.
- **How to run**:
  ```bash
  PYTHONPATH=. python scripts/evaluate_30_questions.py
  ```
