---
title: MAGI System
emoji: 🔮
colorFrom: purple
colorTo: blue
sdk: gradio
app_file: app.py
pinned: false
license: mit
---

# MAGI System v2 (Available on Hugging Face Spaces)

The Magi System is a multi-agent consensus system where 3 distinct "personas" (Melchior, Balthasar, Casper) debate a user's question, and a Master Agent (Gemini) synthesizes the final verdict.

## Concept
Inspired by the supercomputer system from a famous anime, this AI simulates three distinct thought patterns:

*   **MELCHIOR (The Scientist):** Purely logical, data-driven, ignores emotions.
*   **BALTHASAR (The Mother):** Ethical, protective, focuses on humanity and safety.
*   **CASPER (The Woman):** Intuitive, emotional, focuses on personal desire and curiosity.

## Architecture
This version uses a **Single-Shot Architecture** to minimize API calls and latency. A single complex prompt simulates all three experts and the judge in one pass.

## Setup
To run this Space locally or fork it:
1.  Clone the repo.
2.  Install requirements: `pip install -r requirements.txt`
3.  Set `GOOGLE_API_KEY` in your environment variables.
4.  Run `python app.py`.
