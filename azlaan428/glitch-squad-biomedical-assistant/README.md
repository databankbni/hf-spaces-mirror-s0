---
title: ARIA - Research Synthesis & Integrity Auditor
emoji: 🧬
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# ARIA — Autonomous Research Intelligence Agent

> Multi-agent research synthesis and integrity auditing · originally built for the AMD Developer Hackathon 2026
> **Team Glitch Squad** — Ziauddin University, Karachi, Pakistan

---

## What It Does

ARIA is a multi-agent pipeline that takes a research question, retrieves literature, synthesises it into a structured report, and then — on demand — runs a second layer of agents that audit that synthesis for citation accuracy, methodological consistency, and reproducibility.

The pipeline and audit logic are domain-agnostic. The current live demo is wired to **biomedical literature via PubMed and Europe PMC**, but nothing about the architecture is biomedical-specific — swapping the retrieval source and prompts would repoint it at any other literature corpus.

## Pipeline (5 stages)

```
Query Architect → Literature Scout → PRISMA Filter → Evidence Synthesiser → Citation Builder
```

1. **Query Architect** — generates up to 5 MeSH-optimised search queries from your research question
2. **Literature Scout** — fetches each query against PubMed (Entrez, up to 5 results) and Europe PMC (up to 3 results), deduplicating by PMID
3. **PRISMA Filter** — screens every retrieved paper as included/excluded against the question, with a one-line reason for each exclusion
4. **Evidence Synthesiser** — builds a structured 6-section synthesis (Background, Key Findings, Level of Evidence, Conflicting Evidence, Research Gaps, Clinical Implications) with inline PMID citations, using only PRISMA-included papers
5. **Citation Builder** — formats a numbered reference list (authors, journal, year, PMID)

## Integrity Audit (5 agents)

Run on demand after synthesis via the "Run Integrity Audit" button. Results are grouped into **Internal Consistency** and **External Validity**, same as the UI:

**Internal Consistency**
- **Methodology Drift Tracker** — checks whether a paper's stated methodology actually matches its own reported results
- **Confidence Calibration Check** — checks whether the language strength of a synthesis claim matches the actual strength of the evidence behind it

**External Validity**
- **Citation Ghost Detector** — checks every PMID-cited claim in the synthesis against the source abstract it cites
- **Cross-Paper Contradiction Finder** — compares findings across pairs of retrieved papers for agreement or contradiction
- **Reproducibility Score** — scores each paper 0–100 on whether it reports sample size, statistical methods, data/code/materials availability, and inclusion/exclusion criteria

## UI

A sticky, collapsible side-panel with six tabs: **Main**, **Integrity Audit**, **PRISMA**, **References**, **Comparison**, **Follow-up**.

## Other features

- Real-time SSE streaming — progress bar updates as each pipeline stage completes
- Evidence confidence scoring — green/yellow/red badges on each synthesis section, from a second LLM pass
- Abstract viewer — click any citation to expand the full abstract inline
- Evidence comparison table — LLM-extracted structured table of studies/methods/outcomes
- Selective literature review — check specific citations and generate a focused academic paragraph from just those papers
- Predictive forecasting — constructive and destructive forecasts derived from the synthesised evidence
- Follow-up Q&A — ask follow-up questions answered from the already-fetched papers, no re-fetching
- Query refinement suggestions — 3 AI-generated follow-up research questions based on synthesis gaps
- Session history — queries saved to `sessions.json`, reloadable from the sidebar
- **PDF export** — synthesis, evidence comparison table, PRISMA exclusions (with reasons), and the full Integrity Audit, all in one report. Tables and audit cards are page-break-safe: reportlab only starts a new page when a table/card wouldn't fit on the current one, never splitting a row or card across the boundary.

## Tech Stack

| Component | Technology |
|-----------|------------|
| LLM | **Qwen2.5-72B-Instruct via vLLM on AMD MI300X, with automatic fallback to Groq (`llama-3.1-8b-instant`)**. `get_llm()` in `agent/agent.py` probes `VLLM_BASE_URL` before each request; if it's unset or unreachable, it falls back to Groq automatically and logs which backend actually served the request. See [Deploying Your Own AMD MI300X Inference Backend](#deploying-your-own-amd-mi300x-inference-backend) to stand up the vLLM endpoint yourself. |
| Agent Framework | LangGraph + LangChain |
| Literature Retrieval | BioPython Entrez (PubMed) + Europe PMC REST API |
| Web Framework | Flask, SSE streaming |
| PDF Generation | ReportLab |
| Frontend | HTML, CSS, vanilla JS |
| Deployment | Docker container on Hugging Face Spaces |

## Setup

```bash
git clone https://github.com/azlaan428/glitch-squad-biomedical-assistant.git
cd glitch-squad-biomedical-assistant
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Set your Groq API key (required — the app raises an error at request time if it's missing):

```bash
export GROQ_API_KEY=your_key_here      # Windows PowerShell: $env:GROQ_API_KEY = "your_key_here"
```

## Run

```bash
python app.py
```

Open http://localhost:7860 (default port, overridable via the `PORT` env var — this is what the Dockerfile also sets for Hugging Face Spaces).

> Groq's free tier rate-limits fairly aggressively. Every LLM call in the pipeline retries with backoff on a 429, but a query against a large paper set can still take a couple of minutes if it has to back off repeatedly.

## Deploying Your Own AMD MI300X Inference Backend

ARIA defaults to Groq, but will automatically route through a self-hosted **Qwen2.5-72B-Instruct** model on an AMD MI300X GPU if you stand one up. Here's how to reproduce that setup from scratch.

1. **Create the droplet** — go to [devcloud.amd.com](https://devcloud.amd.com), sign in (or sign up), and create a new GPU droplet:
   - Choose an MI300X-backed instance (192GB VRAM)
   - Under **Choose an image → Quick Start**, select the vLLM package (ROCm 7.2.4 host, Ubuntu 24.04, vLLM 0.23.0 pre-installed)
   - Launch the droplet and note its public IPv4 address

2. **SSH in** (default user `root`, port `22`) using the SSH key you configured at droplet creation:
   ```bash
   ssh -i /path/to/your/key root@<droplet-public-ip>
   ```

3. **Confirm the environment.** The vLLM stack runs inside a pre-existing `rocm` docker container, with port 8000 already mapped through to the host:
   ```bash
   docker ps -a
   docker exec rocm pip show vllm
   rocm-smi          # confirms the GPU is detected
   ```

4. **Start the vLLM OpenAI-compatible server**, detached so it survives disconnecting your SSH session:
   ```bash
   docker exec -d rocm bash -lc \
     'nohup vllm serve Qwen/Qwen2.5-72B-Instruct --host 0.0.0.0 --port 8000 > /root/vllm_server.log 2>&1 &'
   ```

5. **Wait for it to finish loading** (roughly a few minutes for this model size — most of the time goes to the safetensors download and shard loading), then confirm it's serving:
   ```bash
   curl http://localhost:8000/v1/models
   ```

6. **Confirm external reachability** from your own machine:
   ```bash
   curl http://<droplet-public-ip>:8000/v1/models
   ```
   No firewall changes were needed in this deployment — `ufw`'s default policy already permitted port 8000 — but check `ufw status verbose` on your own droplet, since this can vary.

7. **Point ARIA at it.** Set `VLLM_BASE_URL` as an environment variable/repository secret wherever ARIA is deployed (e.g. Hugging Face Space → Settings → Repository secrets):
   ```
   VLLM_BASE_URL=http://<droplet-public-ip>:8000/v1
   ```

8. **Restart the deployment.** The footer and results badge should now read *"Powered by Qwen2.5-72B on AMD MI300X"* — confirming the app is actually routing through the AMD backend, not the Groq fallback.

> **If this droplet is destroyed** (e.g. after hackathon credits run out), ARIA doesn't break. `get_llm()` probes `VLLM_BASE_URL` before every request and falls back to Groq automatically and transparently the moment the endpoint stops responding, no code changes needed — the footer just updates to say so. That's by design, not a failure mode.

## Live Demo

https://huggingface.co/spaces/azlaan428/glitch-squad-biomedical-assistant

## Disclaimer

AI-generated synthesis — always verify against primary sources before clinical or other high-stakes use.
