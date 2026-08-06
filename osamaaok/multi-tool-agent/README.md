---
title: Multi Tool Agent
emoji: 🤖
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
---

# Multi-Tool Agent — Agentic AI with Intelligent Tool Routing

An AI agent that routes each question to the right tool automatically — calculator for math, web search for current information, or knowledge base retrieval for AI/ML concepts — then synthesizes a clean final answer. Built end-to-end with a FastAPI backend, Docker deployment, and a verified evaluation harness.

## Live Demo

**Deployed:** [huggingface.co/spaces/osamaaok/multi-tool-agent](https://huggingface.co/spaces/osamaaok/multi-tool-agent)

Ask it anything:
- Math → routed to calculator (guaranteed correct arithmetic)
- Current events / weather / prices → routed to web search (live Tavily results)
- AI/ML concepts (MCP, agents, RAG) → routed to knowledge base (FAISS semantic search)

## How It Works

```
User question
     ↓
Router (Groq LLM + function calling)
     ↓ decides which tool
┌────────────┬───────────────┬──────────────────┐
│ Calculator │  Web Search   │  RAG Retrieval   │
│ (Python)   │  (Tavily API) │  (FAISS + embed) │
└────────────┴───────────────┴──────────────────┘
     ↓ tool result
LLM synthesizes final answer
     ↓
Clean response with tool_used field
```

The router uses Groq's structured function-calling API first, with a text-based fallback mechanism for cases where the model generates malformed tool-call syntax — a real, observed failure mode discovered and documented during development (Llama 3.3 70B on Groq occasionally produces malformed function-call output for certain query phrasings; the fallback catches these reliably).

## Stack

- **LLM**: Groq API (`llama-3.3-70b-versatile`)
- **Tool routing**: Groq function calling + text-based fallback router
- **Web search**: Tavily API
- **Embeddings**: `sentence-transformers` (`all-MiniLM-L6-v2`)
- **Vector search**: FAISS (`faiss-cpu`)
- **Backend**: FastAPI + Pydantic + Uvicorn
- **Frontend**: Plain HTML/CSS/JS with tool-specific color theming
- **Deployment**: Docker on Hugging Face Spaces
- **Version control**: Git + GitHub

## Project Structure

```
multi-tool-agent/
├── tools/
│   ├── calculator.py      # Safe arithmetic via regex-guarded eval()
│   ├── web_search.py      # Tavily wrapper returning top-3 source snippets
│   └── rag_retrieval.py   # Chunking + FAISS indexing + semantic search
├── docs/                  # Knowledge base markdown files
│   ├── agent_fundamentals.md
│   ├── mcp_overview.md
│   └── genai_rag_fundamentals.md
├── router.py              # Tool routing with function-calling + fallback
├── api.py                 # FastAPI backend
├── evaluate.py            # Evaluation harness
├── static/
│   └── index.html         # Dark-theme frontend with tool-color UI
└── Dockerfile
```

## Evaluation Results

Tested against a 10-question verified set spanning all three tool categories, with both routing accuracy and answer accuracy measured independently:

| Metric | Result |
|---|---|
| Routing accuracy | 10/10 (100%) — consistent across all runs |
| Answer accuracy | 9-10/10 (90-100%) — minor variance due to LLM response format differences |
| Crashed (unrecovered) | 0/10 |
| Avg response time | ~1.1-1.4s |

**Routing accuracy was perfectly consistent** — the agent never once assigned a math question to web search, a current-events question to the knowledge base, or vice versa, across any observed run.

**Answer accuracy variance** on 1-2 questions per run is due to non-deterministic LLM phrasing, not incorrect computation or retrieval — the same pattern documented in Phase 1's evaluation findings. The tool was always selected correctly and the underlying result was always correct; the variation was in how the LLM phrased its final synthesized answer.

## Key Engineering Findings

**1. Function-calling reliability varies by model.** Llama 3.3 70B on Groq produces malformed tool-call syntax for certain query phrasings — verified empirically and reproducibly. Built a text-based fallback router that catches these cases, making the system reliable without depending on perfectly-structured function-call output. This is a real, documented limitation of open-weight models' function-calling implementations, not a hypothetical concern.

**2. Calculator tool is genuinely necessary.** Verified empirically that Llama 3.3 70B gets moderately complex arithmetic wrong consistently — tested 3 problems, all 3 wrong (errors ranging from 5th-digit precision loss to 40% deviation). A calculator tool guarantees correctness that the LLM alone cannot.

**3. Eval harnesses need their own testing.** Two of three apparent "failures" in early eval runs were caused by incorrect expected values in the eval set (wrong expected string format), not real agent failures — same finding as Phase 1. Expected values were independently verified via direct Python computation before being reported.

**4. RAG retrieval is semantically accurate but not always maximally specific.** The retrieval correctly identifies the right document out of three candidates, but occasionally returns a related chunk that answers a slightly different angle of the question than the exact phrasing asked — a known limitation of chunk-level similarity search without re-ranking.

## Known Limitations

- **Text-based fallback router is less precise than structured function calling** — it works reliably but is more susceptible to edge cases in tool description matching than a well-functioning structured API would be.
- **FAISS index is rebuilt on every startup** — the embedding model loads and re-embeds all documents each time the server starts. Acceptable for this scale (26 chunks, ~1 second), but would need persistent index caching for larger knowledge bases or production workloads.
- **Knowledge base is static** — documents must be manually updated and the server restarted to reflect new content. A production version would support dynamic document ingestion without restarting.
- **Free tier cold starts** — Hugging Face Spaces free tier spins down after inactivity; first request after idle may take 20-30 seconds while the container restarts and the embedding model loads.

## Running Locally

```bash
git clone https://github.com/ok315/Multi-Tool-Agent.git
cd Multi-Tool-Agent
python -m venv venv
venv\Scripts\Activate.ps1  # Windows
pip install -r requirements.txt
```

Create `.env`:
```
GROQ_API_KEY=your_groq_key
TAVILY_API_KEY=your_tavily_key
```

Run:
```bash
python -m uvicorn api:app --reload
```

Visit `http://127.0.0.1:8000` for the UI or `http://127.0.0.1:8000/docs` for Swagger.

## API

```
POST /ask
{
  "question": "What is 15% of 4827.50?"
}

Response:
{
  "question": "What is 15% of 4827.50?",
  "tool_used": "calculator",
  "answer": "15% of 4827.50 is 724.125"
}
```

```
GET /health  →  {"status": "ok"}
GET /docs    →  Swagger UI
```