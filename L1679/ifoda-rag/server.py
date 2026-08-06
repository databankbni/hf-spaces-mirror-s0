"""
FastAPI server for IFODA RAG System.
Provides REST API and optional Web UI for integration with external systems.
"""

import logging
import os
import sys
from typing import Optional

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from query import IFODAQueryEngine

# Try importing FastAPI
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse
    from pydantic import BaseModel, Field
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    print("[WARNING] FastAPI/uvicorn not installed. Run: pip install fastapi uvicorn")

# Logging — clean, production-friendly.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("ifoda.api")

# Initialize query engine (singleton)
engine = None

def get_engine():
    global engine
    if engine is None:
        engine = IFODAQueryEngine(use_llm=False)
    return engine


# ========== API SCHEMAS ==========

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="User question in RU/EN/UZ")
    top_k: int = Field(5, ge=1, le=20, description="Number of chunks to retrieve after reranking")
    use_llm: bool = Field(False, description="Generate final answer via LLM (DeepSeek/OpenAI-compatible)")


class QueryResponse(BaseModel):
    query: str
    answer: str
    citations: list
    products_found: list
    confidence: str


class HealthResponse(BaseModel):
    status: str
    documents: int
    version: str
    llm_enabled: bool


# ========== CONFIG ==========

API_VERSION = "1.1.0"
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "*").split(",") if o.strip()]
HOST = os.environ.get("API_HOST", "0.0.0.0")
PORT = int(os.environ.get("API_PORT", "8000"))


# ========== FASTAPI APP ==========

if HAS_FASTAPI:
    app = FastAPI(
        title="IFODA RAG API",
        description="RAG System for IFODA Agro Chemical Company — product recommendations, dosages, application guidelines",
        version=API_VERSION,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup():
        eng = get_engine()
        llm_state = "enabled" if os.environ.get("OPENAI_API_KEY") else "disabled (no OPENAI_API_KEY)"
        doc_count = eng.retriever.doc_count
        if doc_count == 0:
            log.warning("No documents indexed! Run ingest.py to populate chroma_db.")
        log.info("IFODA RAG API v%s started", API_VERSION)
        log.info("  docs indexed : %d", doc_count)
        log.info("  LLM mode     : %s", llm_state)
        log.info("  CORS origins : %s", ALLOWED_ORIGINS)
        log.info("  bind         : %s:%d", HOST, PORT)

    @app.get("/health", response_model=HealthResponse)
    async def health():
        eng = get_engine()
        llm_available = bool(os.environ.get("OPENAI_API_KEY"))
        return HealthResponse(
            status="ok",
            documents=eng.retriever.doc_count,
            version=API_VERSION,
            llm_enabled=llm_available,
        )

    @app.post("/query", response_model=QueryResponse)
    async def query(req: QueryRequest):
        try:
            eng = get_engine()
            result = eng.query(req.query, top_k=req.top_k, use_llm=req.use_llm)
            return QueryResponse(
                query=result.query,
                answer=result.answer,
                citations=result.citations,
                products_found=result.products_found,
                confidence=result.confidence,
            )
        except HTTPException:
            raise
        except Exception as e:
            log.exception("Query failed: %s", e)
            raise HTTPException(status_code=500, detail=f"Query failed: {type(e).__name__}")

    @app.get("/context")
    async def context(q: str, top_k: int = 5):
        """Return raw context for external LLM integration."""
        if not q or not q.strip():
            raise HTTPException(status_code=400, detail="Query 'q' must not be empty")
        top_k = max(1, min(int(top_k), 20))
        try:
            eng = get_engine()
            ctx = eng.get_context_only(q, top_k=top_k)
            return {"query": q, "context": ctx}
        except Exception as e:
            log.exception("Context retrieval failed: %s", e)
            raise HTTPException(status_code=500, detail=f"Context retrieval failed: {type(e).__name__}")


    # ========== WEB UI ==========

    WEB_UI_HTML = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>IFODA RAG — Agro Knowledge Base</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
                background: linear-gradient(135deg, #0a4d2e 0%, #0d5e38 30%, #1a7a4c 100%);
                min-height: 100vh;
                color: #fff;
            }
            .container { max-width: 900px; margin: 0 auto; padding: 20px; }
            header {
                text-align: center;
                padding: 30px 0;
                border-bottom: 2px solid rgba(255,255,255,0.2);
                margin-bottom: 30px;
            }
            header h1 { font-size: 2em; margin-bottom: 5px; }
            header p { opacity: 0.8; font-size: 0.95em; }
            .search-box {
                background: rgba(255,255,255,0.1);
                backdrop-filter: blur(10px);
                border-radius: 16px;
                padding: 25px;
                margin-bottom: 25px;
            }
            .search-box input {
                width: 100%;
                padding: 15px 20px;
                border: none;
                border-radius: 12px;
                font-size: 1.05em;
                background: rgba(255,255,255,0.15);
                color: #fff;
                outline: none;
                transition: all 0.3s;
            }
            .search-box input:focus { background: rgba(255,255,255,0.25); }
            .search-box input::placeholder { color: rgba(255,255,255,0.5); }
            .search-box button {
                margin-top: 12px;
                padding: 12px 30px;
                background: #4caf50;
                color: #fff;
                border: none;
                border-radius: 12px;
                font-size: 1em;
                cursor: pointer;
                transition: all 0.3s;
            }
            .search-box button:hover { background: #66bb6a; transform: translateY(-1px); }
            .examples { margin-top: 15px; font-size: 0.85em; opacity: 0.7; }
            .examples span {
                background: rgba(255,255,255,0.1);
                padding: 4px 10px;
                border-radius: 10px;
                margin: 3px;
                cursor: pointer;
                display: inline-block;
            }
            .examples span:hover { background: rgba(255,255,255,0.25); }
            .result {
                background: rgba(255,255,255,0.08);
                backdrop-filter: blur(10px);
                border-radius: 16px;
                padding: 25px;
                margin-bottom: 20px;
                border-left: 4px solid #4caf50;
            }
            .result .confidence {
                display: inline-block;
                padding: 3px 10px;
                border-radius: 10px;
                font-size: 0.8em;
                margin-bottom: 10px;
            }
            .confidence.high { background: #4caf50; }
            .confidence.medium { background: #ff9800; }
            .confidence.low { background: #f44336; }
            .result .answer { white-space: pre-wrap; line-height: 1.7; font-size: 0.95em; }
            .result .sources {
                margin-top: 15px;
                padding-top: 15px;
                border-top: 1px solid rgba(255,255,255,0.15);
                font-size: 0.8em;
                opacity: 0.7;
            }
            .loading { text-align: center; padding: 30px; opacity: 0.7; }
            .loading::after {
                content: '';
                display: inline-block;
                width: 20px;
                height: 20px;
                border: 2px solid #fff;
                border-top-color: transparent;
                border-radius: 50%;
                animation: spin 0.7s linear infinite;
                margin-left: 10px;
            }
            @keyframes spin { to { transform: rotate(360deg); } }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>🌱 IFODA Agro Knowledge Base</h1>
                <p>RAG система для точных рекомендаций по препаратам, удобрениям и защите растений</p>
            </header>

            <div class="search-box">
                <input type="text" id="queryInput"
                       placeholder="Например: инсектицид против тли на хлопчатнике..."
                       onkeypress="if(event.key==='Enter')search()">
                <button onclick="search()">🔍 Найти</button>
                <div class="examples">
                    <span onclick="setQuery('Какой инсектицид против тли на хлопчатнике?')">🪲 Тля на хлопке</span>
                    <span onclick="setQuery('Норма расхода удобрения для томатов')">🍅 Удобрение томатов</span>
                    <span onclick="setQuery('Фунгицид против мучнистой росы на пшенице')">🌾 Мучнистая роса</span>
                    <span onclick="setQuery('What dosage of DALATE for wheat aphids?')">🇬🇧 Wheat aphids</span>
                </div>
            </div>

            <div id="results"></div>
        </div>

        <script>
            function setQuery(q) {
                document.getElementById('queryInput').value = q;
                search();
            }

            async function search() {
                const query = document.getElementById('queryInput').value.trim();
                if (!query) return;

                const resultsDiv = document.getElementById('results');
                resultsDiv.innerHTML = '<div class="loading">Поиск в базе знаний IFODA...</div>';

                try {
                    const resp = await fetch('/query', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({query: query, top_k: 5, use_llm: false})
                    });
                    const data = await resp.json();

                    resultsDiv.innerHTML = `
                        <div class="result">
                            <span class="confidence ${data.confidence}">
                                ${data.confidence === 'high' ? '🟢 Высокая точность' :
                                  data.confidence === 'medium' ? '🟡 Средняя точность' : '🔴 Низкая точность'}
                            </span>
                            <div class="answer">${escapeHtml(data.answer)}</div>
                            ${data.citations && data.citations.length ? `
                            <div class="sources">
                                📎 Источники: ${data.citations.map(c =>
                                    `[${c.index}] ${c.source} | Score: ${c.score}`
                                ).join(' · ')}
                            </div>` : ''}
                            ${data.products_found && data.products_found.length ? `
                            <div class="sources">
                                🏷 Найдены продукты: ${data.products_found.join(', ')}
                            </div>` : ''}
                        </div>
                    `;
                } catch (e) {
                    resultsDiv.innerHTML = `<div class="result" style="border-left-color:#f44336;">
                        ⚠️ Ошибка: ${escapeHtml(e.message)}
                    </div>`;
                }
            }

            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }
        </script>
    </body>
    </html>
    """

    @app.get("/", response_class=HTMLResponse)
    async def web_ui():
        return WEB_UI_HTML


# ========== MAIN ==========

def main():
    if HAS_FASTAPI:
        print("=" * 60)
        print("  IFODA RAG API Server")
        print(f"  Web UI : http://localhost:{PORT}")
        print(f"  API    : http://localhost:{PORT}/docs")
        print("=" * 60)
        uvicorn.run(app, host=HOST, port=PORT, log_level=os.environ.get("LOG_LEVEL", "info").lower())
    else:
        print("FastAPI not installed. Install with: pip install fastapi uvicorn")
        print("Falling back to CLI mode...")
        from query import interactive_cli
        interactive_cli()


if __name__ == "__main__":
    main()
