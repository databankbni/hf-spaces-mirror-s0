import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from pathlib import Path
from app.ingestion_studio.application.events import event_generator
from app.ingestion_studio.application.executor import execute_job, confirm_job_execution
from app.ingestion_studio.domain.models import IngestionJob
from app.ingestion_studio.infrastructure.job_repo import job_repo
from app.ingestion.domain.models import ManifestSource

router = APIRouter(prefix="/api/studio/ingestion", tags=["ingestion_studio"])

@router.post("/upload")
async def upload_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    subject: str | None = Form(None),
    grade: int | None = Form(None),
):
    """Initiate an ingestion job from an uploaded PDF file."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
        
    job_id = str(uuid.uuid4())
    content = await file.read()
    content_hash = hashlib.sha256(content).hexdigest()
    
    # Save the file to a temporary location
    books_dir = Path(__file__).resolve().parent.parent.parent.parent.parent.parent / "data/books/uploads"
    books_dir.mkdir(parents=True, exist_ok=True)
    file_path = books_dir / f"{job_id}_{file.filename}"
    file_path.write_bytes(content)
    
    source = ManifestSource(
        source_id=job_id,
        path=file_path,
        subject=subject,
        grade=grade,
        chunking={"strategy": "page_overlap"} # default
    )
    
    job = IngestionJob(
        id=job_id,
        filename=file.filename,
        content_hash=content_hash,
        status="created",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    job_repo.create(job)
    
    background_tasks.add_task(execute_job, job_id, source)
    return job

@router.get("/jobs")
async def list_jobs():
    """List ingestion jobs."""
    return job_repo.list()

@router.get("/jobs/{id}")
async def get_job(id: str):
    """Get ingestion job by id."""
    job = job_repo.get(id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
    
@router.get("/jobs/{id}/events")
async def get_job_events(id: str, request: Request):
    """SSE endpoint for job events."""
    job = job_repo.get(id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return StreamingResponse(event_generator(id), media_type="text/event-stream")

@router.patch("/jobs/{id}/confirm")
async def confirm_job(id: str, background_tasks: BackgroundTasks):
    """Confirm parameters for an ingestion job and proceed to write to DB."""
    job = job_repo.get(id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.status != "awaiting_confirmation":
        raise HTTPException(status_code=400, detail="Job is not awaiting confirmation")
        
    books_dir = Path(__file__).resolve().parent.parent.parent.parent.parent.parent / "data/books/uploads"
    file_path = books_dir / f"{job.id}_{job.filename}"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Uploaded file not found")
        
    source = ManifestSource(
        source_id=job.id,
        path=file_path,
        chunking={"strategy": "page_overlap"}
    )
        
    background_tasks.add_task(confirm_job_execution, id, source)
    return {"id": id, "status": "confirming"}

@router.get("/jobs/{id}/graph")
async def get_job_graph(id: str):
    """Get the graph data for a completed job."""
    job = job_repo.get(id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    books_dir = Path(__file__).resolve().parent.parent.parent.parent.parent.parent / "data/books/uploads"
    derived_dir = books_dir / "derived"
    graph_path = derived_dir / f"{id}_graph.json"
    
    if not graph_path.exists():
        raise HTTPException(status_code=404, detail="Graph data not found (job may not be complete)")
        
    import json
    return json.loads(graph_path.read_text())
