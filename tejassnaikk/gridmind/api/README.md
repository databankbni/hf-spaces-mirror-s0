Run: `uvicorn api.main:app --reload` from the repo root. Requires `psycopg-pool>=3.2` (already in requirements.txt).
Required env vars: `DATABASE_URL=postgresql://gridmind:gridmind@localhost:5432/gridmind_embeddings`
LLM env vars (for /answer): `LLM_BASE_URL`, `LLM_MODEL`, `GEMINI_API_KEY`
Example (base): `curl -s -X POST http://localhost:8000/retrieve -H 'Content-Type: application/json' -d '{"question": "What must each Responsible Entity develop for supply chain risk management?", "k": 5}' | python -m json.tool`
Example (with cross-reference expansion): `curl -s -X POST http://localhost:8000/retrieve -H 'Content-Type: application/json' -d '{"question": "Which standard defines which BES Cyber Systems CIP-013 applies to?", "k": 5, "expand": true}' | python -m json.tool`
Example (/answer — retrieval + LLM synthesis): `curl -s -X POST http://localhost:8000/answer -H 'Content-Type: application/json' -d '{"question": "What must each Responsible Entity develop for supply chain risk management?", "k": 5}' | python -m json.tool`
