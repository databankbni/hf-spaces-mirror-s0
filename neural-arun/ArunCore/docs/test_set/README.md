# data/test_set/

Golden evaluation queries for ArunCore. This folder will contain a curated set of real questions used to validate retrieval quality and answer accuracy before the agent is deployed.

---

## Purpose
Before writing the ingestion pipeline or the agent layer, a test set must exist. Without it, there is no way to know if the retrieval system is working — whether the right chunks are being returned for the right questions, and whether the LLM is synthesising accurate answers from them.

---

## What Goes Here
A JSON file (`eval_set.json`) containing 30–50 questions across these categories:

| Category | Example Questions |
|---|---|
| **Identity** | "Who are you?" / "What do you do?" |
| **Project-specific** | "How does your legal RAG system handle exact section lookups?" |
| **Tech stack** | "What databases have you worked with?" |
| **Decision reasoning** | "Why did you use ChromaDB?" |
| **Personal background** | "How did you get into engineering?" |
| **Cross-project** | "Which projects use Groq?" |
| **Negative (out-of-scope)** | "What is your salary expectation?" ← should get a graceful fallback |

---

## Format (Planned)
```json
[
  {
    "id": "q001",
    "question": "What is your most complex project?",
    "expected_source": "legal_RAG_system/readme.md",
    "expected_topics": ["RAG", "legal documents", "ChromaDB"],
    "category": "project-specific"
  }
]
```

---

## Current Status
🔲 Not yet built — to be created after the ingestion pipeline is complete.
