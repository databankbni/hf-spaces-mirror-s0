---
title: Arabic Books Publisher
emoji: 📚
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# 📚 Arabic Books Publisher (Enterprise Edition v1.0)

Arabic Books Publisher is an autonomous, fully asynchronous python service designed to run 24/7 on HuggingFace Spaces (via Docker). It queries high-quality public domain sources for Arabic PDF books, processes them through Gemini AI to generate review summaries and metadata, and schedules them natively inside Telegram channels.

---

## 🌟 Key Features

1. **Fully Asynchronous Execution**: Built from the ground up using `asyncio`, `aiohttp`, and Telethon.
2. **Stateless Operations**: Designed for ephemeral cloud environments like HuggingFace Spaces (Docker). All queue states, caches, and scheduled metadata are synced via Firebase Firestore.
3. **Advanced PDF Validation**: Checks magic bytes, page readability, Arabic language characters, and extracts the book cover page (first page to PNG) using PyMuPDF.
4. **Arabic Normalization & Duplicate Prevention**: Combines normalized title/author fields (removing tashkeel/diacritics) with file content hashes to generate unique fingerprints.
5. **Credential Discovery & Failover**: Scrapes environment variables automatically for api keys or sessions, monitors key health, and fails over to backup keys on rate-limits (429) or invalidations.
6. **Dynamic Sources Ranking**: Rates books sources (Internet Archive, Hindawi, Open Library) dynamically based on success metrics and temporarily blacklists poor-performing sources.
7. **Telegram Native Scheduling**: Directly schedules posts (Cover photo + caption followed by the PDF file 10s later) on Telegram servers so publishing continues even if the space goes offline.
8. **Interactive Web Dashboard**: Exposes an Arabic/English web dashboard on port `7860` to pass HuggingFace health checks and monitor live diagnostics.

---

## 📂 Project Structure

This project follows Clean Architecture principles:

- [config.py](file:///C:/Users/MSI/.gemini/antigravity/scratch/arabic_books_publisher/config.py): App configurations and feature flags.
- [app.py](file:///C:/Users/MSI/.gemini/antigravity/scratch/arabic_books_publisher/app.py): Main application entry point and dashboard server.
- [Dockerfile](file:///C:/Users/MSI/.gemini/antigravity/scratch/arabic_books_publisher/Dockerfile): Container compiler.
- [requirements.txt](file:///C:/Users/MSI/.gemini/antigravity/scratch/arabic_books_publisher/requirements.txt): Python dependencies.
- **[core/](file:///C:/Users/MSI/.gemini/antigravity/scratch/arabic_books_publisher/core)**: Domain models and abstract interfaces.
- **[database/](file:///C:/Users/MSI/.gemini/antigravity/scratch/arabic_books_publisher/database)**: Firestore client and repository adapter.
- **[ai/](file:///C:/Users/MSI/.gemini/antigravity/scratch/arabic_books_publisher/ai)**: Prompt manager and Gemini client integrations.
- **[books/](file:///C:/Users/MSI/.gemini/antigravity/scratch/arabic_books_publisher/books)**: Downloader, validator, and fingerprint normalization engines.
- **[sources/](file:///C:/Users/MSI/.gemini/antigravity/scratch/arabic_books_publisher/sources)**: Scrapers for Internet Archive, Hindawi, and Open Library.
- **[telegram/](file:///C:/Users/MSI/.gemini/antigravity/scratch/arabic_books_publisher/telegram)**: Client pool manager and native scheduled publishing wrappers.
- **[scheduler/](file:///C:/Users/MSI/.gemini/antigravity/scratch/arabic_books_publisher/scheduler)**: Timezone-aware APScheduler loop runner.
- **[monitoring/](file:///C:/Users/MSI/.gemini/antigravity/scratch/arabic_books_publisher/monitoring)**: Advanced colored rotated log writer.
- **[utils/](file:///C:/Users/MSI/.gemini/antigravity/scratch/arabic_books_publisher/utils)**: Credential discovery and health pooling utilities.

---

## 📖 Documentation Hub

For details, refer to the individual markdown guides:

1. ⚙️ **[Installation & Local Setup](file:///C:/Users/MSI/.gemini/antigravity/scratch/arabic_books_publisher/docs/Installation.md)**: Local virtualenv settings, `.env` file configurations, and database mock guidelines.
2. 🚀 **[HuggingFace Spaces Deployment](file:///C:/Users/MSI/.gemini/antigravity/scratch/arabic_books_publisher/docs/Deployment.md)**: Steps to create a Docker space, generate Telethon Session strings, encode Firebase keys to Base64, and push code.
3. 🛠️ **[Maintenance & Admin Guide](file:///C:/Users/MSI/.gemini/antigravity/scratch/arabic_books_publisher/docs/Maintenance.md)**: Details on log structures, file retention cleanups, backup procedures, key rotations, and manual overrides.
4. 📐 **[Technical Architecture & Workflows](file:///C:/Users/MSI/.gemini/antigravity/scratch/arabic_books_publisher/docs/Architecture.md)**: High-level architectural diagrams, dependency injection details, and sequence flowcharts of book processing.

---

## ⚡ Quick Start

1. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```
2. Configure your credentials in a `.env` file in the root directory.
3. Set your target Telegram channel details in the Firestore `channels` collection.
4. Start the application:
   ```bash
   python app.py
   ```
5. Open `http://localhost:7860` in your web browser to view the status dashboard.
