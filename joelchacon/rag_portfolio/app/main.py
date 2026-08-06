from fastapi import FastAPI, HTTPException
# from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from uuid import uuid4

from app.core.personalized_rag import Personalized_RAG

# ----------------------------------------------------
# Initialize FastAPI app
# ----------------------------------------------------
app = FastAPI(title="Joel's Assistant API", version="1.1")

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],         
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# ----------------------------------------------------
# Request & Response Schemas
# ----------------------------------------------------
class QuestionRequest(BaseModel):
    user_id: Optional[str] = None
    question: str

class AskResponse(BaseModel):
    answer: str
    documents: Optional[List[str]] = None

# ----------------------------------------------------
# Initialize the RAG system
# ----------------------------------------------------
rag = Personalized_RAG(
    file_path="data/user_information/",
    user_id="default_user",
    persist_dir="./chroma_db",
)

# ----------------------------------------------------
# API Endpoints
# ----------------------------------------------------
@app.get("/")
async def root():
    return {"message": "Welcome to Joel's Personalized RAG API 🚀"}

@app.get("/health")
async def healthcheck():
    """
    Lightweight health check endpoint.
    Used by uptime monitors to keep the app alive and verify basic functionality.
    """
    try:
        # Optional: you can check if indexer is accessible
        _ = rag.user_id  # touch a simple property to ensure rag is initialized
        return {"status": "ok", "service": "joel-assistant", "version": "1.1"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Healthcheck failed: {e}")

@app.get("/status")
async def status():
    """Check if the system has an existing index."""
    indexed = rag.indexer.is_indexed()
    return {"indexed": indexed, "user_id": rag.user_id}

@app.post("/ask", response_model=AskResponse)
def ask_question(request: QuestionRequest):
    """
    Ask the assistant a question.
    Will return a message if no index exists yet.
    """
    try:
        user_id = request.user_id or str(uuid4())
        rag.user_id = user_id

        # Ensure the index is ready
        if not rag.vectorstore:
            if not rag.indexer.is_indexed():
                raise HTTPException(status_code=400, detail="Index not found. Please run /reindex first.")
            rag.index()  # Load existing persisted index

        # Ask the question
        answer = rag.ask(request.question)

        # Get retrieved documents (if retriever stores them)
        docs_retrieved = getattr(rag.retriever, "last_retrieved_docs", [])

        return AskResponse(
            answer=answer,
            documents=[doc.page_content for doc in docs_retrieved] if docs_retrieved else [],
        )

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing question: {e}")

@app.post("/reindex")
def reindex_data():
    """
    Manually trigger full reindexing of documents.
    """
    try:
        rag.index()  # uses the new index() method
        return {"status": "success", "message": "Reindexing completed successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during reindexing: {e}")
