---
project_name: web_wizard
github_url: https://github.com/neural-arun/web_wizard
language: HTML
stars: 0
topics: 
updated_at: 2026-04-08T06:10:58Z
---

# web_wizard

> **GitHub Repository:** [https://github.com/neural-arun/web_wizard](https://github.com/neural-arun/web_wizard)  
> **Primary Language:** HTML | **Stars:** 0 | **Forks:** 0  
> **Description:** No description provided.

---

# Playwright Web Automation & Scraping Curriculum

Welcome to my learning repository for advanced web automation, scraping, and testing using **Playwright for Python**. This repository tracks my progress as I work through a comprehensive, progressive curriculum, from absolute basics to distributed, AI-integrated crawler systems.

## 🚀 The Tech Stack

This project focuses on modern, resilient Python automation:

*   **Core Automation:** Playwright for Python (`playwright`, `playwright-python`)
*   **Testing & CI:** `pytest`, `pytest-playwright`, GitHub Actions, Docker
*   **Data Processing:** `pandas`
*   **Data Storage:** PostgreSQL (via `sqlalchemy`, `psycopg2`), Redis
*   **Message Queues & Orchestration:** Celery, RabbitMQ
*   **AI & Vector Integration:** ChromaDB / Pinecone, Langchain (for Agent tool building)

## 🛠️ Environment Setup

To run the scripts and projects in this repository, you'll need to set up the Python virtual environment and install the required browser binaries.

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/neural-arun/web_wizard.git
    cd web_wizard
    ```

2.  **Create and activate the virtual environment (Windows):**
    ```powershell
    python -m venv venv
    .\venv\Scripts\Activate.ps1
    ```

3.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Install Playwright Browsers (Chromium, Firefox, WebKit):**
    ```bash
    playwright install
    ```

## 📚 Curriculum Map

The learning journey spans from foundational concepts to production-ready, distributed architectures.

### Part 1: Foundations & Core API
*   **Module A:** Foundations (Python async, HTTP, DOM, DevTools)
*   **Module B:** Playwright Core API (Locators, navigation, tracing, emulation)
*   **Module C:** Network & Data Extraction (Interception, JSON parsing, API mocking)
*   **Module D:** Automation Reliability & Debugging (Flaky tests, fallbacks, Playwright Inspector)

### Part 2: Advanced Scraping & Scale
*   **Module E:** Stealth & Anti-bot (Context isolation, proxies, rate limits)
*   **Module F:** Performance & Concurrency (Asyncio pooling, memory optimization)
*   **Module G:** Integration with Data Stack (Postgres, Pandas, Export formats)
*   **Module H:** Testing, CI, Containerization (Docker, Pytest fixtures)

### Part 3: Production & AI Integration
*   **Module I:** Advanced Targets (Infinite scroll, SPAs, multi-step auth)
*   **Module J:** Anti-fraud & Resilience (Ban recovery, circuit breakers)
*   **Module K:** Production Orchestration (Queueing with Celery/RabbitMQ, Autoscaling)
*   **Module L:** Playwright as an Agent Tool (Building sandbox tools for LLM integration)

## 🏗️ Hands-on Projects

1.  **Project 1:** Single-page scraper (CSV Export)
2.  **Project 2:** Login-protected scraper
3.  **Project 3:** Infinite-scroll scraper & deduplication
4.  **Project 4:** XHR-intercept scraper
5.  **Project 5:** Multi-user crawler writing to Postgres
6.  **Project 6:** Playwright-agent connector for LLM/RAG workflows
7.  **Capstone:** Distributed, Dockerized crawler with queue-based orchestration and vector DB pipeline.

*See the full detailed syllabus in `curriculum.md`.*
