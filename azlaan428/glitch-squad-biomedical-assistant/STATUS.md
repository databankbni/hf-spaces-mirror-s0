# ARIA Project Status
_Last updated: July 11, 2026_

## What Was Built

### Synthesis pipeline — `agent/agent.py`, 5 stages

1. **Query Architect** — generates up to 5 MeSH-optimised PubMed queries from the research question
2. **Literature Scout** — fetches each query against PubMed (Entrez, up to 5 results/query) and Europe PMC (up to 3 results/query), sequentially with a short pacing delay between calls, deduplicated by PMID. (Not parallelised — `ThreadPoolExecutor` is imported but currently unused.)
3. **PRISMA Filter** — one LLM call screens all retrieved papers as included/excluded with a one-line reason each; synthesis runs only on included papers
4. **Evidence Synthesiser** — structured synthesis: Background, Key Findings, Level of Evidence, Conflicting Evidence, Research Gaps, Clinical Implications
5. **Citation Builder** — formatted reference list with authors, journal, year, PMID

### Integrity Audit layer — 5 agents, run on demand post-synthesis

`agent/citation_ghost_detector.py`, `agent/methodology_drift_tracker.py`, `agent/confidence_calibration_check.py`, `agent/cross_paper_contradiction_finder.py`, `agent/reproducibility_score.py`, each behind its own POST route. UI groups results into Internal Consistency (Methodology Drift, Confidence Calibration) and External Validity (Citation Ghost, Cross-Paper Contradiction, Reproducibility Score), staggered on the client to avoid piling all 5 requests onto Groq's rate limit at once.

### UI

Side-panel tabbed layout (Main / Integrity Audit / PRISMA / References / Comparison / Follow-up), sticky and collapsible, desktop-responsive.

### Additional features

* SSE streaming: real-time 5-stage progress bar with percentage
* PRISMA-style paper screening with rationale
* Evidence confidence scoring: green/yellow/red badges per synthesis section
* Abstract viewer: click any citation to expand full abstract inline
* Evidence comparison table: LLM extracts a structured table with real author names, no duplicates
* Selective literature review: checkboxes on citations, generates a focused academic paragraph from just the selected papers
* Predictive model: constructive and destructive forecasts as a post-synthesis stage
* Follow-up Q&A: answered from already-fetched papers, no re-fetching
* Query refinement suggestions: 3 AI-generated follow-up research questions
* Session history: queries saved to `sessions.json`, reloadable from sidebar
* Rate-limit retry logic: every LLM call in `agent/agent.py` goes through `llm_invoke_with_retry` (exponential backoff on Groq 429s) — this was inconsistent as recently as this week (`run_table_extractor` was calling the LLM directly and would 500 on a rate limit instead of backing off); fixed 2026-07-11.
* SSL patch for PubMed/Europe PMC Entrez requests on networks with broken cert chains (corporate/university proxies)
* **PDF export**: synthesis, evidence comparison table, PRISMA exclusions (with reasons), and the full Integrity Audit (grouped Internal Consistency / External Validity, same as UI) in one report. Tables and audit cards are wrapped so reportlab avoids splitting a row or card across a page boundary, falling back to starting a fresh page only when a block genuinely doesn't fit the remaining space. Section is omitted entirely (no blank space, no error) if the audit hasn't been run yet. Verified end-to-end this session against a real query with real PubMed/Europe PMC/Groq data — all sections rendered correctly across a 9-page real-data PDF with no mid-table or mid-card splits.

## Tech Stack

* **LLM: Groq — `llama-3.1-8b-instant` (currently active)**. `agent/agent.py`'s `get_llm()` is hardcoded to Groq; there is no runtime provider switch. The project previously ran inference on **Qwen2.5-72B-Instruct via vLLM on a rented AMD MI300X** during the hackathon (commit `7dd2c52`), then reverted to Groq (commit `f81857a`, 2026-05-05) — the vLLM/Qwen code path no longer exists in the current tree, it's git history only. Re-enabling it means restoring that `get_llm()` implementation and standing up an inference endpoint again.
* Agent Framework: LangGraph + LangChain
* Literature Retrieval: BioPython Entrez (PubMed) + Europe PMC REST API
* Web Framework: Flask with SSE streaming
* PDF: ReportLab 4.5.0
* Frontend: HTML, CSS, vanilla JS
* Runtime: no GPU required for the current (Groq-backed) setup — any machine that can run Python 3.11+ and reach the Groq API. Developed/tested this session on Windows 11 with a local venv.

## API Endpoints

* `GET  /` — main UI
* `GET  /stream` — SSE pipeline stream (primary path)
* `POST /query` — standard non-streaming pipeline (fallback)
* `POST /suggest-queries` — 3 AI-generated follow-up research questions
* `POST /export-pdf` — PDF report download (synthesis + comparison table + PRISMA exclusions + integrity audit + references)
* `POST /score` — confidence scoring
* `POST /selective-review` — focused literature review from selected papers
* `POST /predict` — predictive model
* `POST /citation-ghost-check` — Integrity Audit: citation ghost detector
* `POST /methodology-drift-check` — Integrity Audit: methodology drift tracker
* `POST /confidence-calibration-check` — Integrity Audit: confidence calibration check
* `POST /cross-paper-contradiction-check` — Integrity Audit: cross-paper contradiction finder
* `POST /reproducibility-score` — Integrity Audit: reproducibility score
* `GET  /sessions` — load query history
* `POST /sessions/save` — save completed query
* `POST /extract-table` — evidence comparison table
* `POST /followup` — follow-up question against existing synthesis

## Environment

* `GROQ_API_KEY` — required, read directly from the process environment (no `python-dotenv` installed, so a `.env` file is **not** auto-loaded — Flask prints a tip about this at startup if one is present)
* `PORT` — optional, defaults to 7860
* Local dev: `python -m venv venv`, then `python app.py`

## Deployment status (honest as of this update)

There are three remotes; they are **not** in sync:

| Remote | Where | HEAD commit | Status |
|--------|-------|--------------|--------|
| `origin` | GitHub — `azlaan428/glitch-squad-biomedical-assistant` | `c965806` | Up to date — source of truth |
| `personal` | HF Space — `azlaan428/glitch-squad-biomedical-assistant` | `c965806` | Up to date at the git level (matches `origin`). Docker rebuild triggers automatically on push; the rebuilt Space itself was **not** independently re-verified in a browser this session — only local execution was tested directly |
| `hf` | HF Space — `lablab-ai-amd-developer-hackathon/glitch-squad-biomedical-assistant` (team/shared) | `4745039` | **14 commits behind.** This deployment predates the Groq revert — its `get_llm()` still points at `VLLM_BASE_URL`, i.e. it's still wired to the AMD MI300X vLLM endpoint from the hackathon. That endpoint was a rented instance and is presumed no longer running, meaning this Space is likely broken until either the endpoint is restored or it's redeployed from current `main`. Has none of the PRISMA filter, Integrity Audit, or PDF export work. |

**What was actually verified working this session (local execution, real data, no mocks):**
- Full 5-stage pipeline against a real query, real PubMed + Europe PMC retrieval, real Groq synthesis
- PRISMA filter producing real inclusion/exclusion decisions with reasons
- All 5 Integrity Audit checks run successfully against real synthesis/paper data
- `/export-pdf` producing a correct 9-page PDF with all new sections (Comparison Table, PRISMA Exclusions, Integrity Audit) present, correctly grouped, and with no mid-table/mid-card page splits
- Graceful skip of the Integrity Audit PDF section when no audit has been run
- `run_table_extractor` rate-limit retry fix

**Not verified this session:**
- The live rebuilt HF Space UI/behavior in a browser (no browser automation tool was available; testing was done by driving the Flask routes directly over HTTP against a local server)
- The `hf` (team) Space — known stale, not tested

## What Remains / Future Work

1. Redeploy or explicitly retire the `hf` (team hackathon) Space — it's currently stale and likely non-functional (dead vLLM endpoint)
2. Browser-based smoke test of the live `personal` HF Space post-deploy
3. If dual-provider support is wanted again, reintroduce a `get_llm()` switch (env-var gated) instead of hardcoding Groq, rather than relying on git history to bring Qwen/vLLM back
4. Demo video (carried over from hackathon submission checklist — status not reconfirmed this session)
5. Final lablab.ai submission (carried over — status not reconfirmed this session)
