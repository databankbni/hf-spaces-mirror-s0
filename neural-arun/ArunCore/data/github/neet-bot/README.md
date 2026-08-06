---
project_name: neet-bot
github_url: https://github.com/neural-arun/neet-bot
language: Python
stars: 0
topics: 
updated_at: 2026-07-22T14:10:23Z
---

# neet-bot

> **GitHub Repository:** [https://github.com/neural-arun/neet-bot](https://github.com/neural-arun/neet-bot)  
> **Primary Language:** Python | **Stars:** 0 | **Forks:** 0  
> **Description:** No description provided.

---

# 🧬⚡🧪 NEET 2027 Multi-Bot Platform & CBT Hub

Welcome to the **NEET 2027 Preparation Platform** — an AI-powered, multi-bot ecosystem and web interface built to help NEET aspirants master **Biology**, **Physics**, and **Chemistry** through 17,735+ NCERT line-by-line MCQs, real-time CBT exam timers, and instant PDF report cards with personalized AI weak area diagnostics.

---

## 🌟 Platform Overview

The platform operates 3 concurrent Telegram bots and a unified web interface:

1. **🧬 GPT Biology Bot (`@gptbiologybot`)**: 32 Chapters • 7,735 NCERT Line-by-Line MCQs.
2. **⚡ GPT Physics Bot (`@gptphysicsbot`)**: 20 Chapters • 5,000 Numerical & Formula MCQs.
3. **🧪 GPT Chemistry Bot (`@gptchemistrybot`)**: 20 Chapters • 5,000 Reaction & Concept MCQs.

---

## 📁 Repository Directory Structure

```
neet_pp/
├── neet_bot/                    # Master Multi-Bot Engine & Web Server
│   ├── data/                    # Bundled Datasets (Biology, Physics, Chemistry)
│   ├── web/                     # Web Test Simulator & Admin Dashboard
│   ├── main.py                  # Server entry point & 3-bot polling thread manager
│   ├── bot_handlers.py          # Telegram bot handlers & menu logic
│   ├── pdf_report.py            # ReportLab PDF Report Card generator
│   ├── ai_analyzer.py           # OpenAI GPT diagnostic evaluator
│   ├── questions.py             # Balanced chapter question sampling engine
│   ├── db.py                    # SQLite database for test history & analytics
│   ├── config.py                # Environment variables & bot tokens
│   └── test_system.py           # Automated diagnostic test suite (8/8 tests pass)
├── physics_bot/                 # Physics Bot module & standalone data mirror
├── chemistry_bot/               # Chemistry Bot module & standalone data mirror
├── data/                        # Raw NCERT scraped questions & PYQ archives
├── scratch/                     # Data generation & cleaning pipeline scripts
├── bot_welcome_messages.txt     # Copyable Telegram welcome messages
└── README.md                    # Root project documentation
```

---

## 🛠️ Key Features

- **17,735+ NCERT MCQs**: Organized in official NTA / NCERT textbook chapter sequence.
- **Balanced Multi-Chapter Random Sampling**: Equal question distribution across selected chapters without template repetitions.
- **Clean Formula & Symbol Formatting**: Automatic conversion of LaTeX formulas, chemical equations (`H₂SO₄`, `CH₃-CH=CH₂`, `sp³d²`), and angle notation (`45°`).
- **Instant AI PDF Report Cards**: Returns a full test paper answer key followed by an AI Weak Area Diagnostic analyzing missed NCERT sub-concepts.
- **Creator Connect**: Integrated Instagram ([@neural.arun](https://www.instagram.com/neural.arun/)) and LinkedIn ([in/neuralarun](https://www.linkedin.com/in/neuralarun/)) links for author Arun Yadav.

---

## 🧪 System Diagnostics & Automated Testing

To verify the platform's health across all datasets, bots, PDF engine, and AI diagnostic evaluator:

```bash
python3 neet_bot/test_system.py
```

---

## 🚀 Local Setup & Deployment

1. **Clone the repository**:
   ```bash
   git clone https://github.com/neural-arun/neet-bot.git
   cd neet-bot
   ```

2. **Install dependencies**:
   ```bash
   pip install -r neet_bot/requirements.txt
   ```

3. **Start the Multi-Bot Engine & Web Server**:
   ```bash
   python3 neet_bot/main.py
   ```

---

*Crafted with ❤️ by **Arun Yadav** for NEET 2027 Aspirants.*