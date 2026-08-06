from fastapi import APIRouter, Depends

from app.platform.config import Settings, get_settings
from app.platform.db.session import Database, get_database
from typing import Literal
from pydantic import BaseModel

class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str
    database: Literal["ok", "not_configured", "error"]



router = APIRouter(tags=["health"])


def _database_dependency(settings: Settings = Depends(get_settings)) -> Database:
    return get_database(settings)


@router.get("/health", response_model=HealthResponse)
def healthcheck(
    settings: Settings = Depends(get_settings),
    database: Database = Depends(_database_dependency),
) -> HealthResponse:
    database_health = database.healthcheck()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        database=database_health.status,
    )
