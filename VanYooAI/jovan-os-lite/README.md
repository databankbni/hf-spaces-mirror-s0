---
title: Jovan OS Lite
emoji: 🐣
colorFrom: yellow
colorTo: yellow
sdk: gradio
app_file: app.py
pinned: false
---

# Jovan OS Lite

Jovan OS Lite is a portfolio MVP of a local agentic AI operating system for planning, evaluation, weekly review, and human-approved optimization.

It is not a generic chatbot. It is a small stateful system with a planner, evaluator, weekly reviewer, optimizer, SQLite persistence, markdown reports, deterministic Python scoring, and a human approval layer for weight changes.

## Core Loop

```text
Plan -> Execute -> Evaluate -> Review -> Optimize -> Human Apply
```

## Modes

### Hosted Demo Mode

Hosted Demo Mode is intended for Hugging Face Spaces or quick portfolio preview.

- Uses synthetic seed data.
- Returns static, public-safe sample outputs.
- Does not require an OpenAI API key.
- Does not call OpenAI agents.
- Shows a Demo Mode notice in the UI.

Set:

```text
DEMO_MODE=true
```

### Local Live Mode

Local Live Mode is the full app behavior.

- Requires `OPENAI_API_KEY`.
- Uses real OpenAI agent execution.
- Saves generated plans, evaluations, optimizer reports, and approved weight updates to SQLite.
- Exports latest reports to `reports/`.

Set:

```text
DEMO_MODE=false
OPENAI_API_KEY=your_api_key_here
```

## Environment

Copy `.env.example` to `.env` for local use:

```text
OPENAI_API_KEY=your_api_key_here
DEMO_MODE=false
```

For Hugging Face Spaces, set this environment variable instead:

```text
DEMO_MODE=true
```

Do not commit `.env`.

## Quick Start: Local Live Mode

```bash
uv sync
uv run seed_demo.py
uv run app.py
```

Open the Gradio URL shown in the terminal, usually:

```text
http://127.0.0.1:7860
```

## Quick Start: Hosted Demo Mode Locally

PowerShell:

```powershell
$env:DEMO_MODE="true"
uv run app.py
```

Reset to live mode:

```powershell
$env:DEMO_MODE="false"
```

## Agents

### Planner Agent

Creates structured daily plans from user request, active goals, domain weights, recent logs, and recent evaluations.

### Evaluator Agent

Compares a daily execution log against the latest saved plan, classifies completed/missed/unknown items, and returns structured scores and next actions. Python then calculates the final weighted score.

### Weekly Review Agent

Detects patterns across recent logs and evaluations, including bottlenecks, momentum, weak areas, and practical next targets.

### Optimizer Agent

Reviews goals, weights, logs, and evaluations to recommend conservative adjustments. It does not silently apply changes.

## Human Approval Layer

Optimizer recommendations are review-first. Weight changes require a manual Apply action in the UI.

```text
Optimizer recommendation -> User review -> Manual approval -> SQLite update
```

## Demo Data

Fresh databases are safely seeded with synthetic public-safe data if goals and weights are both empty.

Demo domains:

- Formal Education
- Projects / Skill Building
- Health / Training
- Career Visibility

No private user data is included in the repository.

## Tech Stack

- Python
- Gradio
- SQLite
- OpenAI Agents SDK
- Pydantic structured outputs
- Markdown reports
- Deterministic Python scoring

## Project Structure

```text
jovan_os_lite/
  app.py
  demo_outputs.py
  database.py
  os_agents.py
  prompts.py
  schemas.py
  scoring.py
  seed_demo.py
  README.md
  DEMO_SCRIPT.md
  pyproject.toml
  requirements.txt
```

Generated local files:

```text
data/
reports/
```

These are ignored by Git.

## Main Features

- Daily planning
- Daily execution evaluation
- Weekly review
- Dashboard
- Optimizer report
- Persistent SQLite state
- Markdown report export
- Pydantic structured outputs
- Python weighted scoring
- Human-approved weight updates
- Safe hosted demo mode

## Privacy

The following files and folders are intentionally ignored by Git:

```text
.env
data/
reports/
README_PRIVATE.md
notes.txt
notes.ipynb
```

This keeps API keys, local databases, private notes, and generated private reports out of the public repository.

## Status

Jovan OS Lite is a local MVP and portfolio demonstration of a practical agentic AI system.