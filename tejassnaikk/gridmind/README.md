---
title: GridMind
emoji: ⚡
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
short_description: NERC CIP compliance Q&A with cited retrieval
pinned: false
---

# GridMind

GridMind answers plain-English questions about NERC CIP reliability standards by retrieving the most relevant regulatory chunks from a pre-embedded corpus and synthesising a cited answer with an LLM. The corpus covers the NERC CIP-002 and CIP-013 standard families (96 chunks). Retrieval uses Reciprocal Rank Fusion over a dense cosine search (BGE-small-en-v1.5, 384-dim) and a BM25 lexical search, followed by freshness and obligation-strength priors — all in-process with no database dependency. The `/answer` endpoint passes the top-k chunks to an OpenAI-compatible LLM backend (configured via HF Space secrets) and returns an answer with inline citations referencing chunk IDs from the corpus.

## Endpoints

**Retrieve top-K relevant chunks:**
```bash
curl -s -X POST https://<your-space>.hf.space/retrieve \
  -H 'Content-Type: application/json' \
  -d '{"question": "What must each Responsible Entity develop for supply chain risk management?", "k": 5}' \
  | python -m json.tool
```

**Retrieve + LLM synthesis with inline citations:**
```bash
curl -s -X POST https://<your-space>.hf.space/answer \
  -H 'Content-Type: application/json' \
  -d '{"question": "What must each Responsible Entity develop for supply chain risk management?", "k": 5}' \
  | python -m json.tool
```

## Notes

- **Cold starts**: The free HF Spaces tier hibernates after inactivity. The first request after wake-up may take 15–30 seconds while the embedder loads. Subsequent requests are fast.
- **LLM secrets**: `/answer` requires `GEMINI_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL` set as HF Space repository secrets. Without them the endpoint returns 503.
- **No database**: This deployment is fully embedded — retrieval runs from pre-exported Parquet and NumPy artifacts baked into the image at build time.
