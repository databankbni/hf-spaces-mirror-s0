import dataclasses
from pathlib import Path
from datetime import datetime, timezone

from app.ingestion.domain.models import ManifestSource, ParsedDocument
from app.ingestion_studio.domain.models import StageProgress
from app.ingestion_studio.infrastructure.job_repo import job_repo
from app.ingestion_studio.application.events import broadcast_job_event

async def execute_job(job_id: str, source: ManifestSource, gpu_artifact_path: Path | None = None) -> None:
    job = job_repo.get(job_id)
    if not job:
        return
        
    def set_stage(stage: str, pct: float, status: str = "running", detail: str = ""):
        if stage not in job.stage_progress:
            job.stage_progress[stage] = StageProgress(status=status, pct=pct, detail=detail, started_at=datetime.now(timezone.utc))
        else:
            job.stage_progress[stage].status = status
            job.stage_progress[stage].pct = pct
            job.stage_progress[stage].detail = detail
            if status in ("done", "failed"):
                job.stage_progress[stage].ended_at = datetime.now(timezone.utc)
        
        job.status = stage
        job.updated_at = datetime.now(timezone.utc)
        job_repo.update(job)
        broadcast_job_event(job_id, "stage_update", {"stage": stage, "progress": job.stage_progress[stage].model_dump()})
        broadcast_job_event(job_id, "job_update", job.model_dump())

    try:
        set_stage("profiling", 0.0, "running", "Starting profiler")
        
        from app.ingestion.application.profiler import Profiler
        profiler = Profiler()
        book_profile = profiler.profile(source)
        job.profile = dataclasses.asdict(book_profile)
        
        set_stage("profiling", 100.0, "done", "Profiling complete")
        
        from app.ingestion.application.extraction_planner import ExtractionPlanner
        planner = ExtractionPlanner()
        plan = planner.plan(book_profile, job.overrides)
        
        has_got_ocr = any(s.extractor == "got_ocr" for s in plan.steps)
        if has_got_ocr and not gpu_artifact_path:
            job.status = "needs_gpu_artifact"
            job.updated_at = datetime.now(timezone.utc)
            job_repo.update(job)
            broadcast_job_event(job_id, "job_update", job.model_dump())
            return
            
        set_stage("extracting", 0.0, "running", "Extracting document")
        
        from app.ingestion.application.extract_document import extract_document
        doc = extract_document(source, plan, gpu_artifact_path)
        
        parsed_doc_path = source.path.parent / "derived" / f"{source.path.stem}_parsed.json"
        parsed_doc_path.parent.mkdir(parents=True, exist_ok=True)
        parsed_doc_path.write_text(doc.model_dump_json())
        
        set_stage("extracting", 100.0, "done", "Extraction complete")
        
        job.status = "awaiting_confirmation"
        job.updated_at = datetime.now(timezone.utc)
        job_repo.update(job)
        broadcast_job_event(job_id, "job_update", job.model_dump())
        
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.updated_at = datetime.now(timezone.utc)
        job_repo.update(job)
        broadcast_job_event(job_id, "job_failed", {"error": str(exc)})


async def confirm_job_execution(job_id: str, source: ManifestSource) -> None:
    job = job_repo.get(job_id)
    if not job or job.status != "awaiting_confirmation":
        return
        
    def set_stage(stage: str, pct: float, status: str = "running", detail: str = ""):
        if stage not in job.stage_progress:
            job.stage_progress[stage] = StageProgress(status=status, pct=pct, detail=detail, started_at=datetime.now(timezone.utc))
        else:
            job.stage_progress[stage].status = status
            job.stage_progress[stage].pct = pct
            job.stage_progress[stage].detail = detail
            if status in ("done", "failed"):
                job.stage_progress[stage].ended_at = datetime.now(timezone.utc)
        
        job.status = stage
        job.updated_at = datetime.now(timezone.utc)
        job_repo.update(job)
        broadcast_job_event(job_id, "stage_update", {"stage": stage, "progress": job.stage_progress[stage].model_dump()})
        broadcast_job_event(job_id, "job_update", job.model_dump())

    try:
        parsed_doc_path = source.path.parent / "derived" / f"{source.path.stem}_parsed.json"
        if not parsed_doc_path.exists():
            raise FileNotFoundError("Parsed document artifact not found")
            
        doc = ParsedDocument.model_validate_json(parsed_doc_path.read_text())
        
        set_stage("segmenting", 0.0, "running", "Segmenting document")
        
        from app.ingestion.application.subject_pipeline import get_subject_pipeline_registry
        pipeline = get_subject_pipeline_registry().resolve(doc.source.subject)
        result = pipeline.segment(doc)
        
        set_stage("segmenting", 100.0, "done", "Segmenting complete")
        
        set_stage("chunking", 0.0, "running", "Enriching and chunking text")
        result.chunks[:] = pipeline.enrich(result.chunks)
        doc.sections = result.sections
        set_stage("chunking", 100.0, "done", "Chunking complete")

        # Readiness gate (GRO-129): a structurally-broken book is never committed.
        from app.ingestion.domain.readiness import evaluate_source_readiness
        readiness = evaluate_source_readiness(
            doc,
            result.chunks,
            result.duplicate_chunks_skipped,
            toc_anchor_count=result.toc_anchor_count,
            toc_detected_agreement=result.toc_detected_agreement,
        )
        job.readiness = readiness.model_dump(mode="json")
        if readiness.verdict == "FAIL":
            job.status = "blocked"
            job.error = "Readiness gate FAILED: " + "; ".join(readiness.reasons)
            job.updated_at = datetime.now(timezone.utc)
            job_repo.update(job)
            broadcast_job_event(job_id, "job_update", job.model_dump())
            return

        set_stage("loading", 0.0, "running", "Loading into Supabase")
        from app.ingestion.application.load_ingestion import load_ingestion_with_connection
        from app.platform.embeddings import BgeM3Embedder
        from app.platform.config import get_settings
        from app.ingestion.domain.manifest import CorpusManifest
        import psycopg
        from psycopg.rows import dict_row

        # Build CorpusManifest inline using the correct field names
        manifest = CorpusManifest(
            corpus_version="studio-upload",
            embedding_policy_id="bge-m3-dim-v1",
            chunking_policy_id="dim-page-section-v1",
            sources=[doc.source],
        )

        with psycopg.connect(get_settings().database_url, row_factory=dict_row) as conn:
            load_ingestion_with_connection(
                connection=conn,
                manifest_path=None,
                manifest=manifest,
                documents=[doc],
                chunks_by_source={doc.source.source_id: result.chunks},
                duplicate_chunks_skipped=0,
                embedder=BgeM3Embedder(),
            )
            # Fetch the DB-assigned document UUID after loading
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM public.documents WHERE source_id = %s",
                    (doc.source.source_id,),
                )
                row = cur.fetchone()
                job.document_id = str(row["id"]) if row else None
        
        set_stage("loading", 100.0, "done", "Data loaded into Supabase")
        
        job.status = "completed"
        job.updated_at = datetime.now(timezone.utc)
        from app.ingestion_studio.domain.models import JobStats
        job.stats = JobStats(
            pages=len(doc.pages),
            blocks=len(doc.blocks),
            sections=len(doc.sections),
            chunks=len(result.chunks),
            embedded=len(result.chunks)
        )
        job_repo.update(job)
        broadcast_job_event(job_id, "job_update", job.model_dump())
        
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.updated_at = datetime.now(timezone.utc)
        job_repo.update(job)
        broadcast_job_event(job_id, "job_failed", {"error": str(exc)})
