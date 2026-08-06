# 🤖 ArunCore Prompts Directory

Welcome to the **ArunCore Prompts Directory**! This folder houses all system prompts, conversation steering rules, and human takeover guidelines for **Arun's AI Twin**.

Instead of hardcoding prompt strings inside Python source files, the backend (`core/agent.py`) reads these Markdown files dynamically. You can edit any of these prompt files directly to adjust your AI Assistant's tone, rules, personality, or guardrails without touching Python code!

---

## 📂 File Directory & Overview

| File Name | Purpose | What It Controls |
|---|---|---|
| 📄 [`system_prompt.md`](./system_prompt.md) | **Core Persona & Rules** | AI Twin identity, speaking tone, exact language matching (English vs. Hinglish), value-first project explanations, and hiring/lead capture workflows. |
| 📄 [`guardrails.md`](./guardrails.md) | **Conversation Steering & Guardrails** | Defines the **Bridge & Pivot** philosophy. Guarantees that questions about Arun are ALWAYS answered with 100% enthusiasm, and off-topic queries receive a friendly answer before smoothly steering back to Arun's work. |
| 📄 [`handoff_prompt.md`](./handoff_prompt.md) | **Live Human Takeover (3-Way Chat)** | Instructions for co-piloting live conversations when the **Real Arun (👨‍💻 Arun Yadav)** joins the chat via Telegram link, plus alert triggers. |

---

## 🛠️ How to Edit & Customize Prompts

1. Open any of the `.md` files in this directory.
2. Edit the plain English text to update persona, tone, guardrails, or rules.
3. Save the file.
4. The Python backend reads these files via `load_static_context()` in `core/agent.py` on startup/execution.

---

## 💡 Best Practices for Editing Prompts

- **Tone Adjustments**: If you want your AI Twin to sound more technical, casual, or humorous, edit the **Core Identity & Voice** section in `system_prompt.md`.
- **Language Matching**: The AI is instructed to match the user's exact language (100% English for English users, casual Hinglish for Hinglish users). Preserve this rule in `system_prompt.md`.
- **Preventing Rigid Refusals**: Maintain the **Bridge & Pivot** rules in `guardrails.md` so the AI never outputs robotic refusals like *"I don't answer trivia"*.
