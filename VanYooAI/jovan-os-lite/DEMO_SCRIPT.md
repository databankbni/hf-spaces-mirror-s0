# Demo Script

This demo shows how Jovan OS Lite works as a local agentic AI system.

The demo uses synthetic goals, generic domains, and public-safe execution logs. No private user data is required.

---

## Goal of the Demo

The goal is to demonstrate the core agentic loop:

```text
Plan → Execute → Evaluate → Save → Dashboard → Weekly Review → Optimize → Human Approval
```

The demo shows that the system is more than a chatbot. It has:

* multiple agents with different responsibilities
* persistent local state
* structured outputs
* evaluator logic
* optimizer recommendations
* human-approved updates

---

## 1. Prepare Environment

Install dependencies with `uv`:

```bash
uv sync
```

Create a local `.env` file with your API key:

```text
OPENAI_API_KEY=your_api_key_here
```

The `.env` file is local only and should not be committed to Git.

---

## 2. Seed Demo Data

Run:

```bash
uv run seed_demo.py
```

This creates synthetic demo goals and domain weights.

Demo goals:

```text
Complete university coursework
Build AI portfolio projects
Maintain fitness routine
Improve career visibility
```

Demo domain weights:

```text
formalno_obrazovanje: 30%
neformalno_obrazovanje: 30%
sport: 20%
karijera: 20%
```

The internal domain names are kept from the current local prototype, while the demo goal titles are generic and public-safe.

---

## 3. Start the App

Run:

```bash
uv run app.py
```

Open the local Gradio URL shown in the terminal.

It will usually look like:

```text
http://127.0.0.1:7860
```

---

## 4. Planner Demo

Open the **Planner** tab.

Use this example input:

```text
Study, project work, and training.
```

Expected output:

* a daily plan
* required tasks
* recommended tasks
* success criteria
* warnings or tradeoffs

What this demonstrates:

```text
The Planner Agent creates a structured daily plan from a short user request, while considering active goals and domain weights.
```

---

## 5. Evaluator Demo

Open the **Evaluator** tab.

Use this example execution log:

```text
Completed a 90-minute study block. Fixed one project bug and updated the README. Skipped training due to time constraints.
```

Expected output:

* completed study task
* completed project task
* missed training task
* unknown items if some planned tasks were not mentioned
* domain scores
* plan completion score
* final weighted score
* next actions

What this demonstrates:

```text
The Evaluator Agent compares the execution log against the latest saved plan. It distinguishes completed, missed, and unknown items instead of treating missing information as automatic failure.
```

---

## 6. Dashboard Demo

Open the **Dashboard** tab.

Expected output:

* latest score
* last evaluation date
* current domain weights
* active goals
* latest plan preview
* latest evaluation preview
* latest optimization preview, if already generated

What this demonstrates:

```text
The Dashboard shows the current state of the system from SQLite. This demonstrates persistent memory/state, not just a one-off chat response.
```

---

## 7. Weekly Review Demo

Open the **Weekly Review** tab.

Click the button to generate a weekly review.

Expected output:

* strongest momentum
* weak areas
* repeated bottlenecks
* lack of closure
* recommended next actions

What this demonstrates:

```text
The Weekly Review Agent looks across recent evaluations and logs to identify patterns, not just a single-day result.
```

---

## 8. Optimizer Demo

Open the **Optimizer** tab.

Click:

```text
Generate Optimizer Report
```

Expected output:

* system diagnosis
* what should stay the same
* recommended goal changes
* recommended weight changes
* concrete targets for the next cycle
* main risk
* next operating rule
* apply decision

What this demonstrates:

```text
The Optimizer Agent analyzes goals, weights, recent logs, and evaluations. It recommends small system changes, but does not apply them automatically.
```

---

## 9. Human Approval Demo

In the **Optimizer** tab, click:

```text
Apply Latest Weight Recommendations
```

Expected output:

* confirmation message
* new domain weights table

Then open the **Dashboard** tab again.

Expected result:

* updated domain weights are visible in the dashboard

What this demonstrates:

```text
The system has a human approval layer. The optimizer recommends changes, but the user must approve them before the database is updated.
```

---

## 10. Reports Demo

Check the local `reports/` folder.

Expected generated files:

```text
reports/latest_plan.md
reports/latest_evaluation.md
reports/latest_optimization.md
```

What this demonstrates:

```text
The system exports markdown reports, making the agent outputs inspectable and reusable.
```

The `reports/` folder is ignored by Git because generated reports may contain local private data.

---

## Suggested Demo Narration

```text
Jovan OS Lite is a local personal agentic operating system.

It uses several agents with different responsibilities:
Planner, Evaluator, Weekly Review, and Optimizer.

The system stores goals, weights, plans, evaluations, and optimization reports in SQLite.

The Planner generates a daily plan.
The Evaluator compares execution against that plan.
The Weekly Review detects longer-term patterns.
The Optimizer recommends small system-level improvements.

The most important part is the human approval loop:
the optimizer can recommend changes, but the user must manually approve updates before they are applied.
```

---

## Core Architecture Demonstrated

```text
User Input
   ↓
Planner Agent
   ↓
Plan saved to SQLite
   ↓
Execution Log
   ↓
Evaluator Agent
   ↓
Python Weighted Scoring
   ↓
Evaluation saved to SQLite
   ↓
Dashboard / Weekly Review
   ↓
Optimizer Agent
   ↓
Structured Recommendations
   ↓
Human Approval
   ↓
Updated Domain Weights
```

---

## Notes

This demo uses synthetic data created by `seed_demo.py`.

The local SQLite database, generated reports, and `.env` file are not included in the repository.

Users can modify the demo goals and weights in `seed_demo.py`.

The current MVP keeps the original internal domain identifiers:

```text
formalno_obrazovanje
neformalno_obrazovanje
sport
karijera
```

Future versions could make domains fully user-configurable.
