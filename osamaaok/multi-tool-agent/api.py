import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from router import ask_with_routing

app = FastAPI(title="Multi-Tool Agent API")

app.mount("/static", StaticFiles(directory="static"), name="static")

class QuestionRequest(BaseModel):
    question: str

@app.get("/")
def serve_frontend():
    return FileResponse("static/index.html")

@app.post("/ask")
def ask(request: QuestionRequest):
    try:
        answer, tool_used, raw_result = ask_with_routing(request.question)
        return {
            "question": request.question,
            "tool_used": tool_used,
            "answer": answer
        }
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@app.get("/health")
def health():
    return {"status": "ok"}