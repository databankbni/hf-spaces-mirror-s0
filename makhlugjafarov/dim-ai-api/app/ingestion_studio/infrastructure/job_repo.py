import json
from psycopg.rows import dict_row

import psycopg
from app.platform.config import get_settings
from app.ingestion_studio.domain.models import IngestionJob

class JobRepository:
    def get(self, job_id: str) -> IngestionJob | None:
        with psycopg.connect(get_settings().database_url) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT * FROM public.ingestion_jobs WHERE id = %s", (job_id,))
                row = cur.fetchone()
                if not row:
                    return None
                return IngestionJob(**row)

    def list(self, limit: int = 20) -> list[IngestionJob]:
        with psycopg.connect(get_settings().database_url) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT * FROM public.ingestion_jobs ORDER BY updated_at DESC LIMIT %s", (limit,))
                return [IngestionJob(**r) for r in cur.fetchall()]

    def create(self, job: IngestionJob) -> None:
        with psycopg.connect(get_settings().database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.ingestion_jobs 
                    (id, filename, content_hash, status, profile, overrides, stage_progress, stats, error, document_id, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        job.id, job.filename, job.content_hash, job.status,
                        json.dumps(job.profile) if job.profile else None,
                        json.dumps(job.overrides) if job.overrides else None,
                        json.dumps({k: v.model_dump() for k, v in job.stage_progress.items()}),
                        json.dumps(job.stats.model_dump()) if job.stats else None,
                        job.error, job.document_id, job.created_at, job.updated_at
                    )
                )

    def update(self, job: IngestionJob) -> None:
        with psycopg.connect(get_settings().database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE public.ingestion_jobs SET
                        status = %s,
                        profile = %s,
                        overrides = %s,
                        stage_progress = %s,
                        stats = %s,
                        error = %s,
                        document_id = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (
                        job.status,
                        json.dumps(job.profile) if job.profile else None,
                        json.dumps(job.overrides) if job.overrides else None,
                        json.dumps({k: v.model_dump() for k, v in job.stage_progress.items()}),
                        json.dumps(job.stats.model_dump()) if job.stats else None,
                        job.error, job.document_id, job.updated_at, job.id
                    )
                )

job_repo = JobRepository()
